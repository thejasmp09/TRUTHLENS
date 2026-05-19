"""
Core pipeline: Extract claims - multi-agent analysis - autopsy report.
Uses Google Gemini (free tier).
"""

import json
import logging
import re
import config
from dataclasses import dataclass, field

from truthlens.llm import call_gemini as _call_gemini

logger = logging.getLogger(__name__)


# Step 1 : Extract claims

def extract_claims(text: str) -> list[str]:
    """Extract discrete, checkable factual claims from content."""
    prompt = (
        "You are a fact-checking analyst. Extract every discrete, specific, checkable "
        "factual claim from the following text. Ignore opinions, questions, and vague "
        "statements. Return ONLY a valid JSON array of strings, nothing else.\n\n"
        f"Text: \"{text[:3000]}\"\n\n"
        "Example output: [\"Claim one\", \"Claim two\"]\n"
        "If there are no checkable claims, return: []"
    )

    raw = _call_gemini(prompt)

    # Strip markdown code fences if present
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1]
    if raw.endswith("```"):
        raw = raw.rsplit("```", 1)[0]
    raw = raw.strip()

    try:
        claims = json.loads(raw)
        if isinstance(claims, list):
            return [str(c) for c in claims]
    except json.JSONDecodeError:
        logger.warning("Failed to parse claims  JSON: %s",raw[:200])

    # Fallback heuristics: when LLM doesn't return JSON (e.g., MOCK_LLM),
    # try a simple sentence-splitting approach to extract candidate claims.
    if getattr(config, "MOCK_LLM", False):
        sentences = re.split(r'[\n\.\?!]+', text)
        candidates = [s.strip() for s in sentences if len(s.strip()) > 30]
        # return up to 5 candidate sentences as claims
        return candidates[:5]

    return []


#---shared data structures---

@dataclass
class ClaimVerdict:
    claim: str
    verdict: str # "confirmed" | "likely false" | "unverified"
    evidence: list[dict]= field(default_factory=list)
    existing_fact_checks: list[dict] = field(default_factory=list)
    explanation: str = ""
   

@dataclass
class AutopsyReport:
    claims: list[str]
    verdicts: list[ClaimVerdict]
    markdown:str
    overall_verdict: str 
    confidence: str
    agent_results: dict = None


#---Multi-agent pipeline---

def analyze_post_with_agents(
    content: str, source_url: str, platform: str, author: str
) -> AutopsyReport | None:
    """
    Run the full multi-agent pipeline:
    Coordinator dispatches 4 sub-agents in parallel, then synthesizes.
    """
    from truthlens.agents.coordinator import CoordinatorAgent

    logger.info("Analyzing post from %s by @%s (multi-agent mode)", platform, author)

    try:
        coordinator = CoordinatorAgent()
        result = coordinator.run(
            content=content,
            source_url=source_url,
            platform=platform,
            author=author,
        )

        if result is None:
            return None
        
        # Convert agent results into ClaimVerdict objects
        verdicts = []
        checker_verdicts = (result.get("agent_results", {}).get("claim_checker", {}).get("verdicts", []))
        for v in checker_verdicts:
            verdicts.append(ClaimVerdict(
                    claim=v.get("claim", ""),
                    verdict=v.get("verdict", "Unverified"),
                    evidence=v.get("web_sources", []),
                    existing_fact_checks=v.get("fact_checks", []),
                    explanation=v.get("explanation", ""),
                ))
            
        return AutopsyReport(
            claims=result.get("claims", []),
            verdicts=verdicts,
            markdown=result.get("autopsy_md", ""),
            overall_verdict=result.get("overall_verdict", ""),
            confidence=result.get("confidence", 0.0),
            agent_results=result.get("agent_results", {}),
        )
    
    except Exception:
        logger.exception("Multi-agent pipeline failed")
        return None
    