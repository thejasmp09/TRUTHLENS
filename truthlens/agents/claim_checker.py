"""
Claim Checker Agent.
Verifies each extracted claim against web sources nd existing fact-checks.
"""

from truthlens.agents.base import BaseAgent, AgentResult
from truthlens.search import web_search, fact_check_search


class ClaimCheckerAgent(BaseAgent):
    name = "claim_checker"
    role = (
        "Verifies factual claims by cross-referencing web sources and "
        "existing fact-check databases, Produces a verdict for each claim."
    )

    def execute(self, context: dict) -> AgentResult:
        claims = context.get("claims", [])

        if not claims:
            return AgentResult(
                agent_name=self.name,
                status="error",
                summary="No claims to varify.",
            )
        
        verdicts = []
        
        for claim in claims:
            self.logger.info("Checking claim: %s", claim[:80])

            #search for supporting/refuting evidence
            search_results = web_search(claim,max_results=5)

            #check exesting fact-checks databases
            fc_results= fact_check_search(claim,max_results=5)

            #Build context for LLM
            sources_text=""
            for i,r in enumerate(search_results,1):
                sources_text+=(
                    f"  {i}. [{r['title']}]({r['url']})\n"
                    f"      {r['snippet']}\n\n"                                
                )
            if not sources_text:
                sources_text="No web results found.\n"

            fc_text=""
            for i,fc in enumerate(fc_results,1):
                fc_text+=(
                    f"  {i}. {fc['publisher']}: \{fc['rating']}\n"
                    f"      claim: {fc['claim']}\n"
                    f"      URL: {fc['url']}\n\n"
                )        
            if not fc_text:
                fc_text=" No existing fact-check found.\n"

            prompt=(
                "You are a rigorous fact-checker,Assess this claim using ONLY"
                "the evidence provided.Do not use prior knowledge.\n\n"
                f"CLAIM: \"{claim}\"\n\n"
                f"WEB EVIDENCE:\n{sources_text}\n"
                f"EXISTING FACT-CHECKS:\n{fc_text}\n"
                "Provide your assessment:\n"
                "1. VERDICT: Confirmed / Likely False / Unverified\n"
                "2. EXPLANATION: 2-3 sentences citing specific sources\n"
                "3. KEY EVIDENCE: The single most important piece of evidence\n\n"
                "Reply in this exact format:\n"
                "VERDICT: <verdict>\n"
                "EXPLANATION: < explanation>\n"
                "KEY EVIDENCE: <evidence>"
            )

            analysis = self.call_llm(prompt)

            verdict_data = {
                "claim": claim,
                "analysis": analysis,
                "web_sources": search_results,
                "fact_checks": fc_results,
                "verdict": "unverified",
                "explanation": "",
                "key_evidence": "",
            }     

            for line in analysis.splitlines():
                stripped = line.strip()
                if stripped.upper().startswith("VERDICT:"):
                    v = stripped.split(":",1)[1].strip().lower()
                    if "confirmed" in v:
                        verdict_data["verdict"] = "confirmed"
                    elif "false" in v:
                        verdict_data["verdict"] = "Likely False"
                    else:
                        verdict_data["verdict"] = "unverified"
                elif stripped.upper().startswith("EXPLANATION:"):
                    verdict_data["explanation"] = stripped.split(":",1)[1].strip()  
                elif stripped.upper().startswith("KEY EVIDENCE:"):
                    verdict_data["key_evidence"] = stripped.split(":",1)[1].strip()

            verdicts.append(verdict_data)

        #Build summary
        summary_parts=[]
        for v in verdicts:
                summary_parts.append(
                    f"- \"{v['claim'][:60]}...\"-> {v['verdict']}"
            )      
                
        return AgentResult(
            agent_name=self.name,
            status="success",
            data={"verdicts": verdicts},
            summary="\n".join(summary_parts),
        )        
