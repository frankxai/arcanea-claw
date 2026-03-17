---
name: notify
description: Send pipeline run summary via configured webhook channels
trigger: pipeline
depends_on:
  - social-prep
sandbox: true
inputs:
  - name: channels
    type: list[dict]
    description: Notification channel configs (type + url)
    source: config.yaml#arcanea_claw.notify.channels
  - name: pipeline_stats
    type: dict
    description: Aggregated stats from all preceding pipeline steps
    source: runtime
outputs:
  - name: notifications_sent
    type: int
    description: Number of notifications successfully delivered
dependencies:
  python:
    - requests
    - supabase
tables:
  - agent_registry (UPDATE items_processed)
---

# notify

Collects stats from all pipeline steps and sends a summary notification:

```
ArcaneaClaw Pipeline Complete:
- {n} new files scanned
- {n} classified (Guardian assigned)
- {n} processed (WebP + variants)
- {n} scored ({hero_count} hero-tier!)
- {n} social posts drafted
Next run in 15 minutes.
```

Supports Discord webhooks, Slack incoming webhooks, and generic HTTP POST.
Also updates `agent_registry` with the total `items_processed` count.

## Pipeline Position

**Step 8 of 8** — final step, summarizes the entire pipeline run.
