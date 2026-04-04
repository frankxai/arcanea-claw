# ArcaneaClaw Fleet — Master Evolution Plan

> **Vision:** The Claw Fleet becomes the autonomous creative operations layer for every world in the Arcanea multiverse — and then for every creator on the internet.
>
> **Architect:** Starlight (from 2125, looking back at what worked)
> **Voice:** Lumina (the First Light, form-giver)

---

## Phase 0: PROVE IT WORKS (This Session)
**Status:** `in_progress`
**Goal:** One full pipeline run, scan → classify → score → upload, with real data in Supabase.

| Task | Status | Owner |
|------|--------|-------|
| Fix Gemini API key | `blocked` | Frank (30s at aistudio.google.com) |
| Run full Media Claw pipeline | `blocked` | Depends on Gemini key |
| Verify classified assets in Supabase | `pending` | |
| Verify scored assets with TASTE tiers | `pending` | |
| Verify uploads to arcanea-gallery bucket | `pending` | |
| Verify social_queue drafts generated | `pending` | |
| Screenshot /claw/dashboard with live data | `pending` | |

**Exit Criteria:** 9 guardian images classified, scored, tier-assigned, at least 1 uploaded.

---

## Phase 1: PRODUCTION DEPLOY (Week 1)
**Status:** `pending`
**Goal:** Media Claw running 24/7 on Railway, processing real art.

| Task | Status | Notes |
|------|--------|-------|
| Deploy to Railway via button | `pending` | 3 env vars + /data volume |
| Verify Railway health checks pass | `pending` | /health endpoint |
| Mount real source directory | `pending` | Google Drive or upload |
| Monitor first 24h of autonomous runs | `pending` | |
| Set up Discord webhook notifications | `pending` | |
| Connect /claw/dashboard to production data | `pending` | |
| Deploy dashboard to Vercel (arcanea.ai) | `pending` | |

**Exit Criteria:** Media Claw runs autonomously for 24h, processes at least 20 images, sends Discord notifications.

**Architecture Decision — ADR-001: Railway vs Fly vs Render**
- Railway: best Docker support, persistent volumes, one-click deploy, good free tier
- Decision: Railway for v1. Revisit at scale.

---

## Phase 2: HERALD GOES LIVE (Week 2)
**Status:** `pending`
**Goal:** Herald Claw posting real content to real platforms.

| Task | Status | Notes |
|------|--------|-------|
| Get Twitter/X API v2 credentials | `pending` | Developer portal |
| Fix Twitter auth (OAuth 1.0a for posting) | `pending` | Current code uses bearer — wrong for writes |
| Get Discord bot token for Herald | `pending` | |
| Deploy Herald Claw to Railway | `pending` | Separate service, same image |
| First real tweet from Herald | `pending` | The milestone moment |
| First real Discord announcement | `pending` | |
| Verify cross-claw: Media hero → Herald announces | `pending` | Event pipeline test |
| Set up content approval flow | `pending` | Don't auto-post without review |

**Exit Criteria:** Herald posts 1 real tweet, 1 Discord message, triggered by Media Claw event.

**Architecture Decision — ADR-002: Auto-post vs Approval Queue**
- V1: All Herald drafts go to social_queue with status 'draft'
- Human approves → status 'approved' → Herald posts on next cycle
- V2: High-confidence posts can auto-approve (TASTE score 90+ for media announcements)
- Decision: Manual approval for v1. Trust must be earned.

---

## Phase 3: MAESTRO ORCHESTRATOR (Week 3)
**Status:** `pending`
**Goal:** Cross-claw intelligence — claws trigger each other based on business strategies.

| Task | Status | Notes |
|------|--------|-------|
| Design Maestro strategy schema | `pending` | YAML-defined workflows |
| Build Maestro as 6th profile | `pending` | profiles/maestro.yaml |
| Strategy: "Gallery Refresh" | `pending` | Media → Herald showcase |
| Strategy: "Build Log" | `pending` | Scribe changelog → Herald thread |
| Strategy: "Alpha Response" | `pending` | Scout signal → Herald draft |
| Deploy Maestro to Railway | `pending` | Always-on, event-driven |
| Dashboard: strategy execution view | `pending` | Show active strategies |

**Architecture Decision — ADR-003: Maestro Implementation**
- NOT a separate daemon — runs as an event consumer inside any claw
- Strategies are YAML files loaded at startup
- Each strategy defines: trigger_event → skill_sequence → success_criteria
- Maestro evaluates events against all strategies and dispatches

```yaml
# strategies/gallery-refresh.yaml
name: Gallery Refresh
trigger:
  event: media.hero_uploaded
  conditions:
    hero_count: ">= 3"  # batch announcements
actions:
  - claw: herald
    skill: herald_content_draft
    params: { topic: "New gallery additions" }
  - claw: herald
    skill: herald_schedule
    params: { platform: "twitter" }
success: social_queue has new entries
```

---

## Phase 4: FORGE GOES LIVE (Week 4)
**Status:** `pending`
**Goal:** Mint a real NFT collection on Base.

| Task | Status | Notes |
|------|--------|-------|
| Choose art provider: ComfyUI vs Replicate | `pending` | Replicate for v1 (no GPU needed) |
| Get Replicate API token | `pending` | |
| Get Pinata JWT for IPFS | `pending` | |
| Deploy Thirdweb contract on Base Sepolia | `pending` | Testnet first |
| Run Forge: generate 10 test NFTs | `pending` | |
| Verify IPFS pins on Pinata gateway | `pending` | |
| Mint 10 NFTs on Base Sepolia | `pending` | |
| Verify on OpenSea testnet | `pending` | |
| Cross-claw: Forge mint → Herald announce | `pending` | |
| Mainnet deployment decision | `pending` | |

