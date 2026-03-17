---
name: arcanea-taste-scorer
version: "1.0.0"
description: "AI-powered aesthetic quality scoring for images. 5-dimension evaluation: Canon Alignment, Design Compliance, Emotional Impact, Technical Fit, Uniqueness. Scores 0-100 with automatic tier assignment."
author: "frankxai"
homepage: "https://arcanea.ai"
repository: "https://github.com/frankxai/arcanea-claw"
license: "MIT"
tags: [quality-scoring, aesthetic-evaluation, ai-vision, curation, image-quality, taste, creative]
trigger: pipeline
depends_on:
  - media-process
sandbox: true
dependencies:
  python: ">=3.11"
  packages: [google-generativeai, supabase, Pillow]
env:
  required:
    - GEMINI_API_KEY
    - SUPABASE_URL
    - SUPABASE_SERVICE_KEY
inputs:
  - name: batch_size
    type: int
    description: Max images to score per cycle
    default: 15
  - name: model
    type: str
    description: Gemini model for scoring
    default: "gemini-2.0-flash"
  - name: dimensions
    type: list
    description: Scoring dimensions and their weights
    default: [canon_alignment, design_compliance, emotional_impact, technical_fit, uniqueness]
outputs:
  - name: scored_count
    type: int
    description: Number of assets scored this cycle
  - name: hero_count
    type: int
    description: Number of assets that achieved hero tier (80+)
  - name: average_score
    type: float
    description: Average TASTE score across the batch
  - name: tier_distribution
    type: dict
    description: Count of assets in each quality tier
tables:
  - asset_metadata (UPDATE quality_score, quality_tier, quality_dimensions, status)
---

# Arcanea TASTE Scorer

AI-powered aesthetic quality scoring that separates hero-tier artwork from the noise. TASTE stands for the five evaluation dimensions that produce a composite 0-100 score.

## The Five Dimensions

Every image is evaluated on five axes, each scored 0-20:

| Dimension | Weight | What It Measures |
|-----------|--------|------------------|
| **T - Technical Fit** | 0-20 | Resolution, clarity, sharpness, web-readiness. Is this image technically sound? No artifacts, proper exposure, clean edges. |
| **A - Aesthetic / Design Compliance** | 0-20 | Composition, color palette, visual hierarchy, professionalism. Does it follow design principles? |
| **S - Story / Canon Alignment** | 0-20 | Does the image fit the world it belongs to? For fantasy projects: does it match the mythology, characters, and aesthetic canon? |
| **T - Transcendence / Emotional Impact** | 0-20 | Does it evoke feeling? Wonder, power, mystery, joy, awe. Does it make you stop scrolling? |
| **E - Exclusivity / Uniqueness** | 0-20 | Is this distinct from generic AI art? Does it have a recognizable signature, style, or perspective? |

**Composite Score** = sum of all five dimensions (0-100).

## Quality Tiers

| Score Range | Tier | Action |
|-------------|------|--------|
| 80-100 | **Hero** | Featured placement. Uploaded to CDN. Used for banners, social, marketing. |
| 60-79 | **Gallery** | Standard publication. Uploaded to storage. Browsable in galleries. |
| 40-59 | **Archive** | Thumbnails generated, but not actively published. Available on request. |
| 0-39 | **Reject** | Not published. Flagged for review or deletion. |

## Installation

### Via ClawHub

```bash
claw install arcanea-taste-scorer
```

### Via OpenClaw CLI

```bash
openclaw skill add arcanea-taste-scorer
```

### As Part of the Full Pipeline

```bash
claw install arcanea-media-pipeline
# taste-score is included as step 5 of 8
```

## Usage

### In a Pipeline

The scorer runs automatically as step 5 when part of the `arcanea-media-pipeline`. It picks up images with `status='processed'` and updates them with scores and tier assignments.

### Standalone Scoring

Score a single image programmatically:

