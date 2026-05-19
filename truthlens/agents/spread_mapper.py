"""
Spread mapper agent
Tracks how a claim is spreading across platforms by searching for
reposts, variations, and amplification patterns.
"""

from truthlens.agents.base import BaseAgent, AgentResult
from truthlens.search import web_search


class SpreadMapperAgent(BaseAgent):
    name = "spread_mapper"
    role = (
        "Maps how a claim is spreading across the web. Identifies which "
        "platforms it's apperaing on, who is amplyfying it, and how the "
        "narrative is evolving as it spreads."
        )
    
    # Platform-specific search modifiers
    PLATFORM_SEARCHES = [
    ("Reddit", 'site:reddit.com "{claim}"'),
    ("Twitter/X", 'site:twitter.com OR site:x.com "{claim}"'),
    ("Facebook", 'site:facebook.com "{claim}"'),
    ("YouTube", 'site:youtube.com "{claim}"'),
    ("TikTok", 'site:tiktok.com "{claim}"'),
    ("News", '"{claim}" news'),
    ("Blogs", '"{claim}" blog'),
]

    def execute(self, context: dict) -> AgentResult:
        claims = context.get("claims", [])
        content = context.get("content", "")

        if not claims:
            return AgentResult(
                agent_name=self.name,
                status="no_data",
                summary="No claims to map spread for.",
            )
        
        # Use the most significant claim(first one) for spread mapping
        # to conserve API calls
        primary_claim = claims[0]
        short_claim = primary_claim[:80]

        self.logger.info("Mapping spread for claim: %s", short_claim)

        platform_hits = []

        for platform_name, query_template in self.PLATFORM_SEARCHES:
            query = query_template.format(claim=short_claim)
            results = web_search(query, max_results=5)
            if results:
                platform_hits.append({
                    "platform": platform_name,
                    "hit_count": len(results),
                    "results": results,
                })            

        # Build context for LLM spread analysis
        spread_text = ""
        for hit in platform_hits:
            spread_text += f"\n   {hit['platform']}: {hit['hit_count']} hits\n"
            for r in hit["results"]:
                spread_text += f"      - [{r['title']}]({r['url']})\n"
                spread_text += f"        {r['snippet'][:150]}\n"

        if not spread_text:
            spread_text = "No cross-platform spread detected.\n"

        prompt = (
            "You are a misinformation spread analyst. Based on the serach results "
            "below, analyze how this claim is spreading across the web.\n\n"
            f"CLAIM: \"{primary_claim}\"\n\n"
            f"PLATFORM PRESENCE:\n{spread_text}\n\n"
            "Provide:\n"
            "1. SPREAD LEVEL: Confined / Moderate / Widespread / Viral\n"
            "2. PLATFORMS AFFECTED: comma-separated list\n"
            "3. MUTATION: Has the claim changed as it spread? "
            "Describe any variations.\n"
            "4. KEY AMPLIFIERS: Who or what seems to be amplyfying this? "
            "(if identifiable)\n"
            "5. SPREAD SUMMARY: 2-3 sentences\n\n"
            "Reply in this exact format:\n"
            "SPREAD LEVEL: <level>\n"
            "PLATFORMS AFFECTED: <platforms>\n"
            "MUTATION: <mutation>\n"
            "KEY AMPLIFIERS: < amplifiers>\n"
            "SPREAD SUMMARY: <summary>\n"
        )

        analysis = self.call_llm(prompt)

        spread_data = {
            "primary_claim": primary_claim,
            "analysis": analysis,
            "platform_hits": platform_hits,
            "spread_level": "Unknown",
            "platforms_affected": "",
            "mutation": "",
            "key_amplifiers": "",
            "spread_summary": "",
        }

        for line in analysis.splitlines():
            stripped = line.strip()
            if stripped.upper().startswith("SPREAD LEVEL:"):
                spread_data["spread_level"] = stripped.split(":", 1)[1].strip()
            if stripped.upper().startswith("PLATFORMS AFFECTED:"):
                spread_data["platforms_affected"] = stripped.split(":", 1)[1].strip()
            if stripped.upper().startswith("MUTATION:"):
                spread_data["mutation"] = stripped.split(":", 1)[1].strip()
            if stripped.upper().startswith("KEY AMPLIFIERS:"):
                spread_data["key_amplifiers"] = stripped.split(":", 1)[1].strip()
            if stripped.upper().startswith("SPREAD SUMMARY:"):
                spread_data["spread_summary"] = stripped.split(":", 1)[1].strip()

        # Summary
        level = spread_data.get("spread_level", "Unknown")
        platforms = spread_data.get("platforms_affected", "Unknown")
        summary = f"Spread level: {level}. Platforms affected: {platforms}."

        return AgentResult(
            agent_name=self.name,
            status="success",
            data={"spread": spread_data},
            summary=summary,
        )
