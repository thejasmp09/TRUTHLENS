# TruthLens

Real-time misinformation autopsy agent.
Ingests posts from Reddit, Bluesky, and news RSS feeds, runs a 4-agent
parallel analysis pipeline, and generates structured fact-check reports
using free-tier APIs where possible.

How it works

1. Ingest (Reddit / Bluesky / News RSS)
2. Virality filter
3. Multi-agent analysis (parallel):
   - `OriginTracer` — finds earliest known source
   - `ClaimChecker` — verifies each claim against web evidence
   - `CounterEvidence` — hunts debunking articles & retractions
   - `SpreadMapper` — maps cross-platform amplification
4. Produce HTML report + store structured data in SQLite
5. Optional: publish results back to Bluesky

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env
```

**Required:**
- Gemini: `GEMINI_API_KEY` - (free tier) see your Gemini provider dashboard.
**Optional**
- Reddit: `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`
- Bluesky: `BLUESKY_HANDLE`, `BLUESKY_APP_PASSWORD`

## Usage

```bash
# Smoke test (Gemini key only)
python test_pipeline.py

# Run one full ingest/analyze/publish cycle:
```bash
python main.py --once

# Run continuously on the default schedule (every ~18 minutes):
python main.py
```

Outputs

- HTML reports are saved in the `reports/` directory and an index is
  generated at `reports/index.html`.

## Key design choices

- **$0/month** - DuckDuckGo search, Google Fact Check API, Gemini free tier
- **Auto model fallback** - cycles through 14 Gemini models when daily quota is hit
- **Thread-safe rate limitings** - 5s gap between LLM calls; parallel agents serialize cleanly
- **No LLM for synthesis** - final report is template-built from structured agent output (saves quota)

## Project structure (selected)

Below is the top-level structure of the `truthlens` package:

```
truthlens/
├─ agents/
│  ├─ agents.py
│  ├─ claim_checker.py
│  ├─ coordinator.py
│  ├─ counter_evidence.py
│  ├─ origin_tracer.py
│  └─ spread_mapper.py
├─ db.py
├─ filter.py
├─ ingest/
│  ├─ bluesky.py
│  ├─ news.py
│  └─ reddit.py
├─ llm.py
├─ pipeline.py
├─ publish.py
├─ report.py
└─ search.py
```

This list includes the main modules and the two subpackages `agents`
and `ingest` referenced by the codebase.