```python
from skills.score import TasteScorer

scorer = TasteScorer(model="gemini-2.0-flash")

result = await scorer.score_image("/path/to/image.webp")

print(result)
# {
#   "score": 87,
#   "tier": "hero",
#   "dimensions": {
#     "technical_fit": 18,
#     "design_compliance": 17,
#     "emotional_impact": 19,
#     "canon_alignment": 16,
#     "uniqueness": 17
#   },
#   "reasoning": "Strong composition with dynamic lighting..."
# }
```

### Batch Scoring

```python
from skills.score import TasteScorer

scorer = TasteScorer(model="gemini-2.0-flash", batch_size=15)

results = await scorer.score_batch(
    query={"status": "processed", "quality_score": None},
    limit=15
)

print(f"Scored {results['scored_count']} images")
print(f"Heroes: {results['hero_count']}")
print(f"Average: {results['average_score']:.1f}")
```

### CLI

```bash
# Score all unscored processed images
python -m skills.score

# Score a specific file
python -m skills.score --file /path/to/image.webp

# Score with custom thresholds
python -m skills.score --hero-threshold 85 --gallery-threshold 65
```

## Configuration

### Basic

```yaml
taste_score:
  model: "gemini-2.0-flash"
  batch_size: 15
```

### Custom Thresholds

```yaml
upload:
  hero_threshold: 85    # Raise the bar for hero tier
  gallery_threshold: 65  # Raise the bar for gallery tier
```

### Custom Dimensions

Replace the default TASTE dimensions with your own evaluation criteria:

```yaml
taste_score:
  dimensions:
    - name: brand_alignment
      weight: 20
      prompt: "Does this image align with our brand guidelines?"
    - name: accessibility
      weight: 20
      prompt: "Is this image accessible (contrast, alt-text potential)?"
    - name: engagement_potential
      weight: 20
      prompt: "Would this stop someone scrolling on social media?"
    - name: technical_quality
      weight: 20
      prompt: "Is this technically sound for web display?"
    - name: originality
      weight: 20
      prompt: "Is this distinct from stock photography and generic AI output?"
```

### Canon Reference

For world-building projects, provide a canon reference file and the scorer will evaluate alignment against your specific universe:

```yaml
taste_score:
  canon:
    reference: "/path/to/your/CANON.md"
    # The scorer reads this file and uses it as context
    # for the Canon Alignment dimension
```

## How It Works

1. Queries the database for images with `status='processed'` and no quality score
2. Loads each image and sends it to Gemini Vision with a structured evaluation prompt
3. The prompt asks for JSON output with scores (0-20) for each dimension plus reasoning
4. Parses the response, computes the composite score, assigns a tier
5. Updates the database row with `quality_score`, `quality_tier`, `quality_dimensions` (JSON), and `status='scored'`

The Gemini prompt is engineered to produce consistent, reproducible scores. It uses few-shot examples calibrated against human-rated reference images.

## API Response Format

```json
{
  "asset_id": "uuid-here",
  "score": 87,
  "tier": "hero",
  "dimensions": {
    "technical_fit": 18,
    "design_compliance": 17,
    "emotional_impact": 19,
    "canon_alignment": 16,
    "uniqueness": 17
  },
  "reasoning": "Strong composition with dynamic lighting that evokes a sense of divine power. The color palette aligns with the Fire element canon. Minor deduction on canon alignment due to ambiguous character identity. Highly unique rendering style that distinguishes it from standard diffusion output.",
  "scored_at": "2026-03-17T14:30:00Z"
}
```

## Performance

- **Speed**: ~2 seconds per image with Gemini Flash
- **Cost**: Gemini Flash free tier supports ~1,500 images/day (RPM limits)
- **Batch size**: Default 15 per cycle, configurable up to 50
- **Consistency**: Scores vary +/- 3 points across runs for the same image

## Use Cases

- **Content curation**: Automatically surface your best work from thousands of generated images
- **Quality gates**: Block low-quality images from reaching production
- **Portfolio building**: Let the scorer rank your entire archive
- **A/B testing**: Compare aesthetic scores across different generation prompts or models
- **Social scheduling**: Only queue hero-tier images for social media

## License

MIT -- use it, fork it, build on it.
