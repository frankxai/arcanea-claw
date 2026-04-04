# ArcaneaClaw Fleet — Current State
> Last updated: 2026-04-05 00:15 UTC

## Vital Signs

| Metric | Value |
|--------|-------|
| Version | 0.3.0 |
| Commits | 5 |
| Python files | 40 |
| Total LOC | 6,573 |
| Skills | 33 (8 media + 7 forge + 7 herald + 5 scout + 5 scribe + 1 notify) |
| Profiles | 5 (media, forge, herald, scout, scribe) |
| Tests | 85/85 passing |
| Supabase tables | 8 (asset_metadata, agent_registry, social_queue, publish_pipeline, nft_assets, campaign_signals, claw_events, storage buckets x2) |
| CI | GitHub Actions (Python 3.11-3.13 + lint + Docker) |
| Dashboard | /claw/dashboard on arcanea.ai (450 LOC, server-rendered) |

## What's Proven Working (E2E)

| Component | Status | Evidence |
|-----------|--------|----------|
| Daemon startup | WORKING | Starts, loads config, inits health server |
| Agent registration | WORKING | Registered in agent_registry table |
| Heartbeat | WORKING (fixed) | Was using wrong column, now uses 'config' |
| HTTP /health | WORKING | Returns JSON state |
| HTTP /metrics | WORKING | Pipeline timing, skill stats |
| HTTP /trigger | WORKING | Can trigger individual skills |
| media_scan | WORKING | 9 images scanned, hashed, inserted into Supabase |
| media_classify | BLOCKED | Gemini API key expired |
| media_dedup | WORKING | Runs, finds no dupes (correct) |
| media_process | WAITING | Needs classified assets to process |
| taste_score | WAITING | Needs processed assets to score |
| media_upload | WAITING | Needs scored assets to upload |
| social_prep | WAITING | Needs hero-tier assets |
| notify | WORKING | Runs, notifications disabled in local config |
| Cross-claw events | BUILT | Event emitters + consumer loop, untested live |
| Resilience layer | TESTED | 28 tests passing (circuit breaker, rate limiter, retry) |
| CLI | BUILT | run/trigger/status/metrics/fleet/skills subcommands |

## What's NOT Working

| Blocker | Impact | Fix |
|---------|--------|-----|
| Gemini API key expired | Blocks classify, score, social_prep, all Herald drafting, all Scout sentiment | Get fresh key from aistudio.google.com |
| No Railway deployment | Not running 24/7 | Deploy via Railway button |
| Twitter API not configured | Herald can't post | Get Twitter API v2 credentials |
| No real social posting tested | Herald is theoretical | Need platform API keys |
| Forge never triggered | NFT pipeline untested | Need ComfyUI or Replicate token |

## Architecture

```
arcanea-claw/
├── engine/
│   ├── daemon.py          # Main daemon (3 loops: heartbeat, pipeline, events)
│   ├── cli.py             # CLI subcommands
│   ├── supabase_client.py # DB operations
│   ├── resilience.py      # Circuit breaker, rate limiter, retry
│   ├── events.py          # Cross-claw event pipeline
│   ├── logging_config.py  # Structured JSON / human logging
│   └── skills/            # 33 skill modules
│       ├── media_*.py     # 7 media skills
│       ├── nft_*.py       # 7 forge skills
│       ├── herald_*.py    # 7 herald skills
│       ├── scout_*.py     # 5 scout skills
│       ├── scribe_*.py    # 5 scribe skills
│       └── notify.py      # Shared notify skill
├── profiles/              # 5 YAML configs (one per claw type)
├── tests/                 # 85 tests
├── docs/                  # CLAW_FLEET.md, E2E_DEMO_PLAN.md
├── .github/workflows/     # CI pipeline
├── Dockerfile             # Multi-stage, profile-based
└── docker-compose.yml     # All 5 claws from one image
```

## Key Decisions Made

1. **One repo, one image, multiple profiles** — not separate repos per claw
2. **Config-driven skill chains** — daemon reads skill_chain from YAML
3. **Dynamic kwarg injection** — inspect.signature determines what each skill needs
4. **Cross-claw events via Supabase** — not message queues (simplicity over scale)
5. **Python async daemon** — not serverless (needs persistent state + scheduled loops)
6. **Resilience built-in** — circuit breakers, rate limiters, retry at engine level
