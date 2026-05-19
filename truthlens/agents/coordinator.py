"""
Coordinator Agent.
Orchestrates the 4 sub-agents in parallel and synthesizes the autopsy report.
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

    def __init__(self):
        self.logger = logging.getLogger("truthlens.agent.coordinator")
        self.sub_agents: list[BaseAgent] = [
            OriginTracerAgent(),
            ClaimCheckerAgent(),
            CounterEvidenceAgent(),
            SpreadMapperAgent(),
        ]

    def _run_agent(self, agent: BaseAgent, context: dict) -> AgentResult:
        try:
            self.logger.info("Dispatching %s agent", agent.name)
            start = time.time()
            result = agent.execute(context)
            elapsed = time.time() - start
            self.logger.info("%s agent completed in %.1fs (status: %s)", agent.name, elapsed, result.status)
            return result
        except Exception as e:
            self.logger.exception("Agent %s failed", agent.name)
            return AgentResult(agent_name=agent.name, status="error", error=str(e))

    def run(self, content: str, source_url: str, platform: str, author: str) -> dict | None:
        total_start = time.time()
        self.logger.info("=" * 50)
        self.logger.info("Coordinator activated for %s post by @%s", platform, author)

        self.logger.info("Step 1: Extracting claims...")
        claims = _extract_claims(content)

        if not claims:
            self.logger.info("No checkable claims found. Aborting.")
            return None

        self.logger.info("Found %d claims: %s", len(claims), claims)

        context = {
            "content": content,
            "claims": claims,
            "source_url": source_url,
            "platform": platform,
            "author": author,
        }

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

        self.logger.info("Step 3: Synthesizing autopsy report...")
        checker_result = agent_results.get("claim_checker")
        overall_verdict, confidence = self._compute_verdict(checker_result)

        autopsy_md = self.synthesize_report(
            content=content,
            source_url=source_url,
            platform=platform,
            author=author,
            claims=claims,
            agent_results=agent_results,
            overall_verdict=overall_verdict,
            confidence=confidence,
        )

        total_elapsed = time.time() - total_start
        self.logger.info("Coordinator completed in %.1fs. Verdict: %s (%s)", total_elapsed, overall_verdict, confidence)

        return {
            "claims": claims,
            "agent_results": {name: r.data for name, r in agent_results.items()},
            "agent_summaries": {name: r.summary for name, r in agent_results.items()},
            "autopsy_md": autopsy_md,
            "overall_verdict": overall_verdict,
            "confidence": confidence,
        }

    def _compute_verdict(self, checker_result: AgentResult | None) -> tuple[str, str]:
        if not checker_result or checker_result.status != "success":
            return "Unverifiable", "Low"
        verdicts_data = checker_result.data.get("verdicts", [])
        verdict_values = [v.get("verdict", "unverified") for v in verdicts_data]
        if not verdict_values:
            return "Unverifiable", "Low"
        if all(v == "confirmed" for v in verdict_values):
            return "Confirmed True", "High"
        elif all(v == "Likely False" for v in verdict_values):
            return "Likely Misinformation", "High"
        elif any(v == "Likely False" for v in verdict_values):
            return "Contains False Claims", "Medium"
        else:
            return "Unverified", "Low"

    def synthesize_report(self, content, source_url, platform, author, claims, agent_results, overall_verdict, confidence) -> str:

        checker = agent_results.get("claim_checker")
        tracer = agent_results.get("origin_tracer")
        counter = agent_results.get("counter_evidence")
        mapper = agent_results.get("spread_mapper")

        checker_map = {}
        if checker and checker.status == "success":
            for v in checker.data.get("verdicts", []):
                checker_map[v["claim"]] = v

        tracer_map = {}
        if tracer and tracer.status == "success":
            for o in tracer.data.get("origins", []):
                tracer_map[o["claim"]] = o

        counter_map = {}
        if counter and counter.status == "success":
            for ce in counter.data.get("counter_evidence", []):
                counter_map[ce["claim"]] = ce

        spread_data = {}
        if mapper and mapper.status == "success":
            spread_data = mapper.data.get("spread", {})

        total = len(claims)
        false_count = sum(1 for c in claims if checker_map.get(c, {}).get("verdict") == "Likely False")
        confirmed_count = sum(1 for c in claims if checker_map.get(c, {}).get("verdict") == "confirmed")
        unverified_count = total - false_count - confirmed_count

        lines = [
            "# TruthLens Autopsy Report",
            "",
            "## TL;DR",
            "",
            f"Analysis of {total} claim(s): {confirmed_count} confirmed, "
            f"{false_count} likely false, {unverified_count} unverified. "
            f"**Overall verdict: {overall_verdict}** (confidence: {confidence})",
            "",
            "## Original Post",
            "",
            f"> {content[:2000]}",
            "",
            f"**Source:** {source_url} | **Author:** @{author} | **Platform:** {platform}",
            "",
            "---",
            "",
            "## 🔍 Agent 1: Claim Checker",
            "",
            "_Verifies each claim against live web evidence and fact-check databases._",
            "",
        ]

        for claim in claims:
            v = checker_map.get(claim, {})
            verdict = v.get("verdict", "Unverified")
            explanation = v.get("explanation", "No analysis available.")
            key_evidence = v.get("key_evidence", "")
            web_sources = v.get("web_sources", [])
            fact_checks = v.get("fact_checks", [])
            icon = {"confirmed": "✅", "Likely False": "❌"}.get(verdict, "⚠️")

            lines.append(f"### {icon} \"{claim}\"")
            lines.append(f"- **Verdict:** {verdict}")
            lines.append(f"- **Explanation:** {explanation}")
            if key_evidence and "mock" not in key_evidence.lower():
                lines.append(f"- **Key Evidence:** {key_evidence}")
            if web_sources:
                lines.append("- **Web Sources:**")
                for s in web_sources[:3]:
                    lines.append(f"  - [{s.get('title', s.get('url',''))}]({s.get('url','')})")
            if fact_checks:
                lines.append("- **Fact Checks:**")
                for fc in fact_checks[:3]:
                    lines.append(f"  - {fc.get('publisher','')}: {fc.get('rating','')} — [{fc.get('url','')}]({fc.get('url','')})")
            lines.append("")

        lines += [
            "---", "",
            "## 🕵️ Agent 2: Origin Tracer", "",
            "_Traces where each claim first appeared and whether it has been distorted._", "",
        ]

        if tracer and tracer.status == "success":
            for claim in claims:
                o = tracer_map.get(claim, {})
                lines.append(f"### \"{claim}\"")
                lines.append(f"- **Probable Origin:** {o.get('probable_origin', 'Could not determine.')}")
                if o.get("original_context"):
                    lines.append(f"- **Original Context:** {o.get('original_context')}")
                if o.get("confidence"):
                    lines.append(f"- **Confidence:** {o.get('confidence')}")
                earliest = o.get("earliest_mentions", [])
                if earliest:
                    lines.append("- **Earliest Mentions:**")
                    for m in earliest[:3]:
                        lines.append(f"  - [{m.get('title', m.get('url',''))}]({m.get('url','')})")
                lines.append("")
        else:
            lines += ["_Origin tracer data not available._", ""]

        lines += [
            "---", "",
            "## 🛡️ Agent 3: Counter Evidence", "",
            "_Hunts for debunking articles, corrections, and retractions._", "",
        ]

        if counter and counter.status == "success":
            for claim in claims:
                ce = counter_map.get(claim, {})
                lines.append(f"### \"{claim}\"")
                lines.append(f"- **Counter-Evidence Exists:** {ce.get('counter_evidence_exists', 'Unknown')}")
                rebuttal = ce.get("strongest_rebuttal", "")
                if rebuttal and rebuttal.lower() not in ("", "none", "none found", "none found."):
                    lines.append(f"- **Strongest Rebuttal:** {rebuttal}")
                if ce.get("debunk_summary"):
                    lines.append(f"- **Summary:** {ce.get('debunk_summary')}")
                debunking = ce.get("debunking_sources", [])
                if debunking:
                    lines.append("- **Debunking Sources:**")
                    for s in debunking[:3]:
                        lines.append(f"  - [{s.get('title', s.get('url',''))}]({s.get('url','')})")
                lines.append("")
        else:
            lines += ["_Counter-evidence data not available._", ""]

        lines += [
            "---", "",
            "## 📡 Agent 4: Spread Mapper", "",
            "_Maps how the claim is spreading across platforms._", "",
        ]

        if mapper and mapper.status == "success" and spread_data:
            lines.append(f"- **Spread Level:** {spread_data.get('spread_level', 'Unknown')}")
            lines.append(f"- **Platforms Affected:** {spread_data.get('platforms_affected', 'None identified')}")
            if spread_data.get("mutation"):
                lines.append(f"- **Narrative Mutations:** {spread_data.get('mutation')}")
            if spread_data.get("key_amplifiers"):
                lines.append(f"- **Key Amplifiers:** {spread_data.get('key_amplifiers')}")
            if spread_data.get("spread_summary"):
                lines.append(f"- **Summary:** {spread_data.get('spread_summary')}")
            platform_hits = spread_data.get("platform_hits", [])
            if platform_hits:
                lines.append("")
                lines.append("**Platform Hit Counts:**")
                for ph in platform_hits:
                    lines.append(f"  - {ph['platform']}: {ph['hit_count']} result(s)")
        else:
            lines += ["_Spread data not available._"]

        lines += [
            "", "---", "",
            "## ⚖️ Final Verdict", "",
            f"**{overall_verdict}** (Confidence: {confidence})", "",
        ]

        return "\n".join(lines)