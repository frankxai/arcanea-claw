"""scribe-changelog-scan skill: Scan Git repos for recent commits and generate changelog material.

Pulls commit history from configured repos, groups by type (feat/fix/docs),
and stores structured changelog entries.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

import requests

logger = logging.getLogger("arcanea-claw.scribe-changelog-scan")


def _fetch_recent_commits(repo: str, since: str = "24h", token: str = "") -> list[dict]:
    """Fetch recent commits from GitHub API."""
    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        resp = requests.get(
            f"https://api.github.com/repos/{repo}/commits",
            headers=headers,
            params={"per_page": 50},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        logger.warning("Failed to fetch commits from %s: %s", repo, exc)
        return []


def _categorize_commit(message: str) -> str:
    """Categorize commit by conventional commit prefix."""
    msg = message.lower().strip()
    if msg.startswith("feat"):
        return "feature"
    elif msg.startswith("fix"):
        return "fix"
    elif msg.startswith("docs"):
        return "docs"
    elif msg.startswith("refactor"):
        return "refactor"
    elif msg.startswith("test"):
        return "test"
    elif msg.startswith("chore"):
        return "chore"
    return "other"


def run(config: dict[str, Any], supabase: Any) -> dict[str, Any]:
    """Scan repos for recent commits and build changelog entries."""
    sources = config.get("sources", {})
    gh_cfg = sources.get("github", {})
    repos = gh_cfg.get("repos", [])
    token = os.environ.get("GITHUB_TOKEN", "")

    entries = []

    for repo in repos:
        commits = _fetch_recent_commits(repo, token=token)

        for commit in commits[:20]:
            msg = commit.get("commit", {}).get("message", "").split("\n")[0]
            category = _categorize_commit(msg)
            author = commit.get("commit", {}).get("author", {}).get("name", "")
            sha = commit.get("sha", "")[:8]

            entries.append({
                "repo": repo,
                "sha": sha,
                "message": msg,
                "category": category,
                "author": author,
                "date": commit.get("commit", {}).get("author", {}).get("date", ""),
            })

    logger.info("Scanned %d commits across %d repos", len(entries), len(repos))
    return {"commits_scanned": len(entries), "changelog_entries": entries}
