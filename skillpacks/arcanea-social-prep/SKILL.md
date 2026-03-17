---
name: arcanea-social-prep
version: "1.0.0"
description: "Auto-generate platform-optimized image variants and AI-written captions for Instagram, LinkedIn, X, YouTube, and TikTok from any source image."
author: "frankxai"
homepage: "https://arcanea.ai"
repository: "https://github.com/frankxai/arcanea-claw"
license: "MIT"
tags: [social-media, content-creation, image-variants, ai-captions, marketing, automation, instagram, linkedin, twitter]
trigger: pipeline
depends_on:
  - media-upload
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
  - name: platforms
    type: list[str]
    description: Target social platforms
    default: [instagram, linkedin, x, youtube, tiktok]
  - name: model
    type: str
    description: Gemini model for caption generation
    default: "gemini-2.0-flash"
  - name: tone
    type: str
    description: Voice/tone for generated captions
    default: "creative"
  - name: hashtag_count
    type: int
    description: Maximum hashtags per platform
    default: 15
outputs:
  - name: posts_queued
    type: int
    description: Number of social queue entries created
  - name: platforms_covered
    type: list[str]
    description: Platforms for which posts were generated
tables:
  - social_queue (INSERT with status='draft')
  - asset_metadata (READ hero-tier assets)
---

# Arcanea Social Prep

Automatically generate platform-optimized image variants and AI-written captions for every major social platform. Drop in a hero image, get back ready-to-post content for Instagram, LinkedIn, X, YouTube, and TikTok.

## What It Does

For each hero-tier image, Social Prep creates:

| Platform | Image Variant | Aspect Ratio | Caption Style |
|----------|--------------|--------------|---------------|
| **Instagram** | Square crop | 1:1 (1080x1080) | Visual storytelling + hashtags (up to 30) |
| **LinkedIn** | Wide crop | 1.91:1 (1200x628) | Professional narrative, thought leadership tone |
| **X (Twitter)** | Wide crop | 16:9 (1200x675) | Punchy, under 280 chars, 3-5 hashtags |
| **YouTube** | Wide crop | 16:9 (1920x1080) | Thumbnail-optimized, title + description |
| **TikTok** | Portrait crop | 9:16 (1080x1920) | Trending hooks, casual voice, hashtag challenges |

Each variant is generated from the source image using intelligent cropping that preserves the subject. Captions are written by Gemini with platform-specific voice, length, and hashtag strategies.

## Installation

### Via ClawHub

```bash
claw install arcanea-social-prep
```

### Via OpenClaw CLI

```bash
openclaw skill add arcanea-social-prep
```

### As Part of the Full Pipeline

```bash
claw install arcanea-media-pipeline
# social-prep is included as step 7 of 8
```

## Usage

### In a Pipeline

Runs automatically as step 7 of the media pipeline. Picks up uploaded hero-tier assets and generates social queue entries.

### Standalone

```python
from skills.social_prep import SocialPrep

prep = SocialPrep(model="gemini-2.0-flash")

posts = await prep.prepare(
    image_path="/path/to/hero-image.webp",
    platforms=["instagram", "linkedin", "x"],
    metadata={
        "title": "Dragon's Awakening",
        "tags": ["fire", "dragon", "fantasy"],
        "description": "A fire guardian rises from volcanic stone."
    }
)

for post in posts:
    print(f"[{post['platform']}] {post['caption'][:80]}...")
    print(f"  Variant: {post['variant_path']}")
    print(f"  Hashtags: {', '.join(post['hashtags'])}")
```

### CLI

```bash
# Prepare social posts for all hero-tier uploads
python -m skills.social_prep

# Prepare for a specific image
python -m skills.social_prep --file /path/to/image.webp --platforms instagram,x

# Preview captions without creating queue entries
python -m skills.social_prep --dry-run
```

## Configuration

### Basic

```yaml
social_prep:
  model: "gemini-2.0-flash"
  platforms: [instagram, linkedin, x, youtube, tiktok]
```

### Custom Voice

Control the tone of generated captions:

```yaml
social_prep:
  tone: "mythic-professional"
  brand_voice: |
    We are a creative world-building platform. Our voice is:
    - Elevated but accessible
    - Mythic but grounded
    - Inspiring without being preachy
    Avoid: corporate jargon, clickbait, emoji spam
```

### Platform-Specific Overrides

```yaml
social_prep:
  platforms:
    instagram:
      enabled: true
      max_hashtags: 25
      caption_style: "storytelling"
      include_cta: true
      cta_text: "Link in bio"
    linkedin:
      enabled: true
      max_hashtags: 5
      caption_style: "thought-leadership"
      include_cta: true
      cta_text: "Read more at arcanea.ai"
    x:
      enabled: true
      max_hashtags: 3
      max_length: 270
    youtube:
      enabled: true
      generate_title: true
      generate_description: true
    tiktok:
      enabled: true
      max_hashtags: 10
      caption_style: "trending-hook"
```

### Hashtag Strategy

```yaml
social_prep:
  hashtags:
    # Always include these
    pinned: ["#arcanea", "#worldbuilding"]
    # Never use these
    blocked: ["#followforfollow", "#like4like"]
    # Generate from image metadata
    from_metadata: true
    # Generate trending suggestions
    suggest_trending: true
```

## Caption Generation

The AI caption generator uses the image itself plus any available metadata to write platform-appropriate copy. The prompt chain:

1. **Image analysis**: Gemini Vision describes the image content, mood, colors, and subjects
2. **Metadata integration**: Tags, categories, and descriptions from earlier pipeline steps are incorporated
3. **Platform formatting**: Each platform gets a separately generated caption tuned for its audience, length limits, and conventions
4. **Hashtag generation**: Relevant hashtags are generated per platform, respecting count limits and blocked terms

### Example Output

**Source image**: A photorealistic fantasy warrior surrounded by flame

**Instagram**:
> The fire burns not to destroy -- it burns to reveal what was always beneath the surface.
>
> When Draconia opens the Fire Gate, she doesn't ask if you're ready. She asks if you're willing.
>
> #arcanea #worldbuilding #fantasyart #firelement #aiart #characterdesign #mythology #creativecoding #digitalart #conceptart

**LinkedIn**:
> What does quality curation look like when you generate 200 images a day?
>
> We built an AI-powered scoring system (TASTE) that evaluates every image across 5 dimensions before it ever reaches an audience. This piece scored 92/100 -- hero tier.
>
> The creative bottleneck isn't generation anymore. It's selection.
>
> #CreativeAI #ContentStrategy #WorldBuilding

**X**:
> The Fire Gate opens. 92/100 TASTE score. Hero tier.
>
> When your pipeline scores better than your team, you let it curate.
>
> #arcanea #aiart #fantasy

## Social Queue

Generated posts are stored in the `social_queue` table with `status='draft'`. From there, you can:

- **Review and approve** via the Command Center dashboard
- **Schedule** for specific times
- **Auto-publish** via connected platform APIs
- **Edit** captions before publishing

Queue entry format:

```json
{
  "asset_id": "uuid",
  "platform": "instagram",
  "caption": "The fire burns not to destroy...",
  "hashtags": ["#arcanea", "#fantasyart", "..."],
  "variant_url": "https://cdn.arcanea.ai/social/instagram/image-1080x1080.webp",
  "variant_dimensions": [1080, 1080],
  "status": "draft",
  "created_at": "2026-03-17T14:30:00Z",
  "scheduled_at": null
}
```

## Supported Image Formats

Input: JPEG, PNG, WebP, GIF (first frame), TIFF, BMP
Output: WebP (all variants)

## License

MIT -- use it, fork it, build on it.
