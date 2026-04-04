# The Claw Fleet — ArcaneaClaw Multi-Agent Architecture

> One engine. Five Claws. One shared brain.

---

## Architecture

```
                    ┌──────────────────────────────┐
                    │      Supabase (Shared)        │
                    │  asset_metadata  agent_registry│
                    │  social_queue    nft_assets    │
                    │  content_pipeline campaigns    │
                    └─────────┬────────────────┬────┘
                              │                │
         ┌────────────────────┼────────────────┼────────────────┐
         │                    │                │                │
    ┌────▼────┐         ┌────▼────┐      ┌────▼────┐     ┌────▼────┐
    │  MEDIA  │         │  FORGE  │      │ HERALD  │     │  SCOUT  │
    │  Claw   │         │  Claw   │      │  Claw   │     │  Claw   │
    │         │         │         │      │         │     │         │
    │ scan    │         │ art_gen │      │ trend   │     │ market  │
    │ classify│         │ compose │      │ draft   │     │ compete │
    │ dedup   │         │ metadata│      │ thread  │     │ alpha   │
    │ process │         │ ipfs    │      │ schedule│     │ report  │
    │ score   │         │ mint    │      │ post    │     │         │
    │ upload  │         │ list    │      │ engage  │     │         │
    │ social  │         │ rarity  │      │ analyze │     │         │
    │ notify  │         │ notify  │      │ notify  │     │         │
    └─────────┘         └─────────┘      └─────────┘     └─────────┘
      Railway             Railway          Railway         Railway
      Service 1           Service 2        Service 3       Service 4
```

## The Five Claws

### 1. ArcaneaClaw Media (exists)
**Profile:** `profiles/media.yaml`
**Purpose:** AI-powered media pipeline — scan, classify, score, upload
**Cadence:** Every 15 min
**APIs:** Gemini Vision, Supabase Storage, Vercel Blob

### 2. ArcaneaClaw Forge
**Profile:** `profiles/forge.yaml`
**Purpose:** NFT creation engine — generate art, compose traits, mint, list
**Cadence:** On-demand / triggered
**APIs:** ComfyUI/Replicate (art gen), Pinata (IPFS), Thirdweb/Crossmint (minting)

### 3. ArcaneaClaw Herald
**Profile:** `profiles/herald.yaml`
**Purpose:** PR & social engine — elegant shilling, thread crafting, engagement
**Cadence:** Every 30 min scan, event-driven posting
**APIs:** Twitter/X API, LinkedIn API, Discord webhooks, Gemini (content gen)

### 4. ArcaneaClaw Scribe
**Profile:** `profiles/scribe.yaml`
**Purpose:** Content engine — blogs, changelogs, newsletters, press releases
**Cadence:** Daily / on commit
**APIs:** Gemini (writing), GitHub API (changelog), Notion (publishing)

### 5. ArcaneaClaw Scout
**Profile:** `profiles/scout.yaml`
**Purpose:** Intelligence engine — market trends, competitor moves, alpha signals
**Cadence:** Every hour
**APIs:** Twitter/X search, Reddit, Google Trends, CoinGecko, OpenSea

## Shared Infrastructure

- **Engine:** Same daemon.py, supabase_client.py, health server
- **Database:** Shared Supabase with domain-specific tables
- **Registry:** All Claws register in agent_registry, heartbeat independently
- **Notifications:** Each Claw has its own notify skill → shared webhook channels
- **MCP:** Unified MCP server exposes tools for ALL Claws

## Deploy Pattern

```bash
# Each Claw is the same Docker image with a different CLAW_PROFILE env var
docker run -e CLAW_PROFILE=media  arcanea-claw
docker run -e CLAW_PROFILE=forge  arcanea-claw
docker run -e CLAW_PROFILE=herald arcanea-claw
docker run -e CLAW_PROFILE=scout  arcanea-claw
```

On Railway: 4 services from the same repo, differentiated by CLAW_PROFILE.
