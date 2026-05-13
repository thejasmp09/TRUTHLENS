"""
Counter-evidence agent.
Specifically hunts for debunking evidence, corrections and retractions
related to the claims being analyzed.
"""

from truthlens.agents.base import BaseAgent, AgentResult
from truthlens.search import web_search, fact_check_search


class CounterEvidenceAgent(BaseAgent):
    name = "counter_evidence"
    role = (
        "Actively searches for debunking articles, official corrections, "
        "retractions, and counter evidence for each claim. Acts as the "
        "devil's advocate to challenge viral naratives."
    )

    # Search modifiers designed to find debunking content
    DEBUNK_QUERIES = [
        '"{claim}" debunked OR fake OR falls OR hoax',
        '"{claim}" fact check',
        '"{claim}" correction OR retraction OR clarification',
        '"{claim}" snopes OR ploitifact OR reuters fact check',
    ]

    def execute(self, context: dict) -> AgentResult:
        claims = context.get("claims", [])

        if not claims:
            return AgentResult(
                agent_name=self.name,
                status="no_data",
                summary="No claims to find counter-evidence for.",
            )
        
        counter_evidence = []
        
        for claim in claims:
            self.logger.info("Finding counter-evidence: %s", claim[:80])
            
            all_results = []
            
            # Run multiple targeted searches
            for query_template in self.DEBUNK_QUERIES:
                query = query_template.format(claim=claim[:80])
                results = web_search(query, max_results=3)
                all_results.extend(results)
            
            # Also check fact-check databases explicitly
            fc_results = fact_check_search(claim, max_results=3)

            # Deduplicate by URL
            seen_urls = set()
            unique_results = []
            for r in all_results:
                if r["url"] not in seen_urls:
                    seen_urls.add(r["url"])
                    unique_results.append(r)

            # LLM analysis of counter evidence
            evidence_text = ""
            for i, r in enumerate(unique_results[:8], 1):
                evidence_text += (
                    f"{i}. [{r['title']}]({r['url']})\n"
                    f"   {r['snippet']}\n\n"
                )
            if not evidence_text:
                evidence_text = "No debunking content found.\n"

            fc_text = ""
            for i, fc in enumerate(fc_results, 1):
                fc_text += (
                    f"{i}. {fc['publisher']}: {fc['rating']}\n"
                    f"   URL: {fc['url']}\n\n"
                )      
            if not fc_text:
                fc_text = "No fact-checks found.\n"

            prompt = (
                "You are a counter-evidence specialist. Your job is to find and "
                "Summarize all available evidence that CONTRADICTS or DEBUNKS "
                "the following claim.\n\n"
                f"CLAIM: \"{claim}\"\n\n"
                f"DEBUNKING SOURCES FOUND:\n{evidence_text}\n"
                f"FACT-CHECK RESULTS:\n{fc_text}\n"    
                "Provide:\n"
                "1. COUNTER_EVIDENCE_EXISTS: Yes / No / Partial\n"
                "2. STRONGEST REBUTTAL: The single strongest piece of "
                "counter-evidence (or 'None found')\n"
                "3. DEBUNK SUMMARY: 2-3 sentences summarizing available "
                "counter-evidence\n\n"
                "Reply in this exact format:\n"
                "COUNTER_EVIDENCE_EXISTS: <yes/no/partial>\n"
                "STRONGEST REBUTTAL: <rebuttal>\n"
                "DEBUNK SUMMARY: <summary>"
            )

            analysis = self.call_llm(prompt)

            ce_data = {
                "claim": claim,
                "analysis": analysis,
                "debunking_sources": unique_results[:8],
                "fact_checks": fc_results,
                "counter_evidence_exists": "Unknown",
                "strongest_rebuttal": "",
                "debunk_summary": "",
            }

            for line in analysis.splitlines():
                stripped = line.strip()
                if stripped.upper().startswith("COUNTER_EVIDENCE_EXISTS:"):
                    ce_data["counter_evidence_exists"] = stripped.split(":", 1)[1].strip()
                elif stripped.upper().startswith("STRONGEST REBUTTAL:"):
                    ce_data["strongest_rebuttal"] = stripped.split(":", 1)[1].strip()
                elif stripped.upper().startswith("DEBUNK SUMMARY:"):
                    ce_data["debunk_summary"] = stripped.split(":", 1)[1].strip()

            counter_evidence.append(ce_data)

        # summary
        summary_parts = []
        for ce in counter_evidence:
            exists = ce.get("counter_evidence_exists", "Unknown") 
            summary_parts.append(
                f"- \"{ce['claim'][:60]}...\": Counter-evidence exists: {exists}"
            )       

        return AgentResult(
            agent_name=self.name,
            status="success",
            data={"counter_evidence": counter_evidence},
            summary="\n".join(summary_parts),
        )    