**Architecture Decision — ADR-004: NFT Chain Selection**
- Base: low gas, Coinbase distribution, growing NFT ecosystem
- Abstract: new chain with creator focus, but small
- Decision: Base for v1. Multi-chain in v3.

---

## Phase 5: SCOUT + SCRIBE ACTIVATION (Week 5)
**Status:** `pending`
**Goal:** Intelligence and content running autonomously.

| Task | Status | Notes |
|------|--------|-------|
| Deploy Scout to Railway | `pending` | 1h cycle |
| Verify GitHub trending scan | `pending` | No auth needed |
| Verify Reddit scan | `pending` | Public API, rate limited |
| Deploy Scribe to Railway | `pending` | Daily cycle |
| Get GitHub token for commit scanning | `pending` | |
| First auto-generated changelog | `pending` | |
| First intelligence report in Discord | `pending` | |
| Cross-claw: Scout alpha → Herald response | `pending` | |
| Cross-claw: Scribe blog → Herald thread | `pending` | |

---

## Phase 6: CLAW SDK (Month 2)
**Status:** `planned`
**Goal:** Anyone can build a Claw skill.

| Task | Status | Notes |
|------|--------|-------|
| Define skill specification format | `pending` | skill.yaml + skill.py + tests/ |
| Build `arcanea-claw skill create` CLI command | `pending` | Scaffolding |
| Build `arcanea-claw skill test` command | `pending` | Local harness |
| Build `arcanea-claw skill publish` command | `pending` | Upload to store |
| Write SDK documentation | `pending` | |
| Publish @arcanea/claw-sdk to npm/pip | `pending` | |
| First community skill submission | `pending` | The milestone |

**Architecture Decision — ADR-005: Skill Format**
```
skills/my-custom-skill/
├── skill.yaml         # Metadata: name, version, author, pricing, config schema
├── skill.py           # The run(config, supabase, gemini_model?) function
├── requirements.txt   # Python dependencies (sandboxed)
├── tests/
│   └── test_skill.py  # Must pass before publish
└── README.md          # Marketplace listing content
```

---

## Phase 7: CLAW STORE (Month 2-3)
**Status:** `planned`
**Goal:** Marketplace for creative pipeline skills on arcanea.ai.

| Task | Status | Notes |
|------|--------|-------|
| Design store UI on arcanea.ai/claw/store | `pending` | |
| Build skill submission API | `pending` | |
| Build skill review/approval flow | `pending` | |
| Implement one-click install | `pending` | Adds skill to profile |
| Payment integration (Stripe) | `pending` | 70/30 creator split |
| Launch with 10 first-party skills | `pending` | Style packs, voice templates |
| Open to community submissions | `pending` | |

**Architecture Decision — ADR-006: Store vs ClawHub**
- We DO publish to OpenClaw's ClawHub for distribution (347K users)
- We ALSO have our own store for creative-specific skills
- Our store is focused: style packs, trait generators, voice templates
- ClawHub gets generic wrappers of our skills
- Decision: Dual-publish. Own store for revenue. ClawHub for reach.

---

## Phase 8: MULTI-WORLD (Month 3-4)
**Status:** `planned`
**Goal:** Every World in the Arcanea multiverse gets its own Claw Fleet.

| Task | Status | Notes |
|------|--------|-------|
| World-scoped config: each world defines its own classification | `pending` | |
| World-scoped TASTE scoring: different aesthetics per world | `pending` | |
| World-scoped Herald voice: each world has its own social voice | `pending` | |
| World-scoped Forge traits: each world's NFT collection | `pending` | |
| Hosted Claws: spin up a fleet for a new world in one click | `pending` | |
| Pricing: free tier (1 claw) + pro ($19/mo, all 5) | `pending` | |

---

## Success Metrics

| Metric | Phase 0 | Phase 2 | Phase 5 | Phase 8 |
|--------|---------|---------|---------|---------|
| Assets processed | 9 | 100+ | 500+ | 5,000+ |
| Social posts published | 0 | 10+ | 100+ | 1,000+ |
| NFTs minted | 0 | 0 | 10+ | 1,111+ |
| Claws deployed | 1 local | 2 Railway | 5 Railway | 50+ hosted |
| Community skills | 0 | 0 | 0 | 20+ |
| Revenue | $0 | $0 | $0 | $500+/mo |

---

## Errors Encountered

| Error | When | Resolution |
|-------|------|------------|
| Unicode box chars crash on Windows cp1252 | Phase 0 | Replaced with ASCII, added utf-8 reconfigure |
| Heartbeat used 'metadata' column (doesn't exist) | Phase 0 | Changed to 'config' column |
| Gemini API key expired | Phase 0 | BLOCKED — need fresh key from Frank |
| google.generativeai deprecated | Phase 0 | FutureWarning — migrate to google.genai later |
| 4 pipeline tests failed (mock import) | Phase 0 | Fixed mock to pass through non-skill imports |

---

## Key Architecture Principles (Starlight Architect)

1. **One image, many personalities** — CLAW_PROFILE is the only differentiator
2. **Skills are the unit of composition** — everything is a skill with run()
3. **Events are the integration layer** — claws don't call each other, they emit events
4. **Supabase is the shared brain** — no message queues, no Redis, just PostgreSQL
5. **Resilience is built-in** — circuit breakers and rate limiters at engine level, not per-skill
6. **Config over code** — strategies, skill chains, and thresholds are all YAML
7. **Dual-publish** — own store for revenue, ClawHub for reach
8. **World-scoped** — everything is parameterized by world_id for multiverse support
