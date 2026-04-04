# ArcaneaClaw Fleet — Findings & Discoveries

## Architecture Findings

### F-001: Daemon-Skill Interface Was Broken (RESOLVED)
- **Discovery:** daemon.py called `await mod.run(config)` but all skills expected `run(config, supabase, gemini_model)`
- **Resolution:** inspect.signature dynamic kwarg injection + run_in_executor for sync skills
- **Impact:** Would have crashed every skill call. Caught before production.

### F-002: Supabase Schema Mismatch (RESOLVED)
- **Discovery:** Multiple mismatches between Python code and SQL schema:
  - `register_agent()` missing required `agent_type` field
  - `heartbeat()` writing to `metadata` column (doesn't exist, it's `config`)
  - `social_prep` inserting columns that don't exist in `social_queue`
  - `media_upload` using `uploaded` status not in CHECK constraint
- **Resolution:** Fixed all four. Added schema-aware column mapping.
- **Lesson:** Always diff Python code against SQL migration BEFORE deploying.

### F-003: Cross-Claw Events Need No Infrastructure
- **Discovery:** Considered Redis/RabbitMQ for event pipeline. Realized Supabase polling is sufficient at our scale.
- **Decision:** Simple `claw_events` table with status lifecycle (pending → processing → completed/failed).
- **Trade-off:** Higher latency (30s poll) but zero infrastructure cost. At 10K events/day we'd need real queues.

### F-004: Windows Signal Handling Requires Fallback
- **Discovery:** `loop.add_signal_handler()` raises `NotImplementedError` on Windows.
- **Resolution:** Try/except with `signal.signal()` fallback for Windows development.

### F-005: Python 3.13 Compatible
- **Discovery:** All code runs clean on Python 3.13.7. No compatibility issues.
- **Note:** `google.generativeai` package is deprecated — migrate to `google.genai` before it breaks.

## Strategic Findings

### F-006: OpenClaw Ecosystem Analysis
- **OpenClaw:** 347K stars, extremely active (commits daily), massive ecosystem
- **ClawHub:** 5,400+ skills, community-maintained
- **NanoClaw:** Lightweight alternative (Anthropic Agent SDK based)
- **Frank's fork:** `arcanea-openclaw` — 18K commits behind, stale
- **Key insight:** Our skill format is DIFFERENT from OpenClaw's. We're a pipeline engine, not an assistant. Dual-publish strategy makes sense.

### F-007: The Gemini Dependency
- **Finding:** 3 of 8 media skills, ALL herald content skills, and ALL scout sentiment skills depend on Gemini.
- **Risk:** Single provider dependency. Key expiration = 60% of fleet disabled.
- **Recommendation:** Abstract LLM calls behind a provider interface. Support Gemini, Claude, local models.
- **Priority:** Phase 3 (after proving the pipeline works).

### F-008: Railway Deployment Ready
- **Finding:** Dockerfile, railway.json, docker-compose.yml all production-ready.
- **Finding:** Railway supports multiple services from one repo (one per claw).
- **Finding:** Persistent volumes mount at `/data` for source/staging/processed.
- **Cost estimate:** ~$5/mo per claw on Railway (Starter plan).

### F-009: Storage Tier Architecture
- **Hero (80+):** Vercel Blob — fast CDN, expensive per GB
- **Gallery (60-79):** Supabase Storage — free tier generous, slower
- **Thumbnail (40-59):** Supabase Storage — small files, high volume
- **Reject (<40):** Not uploaded, stays local
- **Both buckets created:** arcanea-gallery + thumbnails (public, RLS configured)

### F-010: Claw Store Revenue Model
- **Style Packs:** $4.99 (classification + scoring rules per aesthetic)
- **Voice Templates:** $2.99 (Herald personality configs)
- **Trait Generators:** $9.99 (Forge composition rules)
- **Intel Modules:** $4.99/mo (Scout data sources)
- **Split:** 70% creator / 30% platform
- **Note:** Don't build the store until Phase 6. Need at least 5 production claws first.

## Technical Debt

| Item | Severity | Phase to Fix |
|------|----------|-------------|
| `google.generativeai` deprecated | Medium | Phase 3 |
| Twitter OAuth 1.0a not implemented (using bearer) | High | Phase 2 |
| ComfyUI API format doesn't match real API | Medium | Phase 4 |
| No LLM provider abstraction | Medium | Phase 3 |
| No type hints on skill interfaces | Low | Phase 6 (SDK) |
| Dead helper functions in supabase_client.py | Low | Anytime |
| No integration tests (only unit) | Medium | Phase 1 |

## OpenClaw Ecosystem Intelligence (2026-04-05)

### F-011: ClawHavoc Security Crisis
- **Discovery:** Jan 2026, 800+ malicious skills on ClawHub (~20% of registry). Delivered AMOS malware.
- **Impact on us:** Publishing verified, high-quality skills from @arcanea is a competitive advantage. Post-crisis trust is low.
- **Action:** Added security metadata to SKILL.md and clawhub.json. Container-first, permissions declared.

### F-012: ClawHub Compatibility Gap
- **Discovery:** Our SKILL.md was missing the `metadata.openclaw` block (requires.env, requires.bins, primaryEnv).
- **Resolution:** Added full ClawHub-compatible frontmatter. Ready to submit 4 skillpacks.
- **Ecosystem size:** 13,729 skills on ClawHub, 250K+ stars on OpenClaw.

### F-013: We're Already Ahead
- **MCP-native:** Most ClawHub skills are SKILL.md only (prompt instructions). We ship an actual MCP server with 11 tools.
- **Pipeline architecture:** Nobody in ClawHub has a multi-skill sequential pipeline. All are single-step tools.
- **TASTE scoring:** 5-dimension aesthetic evaluation is unique in the entire ecosystem.
- **Fleet coordination:** 5 coordinated claws with cross-claw events. OpenClaw runs one agent. We run five.

### F-014: NanoClaw Container Security Model
- **Discovery:** NanoClaw (Anthropic Agent SDK based) uses container-level isolation for every session.
- **Our alignment:** We already run in Docker/Podman with non-root user. Architecturally matched.

### F-015: Moltbook Acquired by Meta
- **Discovery:** "Reddit for AI agents." Meta acquired March 2026. Transitioning to walled garden.
- **Action:** Low priority as a Herald platform. Monitor API stability post-acquisition.

### F-016: Security Audit Results (5 CRITICAL fixed)
- CRIT-01: /trigger now authenticated (CLAW_API_SECRET bearer)
- CRIT-03: Skill allowlist enforced (33 known skills only)
- CRIT-04: File path validation added
- CRIT-05: media_scan followlinks=False + resolved paths
- HIGH-01: Inbound rate limiting (30/60s per IP)
- HIGH-03: Secret fallback to YAML removed
- HIGH-04: Pillow MAX_IMAGE_PIXELS=50M
- MED-01: Error sanitization on HTTP responses
- MED-04: Dependencies pinned to exact versions
- MED-06: Log secret redaction filter
