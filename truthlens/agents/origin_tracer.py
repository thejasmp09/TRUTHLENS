"""
Origin tracing agent.
Finds the earliest known instance of each claim to identify
where the information (or misinformation) likely originated.
"""

from truthlens.agents.base import BaseAgent, AgentResult
from truthlens.search import time_filtered_search, web_search


class OriginTracerAgent(BaseAgent):
    name = "origin_tracer"
    role = (
        "Traces the origin of a claim by searching for the earliest known "
        "mentions across the web. Identifies the probable source and how "
        "the narrative first appeared."
        )

    def execute(self , context: dict) -> AgentResult:
        claims = context.get("claims", [])
        content = context.get("content", "")

        if not claims:
            return AgentResult(
                agent_name=self.name,
                status="no_data",
                summary="No claims to trace.",
            )
        
        origins = []

        for claim in claims:
            self.logger.info("Tracing origin: %s", claim[:80])

            # Search for earliest mentions
            early_results = time_filtered_search(claim, max_results=5)

            # Also search with "first reported" / "original source" modifiers
            source_result = web_search(
                f'"{claim[:80]}" original source OR first reported',
                max_results=3,
            )

            all_results = early_results + source_result

            # Use LLM to analyze the origin
            results_text = ""
            for i, r in enumerate(all_results, 1):
                results_text += (
                    f"  {i}. [{r['title']}]({r['url']})\n"
                    f"     {r['snippet']}\n\n"
                )

            if not results_text:
                results_text = " No results found.\n"

            prompt = (
                f"You are an investigative analyst tracing the origin of a claim.\n\n"
                f"CLAIM: \"{claim}\"\n\n"
                f"EARLIEST MENTIONS FOUND:\n{results_text}\n"
                "Based on these rsults, determine:\n"
                "1. PROBABLE ORIGIN: Where did this claim likely first appear? "
                "(specific source, date if available)\n"
                "2. ORIGINAL CONTEXT: Was the original context different from how "
                "it's being shared now?\n"
                "3. CONFIDENCE: High / Medium / Low\n\n"
                "Reply in this exact format:\n"
                "PROBABLE ORIGIN: <origin>\n"
                "ORIGINAL CONTEXT: <context>\n"
                "CONFIDENCE: <level>"
            )

            analysis = self.call_llm(prompt)

            origin_data = {
                "claim": claim,
                "analysis": analysis,
                "earliest_mentions": all_results[:5],
            }

            # Parse structured fields
            for line in analysis.splitlines():
                stripped = line.strip()
                if stripped.upper().startswith("PROBABLE ORIGIN:"):
                    origin_data["probable_origin"] = stripped.split(":", 1)[1].strip()
                if stripped.upper().startswith("ORIGINAL CONTEXT:"):
                    origin_data["original_context"] = stripped.split(":", 1)[1].strip()
                if stripped.upper().startswith("CONFIDENCE:"):
                    origin_data["confidence"] = stripped.split(":", 1)[1].strip()

            origins.append(origin_data)

        # Build summary
        summary_parts = []
        for o in origins:
            origin = o.get("probable_origin", "Unknown")
            summary_parts.append(f"- Claim: \"{o['claim'][:60]}...\" | Probable Origin: {origin}")

        return AgentResult(
            agent_name=self.name,
            status="success",
            data={"origins": origins},
            summary="\n".join(summary_parts),
        )
    