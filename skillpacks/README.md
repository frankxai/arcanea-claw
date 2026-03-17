# ArcaneaClaw Skill Packs

Publishable skill packs for [ClawHub](https://clawhub.dev) (OpenClaw marketplace) and standalone installation. Each pack is a self-contained, documented skill or bundle that can be installed with a single command.

## Available Skill Packs

### arcanea-media-pipeline

**The full pipeline.** All 8 media processing skills bundled as one installable package.

```bash
claw install arcanea-media-pipeline
```

Drop images anywhere. The pipeline scans, classifies (Gemini Vision), deduplicates, processes (WebP + 6 variants), scores (TASTE 0-100), uploads to tiered storage, generates social posts, and notifies you.

**Skills included**: media-scan, media-classify, media-process, media-dedup, taste-score, media-upload, social-prep, notify

[Full documentation](./arcanea-media-pipeline/SKILL.md)

---

### arcanea-taste-scorer

**AI-powered aesthetic scoring.** The unique differentiator -- a 5-dimension quality evaluation system.

```bash
claw install arcanea-taste-scorer
```

Scores every image on Technical Fit, Aesthetic Compliance, Story Alignment, Transcendence (emotional impact), and Exclusivity (uniqueness). Composite score 0-100 with automatic tier assignment (hero / gallery / archive / reject).

Configurable dimensions -- replace the defaults with your own evaluation criteria.

[Full documentation](./arcanea-taste-scorer/SKILL.md)

---

### arcanea-social-prep

**Social media content factory.** Platform-optimized variants and AI-written captions.

```bash
claw install arcanea-social-prep
```

From one source image, generates ready-to-post content for Instagram (1:1), LinkedIn (1.91:1), X (16:9), YouTube (16:9), and TikTok (9:16). Each platform gets its own caption style, hashtag strategy, and voice.

[Full documentation](./arcanea-social-prep/SKILL.md)

---

### arcanea-command-center

**Visual dashboard.** The human-in-the-loop control surface for autonomous pipelines.

```bash
claw install arcanea-command-center
```

Web-based dashboard with an approval inbox, live agent monitoring, social post scheduling, and a publish pipeline. Built on Next.js + Supabase Realtime for live updates.

[Full documentation](./arcanea-command-center/SKILL.md)

---

## Installation Methods

### ClawHub (recommended)

```bash
# Install the ClawHub CLI
npm install -g @openclaw/cli

# Install any skill pack
claw install arcanea-media-pipeline
```

### OpenClaw CLI

```bash
openclaw skill add arcanea-taste-scorer
```

### npm

```bash
npm install @arcanea/claw
```

### Standalone (Git)

```bash
git clone https://github.com/frankxai/arcanea-claw.git
cd arcanea-claw
pip install -r requirements.txt  # Python skills
npm install                       # Node.js skills + Command Center
```

### Docker

```bash
git clone https://github.com/frankxai/arcanea-claw.git
cd arcanea-claw
docker compose up -d
```

## Skill Pack Structure

Each skill pack follows the OpenClaw SKILL.md specification:

```
skillpacks/
  arcanea-media-pipeline/
    SKILL.md          # Manifest + documentation (YAML frontmatter + Markdown)
  arcanea-taste-scorer/
    SKILL.md
  arcanea-social-prep/
    SKILL.md
  arcanea-command-center/
    SKILL.md
```

The `SKILL.md` frontmatter contains:
- **name, version, description** -- package identity
- **dependencies** -- runtime requirements (Python packages, Node packages)
- **env** -- required and optional environment variables
- **inputs/outputs** -- typed skill interface
- **tags** -- for ClawHub discoverability
- **trigger, depends_on** -- pipeline orchestration metadata

## Relationship to Individual Skills

The `skills/` directory at the repo root contains the 8 individual pipeline skills with their own `SKILL.md` files. These are the atomic building blocks.

The `skillpacks/` directory contains composite, publishable packages that bundle skills together or package them for standalone use with full documentation, configuration guides, and usage examples.

```
arcanea-claw/
  skills/                  # Atomic skills (internal)
    media-scan/SKILL.md
    media-classify/SKILL.md
    media-process/SKILL.md
    media-dedup/SKILL.md
    taste-score/SKILL.md
    media-upload/SKILL.md
    social-prep/SKILL.md
    notify/SKILL.md
  skillpacks/              # Publishable packages (external)
    arcanea-media-pipeline/SKILL.md   # Bundles all 8
    arcanea-taste-scorer/SKILL.md     # Standalone scorer
    arcanea-social-prep/SKILL.md      # Standalone social
    arcanea-command-center/SKILL.md   # Dashboard UI
```

## Environment Variables

All skill packs share a common set of environment variables:

| Variable | Required By | Description |
|----------|-------------|-------------|
| `GEMINI_API_KEY` | media-pipeline, taste-scorer, social-prep | Google Gemini API key |
| `SUPABASE_URL` | all | Supabase project URL |
| `SUPABASE_SERVICE_KEY` | media-pipeline, taste-scorer, social-prep | Supabase service role key |
| `SUPABASE_ANON_KEY` | command-center | Supabase anonymous key |
| `VERCEL_BLOB_TOKEN` | media-pipeline | Vercel Blob storage token (for hero-tier CDN upload) |
| `NOTIFY_WEBHOOK_URL` | media-pipeline | Webhook URL for pipeline notifications |

## License

MIT
