"""
Coordinator Agent.
Orchestrates the 4 sub-agents in parallel, collects their results,
and synthesizes the final autopsy report.
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import config
from truthlens.agents.base import BaseAgent, AgentResult
from truthlens.agents.origin_tracer import OriginTracerAgent
from truthlens.agents.claim_checker import ClaimCheckerAgent
from truthlens.agents.counter_evidence import CounterEvidenceAgent
from truthlens.agents.spread_mapper import SpreadMapperAgent
from truthlens.pipeline import extract_claims as _extract_claims

logger = logging.getLogger(__name__)


class CoordinatorAgent:
    """
    The Coordinater does not inherit from BaseAgent - it is the orchestrator.
    
    Workflow:
    1. Extract claims from content (preprocessing)
    2. Spawn 4 sub-agents in parallel with shared context
    3. Collect all results
    4. Synthesize a unified autopsy report
    """

    def __init__(self):
        self.logger = logging.getLogger("truthlens.agent.coordinator")
        self.sub_agents: list[BaseAgent] = [
            OriginTracerAgent(),
            ClaimCheckerAgent(),
            CounterEvidenceAgent(),
            SpreadMapperAgent(),
        ]

    def _run_agent(self, agent: BaseAgent, context: dict) -> AgentResult:
        """Run a single agent with error handling."""
        try:
            self.logger.info("Dispatching %s agent", agent.name)
            start = time.time()
            result = agent.execute(context)
            elapsed = time.time() - start
            self.logger.info(
                "%s agent completed in %.1fs (status: %s)",
                agent.name, elapsed, result.status,
            )
            return result
        except Exception as e:
            self.logger.exception("Agent %s failed", agent.name)
            return AgentResult(
                agent_name=agent.name,
                status="error",
                error=str(e),
            )
        
    def run(
        self,
        content: str,
        source_url: str,
        platform: str,
        author: str,
        ) -> dict | None:
        """
        Full coordinator pipeline:
        Extract claims -> dispatch sub-agents in parallel -> synthesize report.

        Returns a dict with:
            claims, agent_results, autopsy_md, overall_verdict, confidence
        Or None if no checkable claims found.
        """
        total_start = time.time()
        self.logger.info("=" * 50)
        self.logger.info("Coordinator activated for %s post by @%s", platform, author)

        # Step 1: Extract claims
        self.logger.info("Step 1: Extracting claims...")
        claims = _extract_claims(content)

        if not claims:
            self.logger.info("No checkable claims found. Aborting.")
            return None

        self.logger.info("Found %d claims: %s", len(claims), claims)

        # Step 2: Build shared context
        context = {
            "content": content,
            "claims": claims,
            "source_url": source_url,
            "platform": platform,
            "author": author,
        }

        # Step 3: Dispatch sub-agents in parallel
        self.logger.info("Step 2: Dispatching %d sub-agents in parallel...", len(self.sub_agents))
        agent_results: dict[str, AgentResult] = {}

        with ThreadPoolExecutor(max_workers=4) as executor:
            future_to_agent = {
                executor.submit(self._run_agent, agent, context): agent
                for agent in self.sub_agents
            }

            for future in as_completed(future_to_agent):
                agent = future_to_agent[future]
                result = future.result()
                agent_results[agent.name] = result

        # Step 4: Synthesize autopsy report
        self.logger.info("Step 3: Synthesizing autopsy report...")

        # Determine overall verdict from claim_checker results
        checker_result = agent_results.get("claim_checker")
        overall_verdict, confidence = self._compute_verdict(checker_result)

        # Build the autopsy markdown
        autopsy_md = self.synthesize_report(
            content = content,
            source_url = source_url,
            platform = platform,
            author = author,
            claims = claims,
            agent_results = agent_results,
            overall_verdict = overall_verdict,
            confidence = confidence,
        )

        total_elapsed = time.time() - total_start
        self.logger.info(
            "Coordinator completed in %.1fs. Overall verdict: %s (confidence: %.2f)",
            total_elapsed, overall_verdict, confidence,
        )

        return {
            "claims": claims,
            "agent_results": {name: r.data for name, r in agent_results.items()},
            "agent_summaries": {name: r.summary for name, r in agent_results.items()},
            "autopsy_md": autopsy_md,
            "overall_verdict": overall_verdict,
            "confidence": confidence,
        }

    def _compute_verdict(self, checker_result: AgentResult | None) -> tuple[str, str]:
        """Derive overall verdict from claim checker results."""
        if not checker_result or checker_result.status != "success":
            return "unverifiable","Low"
        
        verdicts_data = checker_result.data.get("verdicts",[])
        verdict_values = [v.get("verdict","unverifiable") for v in verdicts_data]

        if not verdict_values:
            return "Unverifiable", "Low"
        
        if all(v == "Confirmed" for v in verdict_values):
            return "Confirmed True", "High"
        elif all(v == "Likely False" for v in verdict_values):
            return "Likely Misinformation", "High"
        elif any(v == "Likely False" for v in verdict_values):
            return "contains False Claims", "Medium"
        else:
            return "Unverified", "Low"
        
    def synthesize_report(
        self,
        content: str,
        source_url: str,
        platform: str,
        author: str,
        claims: list[str],
        agent_results: dict[str, AgentResult],
        overall_verdict: str,
        confidence: str,
    ) -> str:
        """Build the autopsy report directly from structured agent data (no extra LLM call)."""

        checker = agent_results.get("claim_checker")
        tracer = agent_results.get("origin_tracer")
        counter = agent_results.get("counter_evidence")
        mapper = agent_results.get("spread_mapper")

        # Index agent outputs by claim text for O(1) lookup
        checker_map: dict[str, dict] = {}
        if checker and checker.status == "success":
            for v in checker.data.get("verdicts", []):
                checker_map[v["claim"]] = v

        tracer_map: dict[str, dict] = {}
        if tracer and tracer.status == "success":
            for o in tracer.data.get("origins", []):
                tracer_map[o["claim"]] = o

        counter_map: dict[str, dict] = {}
        if counter and counter.status == "success":
            for ce in counter.data.get("counter_evidence", []):
                counter_map[ce["claim"]] = ce

        # Build markdown report
        lines = [
            f"# TruthLens Autopsy Report",
            "",
            "## TL:DR",
            "",
        ]

        # Count verdicts for TL;DR
        false_count = sum(1 for c in claims if checker_map.get(c, {}).get("verdict") == "Likely False")
        unverified_count = sum(1 for c in claims if checker_map.get(c, {}).get("verdict") == "Unverified")
        total = len(claims)

        if false_count > 0:
            lines.append(
                f"Analysis of {total} claims found {false_count} likely false "
                f"and {unverified_count} unverified. "
                f"**Overall verdict: {overall_verdict}** (confidence: {confidence})"
            )
        else:
            lines.append(
                f"Analysis of {total} claims found {unverified_count} unverified. "
                f"**Overall verdict: {overall_verdict}** (confidence: {confidence})"
            )

        lines += [
            "",
            "## Original Post",
            "",
            f"> {content[:2000]}",
            "",
            f"Source:** {source_url} | **Author:** @{author} | **Platform:** {platform}",
            "",
            "## Claim Analysis",
            "",
        ]

        for claim in claims:
            v = checker_map.get(claim, {})
            o = tracer_map.get(claim, {})
            ce = counter_map.get(claim, {})

            verdict = v.get("verdict", "Unverified")
            explanation = v.get("explanation", "No analysis available.")
            origin = o.get("probable_origin", "")
            rebuttal = ce.get("strongest_rebuttal", "")

            lines.append(f"### \"{claim}\"")
            lines.append("")
            lines.append(f"- **Verdict**: {verdict}")
            lines.append(f"- **Evidence**: {explanation}")
            if origin:
                lines.append(f"- **Origin:** {origin}")
            if rebuttal and rebuttal.lower() not in ("none", "none found", "none found."):
                lines.append(f"- **Counter-evidence:** {rebuttal}")
            lines.append("")

        # Spread section
        lines.append("## Spread Assessment")
        lines.append("")
        if mapper and mapper.status == "success":
            spread = mapper.data.get("spread", {})
            lines.append(f"- **Spread level:** {spread.get('spread_level', 'Unknown')}")
            lines.append(f"- **Platforms** {spread.get('platforms_affected', 'None identified')}")
            if spread.get("mutation"):
                lines.append(f"- **Narrative mutations:** {spread['mutation']}")
            if spread.get("key_amplifiers"):
                lines.append(f"- **Key amplifiers:** {spread['key_amplifiers']}")
        else:
            lines.append("Spread data not available.")
        lines.append("")

        # Verdict
        lines.append("## Verdict")
        lines.append("")
        lines.append(f"**{overall_verdict}** (Confidence: {confidence})")

        return "\n".join(lines)
    