#!/usr/bin/env node

/**
 * ArcaneaClaw MCP Server
 *
 * Gives Claude Code native tool access to the ArcaneaClaw media pipeline.
 * Reads/writes manifest.json directly (local-first, no Supabase required).
 *
 * Tools: claw_status, claw_scan, claw_inbox, claw_approve, claw_reject,
 *        claw_stats, claw_process, claw_heroes, claw_classify, claw_pipeline
 */

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import * as fs from "node:fs";
import * as path from "node:path";
import { execSync, exec } from "node:child_process";

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------

const CLAW_DIR = process.env.CLAW_DIR || path.resolve(process.cwd());
const MANIFEST_PATH =
  process.env.MANIFEST_PATH || path.join(CLAW_DIR, "manifest.json");
const PID_FILE = path.join(CLAW_DIR, "daemon.pid");
const CONFIG_PATH = path.join(CLAW_DIR, "config.yaml");

// ---------------------------------------------------------------------------
// Runtime detection — OpenClaw vs Claude Code vs standalone
// ---------------------------------------------------------------------------

type ClawRuntime = "openclaw" | "nanoclaw" | "claude-code" | "standalone";

function detectRuntime(): ClawRuntime {
  if (process.env.OPENCLAW_SKILL_DIR || process.env.OPENCLAW_VERSION) {
    return "openclaw";
  }
  if (process.env.NANOCLAW_SKILL_DIR || process.env.NANOCLAW_VERSION) {
    return "nanoclaw";
  }
  if (process.env.CLAUDE_CODE || process.env.MCP_PROXY) {
    return "claude-code";
  }
  // Heuristic: Claude Code pipes stdio with specific parent process patterns
  const parentEnv = process.env._ || "";
  if (parentEnv.includes("claude") || parentEnv.includes("mcp")) {
    return "claude-code";
  }
  return "standalone";
}

const CLAW_RUNTIME = detectRuntime();

// Guardians from canon
const GUARDIANS = [
  "Lyssandria",
  "Leyla",
  "Draconia",
  "Maylinn",
  "Alera",
  "Lyria",
  "Aiyami",
  "Elara",
  "Ino",
  "Shinkami",
] as const;

const ELEMENTS = ["Earth", "Water", "Fire", "Wind", "Void"] as const;

const TIERS = {
  hero: { min: 80, label: "Hero" },
  gallery: { min: 60, label: "Gallery" },
  archive: { min: 0, label: "Archive" },
} as const;

// ---------------------------------------------------------------------------
// Manifest types
// ---------------------------------------------------------------------------

interface ManifestAsset {
  id: string;
  file: string;
  path: string;
  status: string; // pending | approved | rejected | processed | uploaded
  guardian?: string;
  element?: string;
  taste_score?: number;
  tier?: string;
  width?: number;
  height?: number;
  size_bytes?: number;
  mime?: string;
  hash?: string;
  tags?: string[];
  classified_at?: string;
  processed_at?: string;
  uploaded_at?: string;
  created_at: string;
  updated_at: string;
}

interface Manifest {
  version: string;
  agent_id: string;
  last_scan_at?: string;
  last_pipeline_at?: string;
  assets: ManifestAsset[];
}

// ---------------------------------------------------------------------------
// Manifest I/O
// ---------------------------------------------------------------------------

function readManifest(): Manifest {
  if (!fs.existsSync(MANIFEST_PATH)) {
    const empty: Manifest = {
      version: "0.1.0",
      agent_id: "arcanea-claw-primary",
      assets: [],
    };
    writeManifest(empty);
    return empty;
  }
  const raw = fs.readFileSync(MANIFEST_PATH, "utf-8");
  return JSON.parse(raw) as Manifest;
}

function writeManifest(manifest: Manifest): void {
  fs.writeFileSync(MANIFEST_PATH, JSON.stringify(manifest, null, 2), "utf-8");
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function generateId(): string {
  return `claw_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
}

function isDaemonRunning(): { running: boolean; pid?: number } {
  if (!fs.existsSync(PID_FILE)) return { running: false };
  try {
    const pid = parseInt(fs.readFileSync(PID_FILE, "utf-8").trim(), 10);
    // Check if process exists (signal 0 = test only)
    process.kill(pid, 0);
    return { running: true, pid };
  } catch {
    return { running: false };
  }
}

function getExtensions(): string[] {
  return [".jpg", ".jpeg", ".png", ".webp", ".gif", ".mp4", ".mov", ".mp3", ".wav", ".flac"];
}

function getIgnorePatterns(): string[] {
  return [".", "__pycache__", "node_modules", ".git", ".next", "dist"];
}

function scanDirectory(dir: string, extensions: string[], ignore: string[]): string[] {
  const results: string[] = [];
  if (!fs.existsSync(dir)) return results;

  function walk(current: string): void {
    let entries: fs.Dirent[];
    try {
      entries = fs.readdirSync(current, { withFileTypes: true });
    } catch {
      return;
    }
    for (const entry of entries) {
      if (ignore.some((p) => entry.name.startsWith(p))) continue;
      const full = path.join(current, entry.name);
      if (entry.isDirectory()) {
        walk(full);
      } else if (entry.isFile()) {
        const ext = path.extname(entry.name).toLowerCase();
        if (extensions.includes(ext)) {
          results.push(full);
        }
      }
    }
  }
  walk(dir);
  return results;
}

/** Classify a file by filename/path heuristics */
function classifyByHeuristics(
  filePath: string
): { guardian?: string; element?: string; tags: string[] } {
  const lower = filePath.toLowerCase();
  const tags: string[] = [];
  let guardian: string | undefined;
  let element: string | undefined;

  // Guardian detection
  const guardianMap: Record<string, string> = {
    lyssandria: "Lyssandria",
    leyla: "Leyla",
    draconia: "Draconia",
    maylinn: "Maylinn",
    alera: "Alera",
    lyria: "Lyria",
    aiyami: "Aiyami",
    elara: "Elara",
    ino: "Ino",
    shinkami: "Shinkami",
    // Godbeast names map to guardian
    kaelith: "Lyssandria",
    veloura: "Leyla",
    draconis: "Draconia",
    laeylinn: "Maylinn",
    otome: "Alera",
    yumiko: "Lyria",
    sol: "Aiyami",
    vaelith: "Elara",
    kyuro: "Ino",
    source: "Shinkami",
  };

  for (const [key, value] of Object.entries(guardianMap)) {
    if (lower.includes(key)) {
      guardian = value;
      break;
    }
  }

  // Element detection
  const elementMap: Record<string, string> = {
    earth: "Earth",
    water: "Water",
    fire: "Fire",
    wind: "Wind",
    void: "Void",
    spirit: "Void",
    crystal: "Water",
    flame: "Fire",
    storm: "Wind",
    stone: "Earth",
    shadow: "Void",
    cosmic: "Void",
  };

  for (const [key, value] of Object.entries(elementMap)) {
    if (lower.includes(key)) {
      element = value;
      break;
    }
  }

  // Content type tags
  if (lower.includes("hero")) tags.push("hero");
  if (lower.includes("portrait")) tags.push("portrait");
  if (lower.includes("banner")) tags.push("banner");
  if (lower.includes("gallery")) tags.push("gallery");
  if (lower.includes("social")) tags.push("social");
  if (lower.includes("godbeast")) tags.push("godbeast");
  if (lower.includes("v3")) tags.push("v3");
  if (lower.includes("v2")) tags.push("v2");
  if (/guardian/i.test(lower)) tags.push("guardian");

  // Version detection
  const versionMatch = lower.match(/v(\d+)/);
  if (versionMatch) tags.push(`version-${versionMatch[1]}`);

  return { guardian, element, tags };
}

function execCommand(cmd: string, cwd?: string): string {
  try {
    return execSync(cmd, {
      cwd: cwd || CLAW_DIR,
      timeout: 60_000,
      encoding: "utf-8",
      stdio: ["pipe", "pipe", "pipe"],
    }).trim();
  } catch (err: any) {
    return `ERROR: ${err.message || err}`;
  }
}

// ---------------------------------------------------------------------------
// MCP Server
// ---------------------------------------------------------------------------

const server = new McpServer({
  name: "arcanea-claw",
  version: "0.1.0",
});

// ---- claw_status ----
server.tool(
  "claw_status",
  "Returns ArcaneaClaw engine status: daemon running, last heartbeat, pipeline count, current task.",
  {},
  async () => {
    const daemon = isDaemonRunning();
    const manifest = readManifest();
    const assetCount = manifest.assets.length;
    const pendingCount = manifest.assets.filter((a) => a.status === "pending").length;
    const approvedCount = manifest.assets.filter((a) => a.status === "approved").length;
    const processedCount = manifest.assets.filter((a) => a.status === "processed").length;

    return {
      content: [
        {
          type: "text" as const,
          text: JSON.stringify(
            {
              daemon: {
                running: daemon.running,
                pid: daemon.pid || null,
                pid_file: PID_FILE,
              },
              manifest: {
                path: MANIFEST_PATH,
                exists: fs.existsSync(MANIFEST_PATH),
                total_assets: assetCount,
                pending: pendingCount,
                approved: approvedCount,
                processed: processedCount,
                last_scan_at: manifest.last_scan_at || null,
                last_pipeline_at: manifest.last_pipeline_at || null,
              },
              config: {
                claw_dir: CLAW_DIR,
                config_exists: fs.existsSync(CONFIG_PATH),
              },
            },
            null,
            2
          ),
        },
      ],
    };
  }
);

// ---- claw_scan ----
server.tool(
  "claw_scan",
  "Triggers a media scan of configured paths. Returns count of new files found.",
  {
    paths: z
      .array(z.string())
      .optional()
      .describe(
        "Override scan paths. If omitted, scans the web app's public/guardians directory and CLAW_DIR."
      ),
  },
  async ({ paths }) => {
    const scanPaths = paths || [
      path.join(CLAW_DIR, ".."),
      path.join(CLAW_DIR, "..", "apps", "web", "public", "guardians"),
    ];
    const extensions = getExtensions();
    const ignore = getIgnorePatterns();

    const manifest = readManifest();
    const existingFiles = new Set(manifest.assets.map((a) => a.path));

    let newCount = 0;
    const newFiles: string[] = [];

    for (const scanPath of scanPaths) {
      const resolved = path.resolve(scanPath);
      if (!fs.existsSync(resolved)) continue;

      const found = scanDirectory(resolved, extensions, ignore);
      for (const filePath of found) {
        if (existingFiles.has(filePath)) continue;

        const stat = fs.statSync(filePath);
        const asset: ManifestAsset = {
          id: generateId(),
          file: path.basename(filePath),
          path: filePath,
          status: "pending",
          size_bytes: stat.size,
          mime: getMime(filePath),
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        };

        manifest.assets.push(asset);
        existingFiles.add(filePath);
        newFiles.push(filePath);
        newCount++;
      }
    }

    manifest.last_scan_at = new Date().toISOString();
    writeManifest(manifest);

    return {
      content: [
        {
          type: "text" as const,
          text: JSON.stringify(
            {
              scanned_paths: scanPaths,
              new_files_found: newCount,
              total_assets: manifest.assets.length,
              new_files: newFiles.slice(0, 50), // Cap at 50 for readability
              truncated: newFiles.length > 50,
            },
            null,
            2
          ),
        },
      ],
    };
  }
);

// ---- claw_inbox ----
server.tool(
  "claw_inbox",
  "Returns media inbox: list of assets filtered by status and/or guardian, with counts.",
  {
    status: z
      .string()
      .optional()
      .describe("Filter by status: pending, approved, rejected, processed, uploaded"),
    guardian: z
      .string()
      .optional()
      .describe("Filter by guardian name (e.g. Lyria, Draconia)"),
    limit: z
      .number()
      .optional()
      .describe("Max assets to return (default 50)"),
  },
  async ({ status, guardian, limit }) => {
    const manifest = readManifest();
    let assets = manifest.assets;

    if (status) {
      assets = assets.filter((a) => a.status === status);
    }
    if (guardian) {
      const g = guardian.toLowerCase();
      assets = assets.filter(
        (a) => a.guardian && a.guardian.toLowerCase() === g
      );
    }

    const total = assets.length;
    const cap = limit || 50;
    const sliced = assets.slice(0, cap);

    // Status counts
    const counts: Record<string, number> = {};
    for (const a of manifest.assets) {
      counts[a.status] = (counts[a.status] || 0) + 1;
    }

    return {
      content: [
        {
          type: "text" as const,
          text: JSON.stringify(
            {
              total_matching: total,
              returned: sliced.length,
              status_counts: counts,
              assets: sliced.map((a) => ({
                id: a.id,
                file: a.file,
                status: a.status,
                guardian: a.guardian || null,
                element: a.element || null,
                taste_score: a.taste_score ?? null,
                tier: a.tier || null,
                tags: a.tags || [],
                path: a.path,
              })),
            },
            null,
            2
          ),
        },
      ],
    };
  }
);

// ---- claw_approve ----
server.tool(
  "claw_approve",
  "Approve assets by ID. Updates manifest status to 'approved'.",
  {
    ids: z.array(z.string()).describe("Array of asset IDs to approve"),
  },
  async ({ ids }) => {
    const manifest = readManifest();
    const idSet = new Set(ids);
    let updated = 0;
    const notFound: string[] = [];

    for (const id of ids) {
      const asset = manifest.assets.find((a) => a.id === id);
      if (asset) {
        asset.status = "approved";
        asset.updated_at = new Date().toISOString();
        updated++;
      } else {
        notFound.push(id);
      }
    }

    writeManifest(manifest);

    return {
      content: [
        {
          type: "text" as const,
          text: JSON.stringify(
            {
              approved: updated,
              not_found: notFound,
              total_requested: ids.length,
            },
            null,
            2
          ),
        },
      ],
    };
  }
);

// ---- claw_reject ----
server.tool(
  "claw_reject",
  "Reject assets by ID. Updates manifest status to 'rejected'.",
  {
    ids: z.array(z.string()).describe("Array of asset IDs to reject"),
    reason: z.string().optional().describe("Rejection reason"),
  },
  async ({ ids, reason }) => {
    const manifest = readManifest();
    let updated = 0;
    const notFound: string[] = [];

    for (const id of ids) {
      const asset = manifest.assets.find((a) => a.id === id);
      if (asset) {
        asset.status = "rejected";
        asset.updated_at = new Date().toISOString();
        if (reason) {
          asset.tags = asset.tags || [];
          asset.tags.push(`rejected:${reason}`);
        }
        updated++;
      } else {
        notFound.push(id);
      }
    }

    writeManifest(manifest);

    return {
      content: [
        {
          type: "text" as const,
          text: JSON.stringify(
            {
              rejected: updated,
              not_found: notFound,
              reason: reason || null,
            },
            null,
            2
          ),
        },
      ],
    };
  }
);

// ---- claw_stats ----
server.tool(
  "claw_stats",
  "Returns full dashboard stats: guardian coverage, element distribution, tier breakdown, total counts.",
  {},
  async () => {
    const manifest = readManifest();
    const assets = manifest.assets;

    // Guardian coverage
    const guardianCounts: Record<string, number> = {};
    for (const g of GUARDIANS) guardianCounts[g] = 0;
    for (const a of assets) {
      if (a.guardian && a.guardian in guardianCounts) {
        guardianCounts[a.guardian]++;
      }
    }

    // Element distribution
    const elementCounts: Record<string, number> = {};
    for (const e of ELEMENTS) elementCounts[e] = 0;
    let unclassifiedElement = 0;
    for (const a of assets) {
      if (a.element && a.element in elementCounts) {
        elementCounts[a.element]++;
      } else {
        unclassifiedElement++;
      }
    }

    // Status counts
    const statusCounts: Record<string, number> = {};
    for (const a of assets) {
      statusCounts[a.status] = (statusCounts[a.status] || 0) + 1;
    }

    // Tier breakdown
    const tierCounts = { hero: 0, gallery: 0, archive: 0, unscored: 0 };
    for (const a of assets) {
      if (a.taste_score == null) {
        tierCounts.unscored++;
      } else if (a.taste_score >= 80) {
        tierCounts.hero++;
      } else if (a.taste_score >= 60) {
        tierCounts.gallery++;
      } else {
        tierCounts.archive++;
      }
    }

    // Score stats
    const scored = assets.filter((a) => a.taste_score != null);
    const scores = scored.map((a) => a.taste_score!);
    const avgScore =
      scores.length > 0
        ? Math.round((scores.reduce((s, v) => s + v, 0) / scores.length) * 10) / 10
        : null;

    return {
      content: [
        {
          type: "text" as const,
          text: JSON.stringify(
            {
              total_assets: assets.length,
              status: statusCounts,
              guardians: guardianCounts,
              elements: { ...elementCounts, unclassified: unclassifiedElement },
              tiers: tierCounts,
              scores: {
                scored_count: scored.length,
                average: avgScore,
                min: scores.length > 0 ? Math.min(...scores) : null,
                max: scores.length > 0 ? Math.max(...scores) : null,
              },
              last_scan_at: manifest.last_scan_at || null,
              last_pipeline_at: manifest.last_pipeline_at || null,
            },
            null,
            2
          ),
        },
      ],
    };
  }
);

// ---- claw_process ----
server.tool(
  "claw_process",
  "Trigger processing on approved/pending assets. Marks them as 'processed'.",
  {
    limit: z.number().optional().describe("Max assets to process (default 20)"),
    status_filter: z
      .string()
      .optional()
      .describe("Which status to process: 'approved' (default) or 'pending'"),
  },
  async ({ limit, status_filter }) => {
    const manifest = readManifest();
    const filterStatus = status_filter || "approved";
    const cap = limit || 20;

    const candidates = manifest.assets.filter(
      (a) => a.status === filterStatus
    );
    const toProcess = candidates.slice(0, cap);

    const processed: string[] = [];
    for (const asset of toProcess) {
      asset.status = "processed";
      asset.processed_at = new Date().toISOString();
      asset.updated_at = new Date().toISOString();
      processed.push(asset.id);
    }

    writeManifest(manifest);

    return {
      content: [
        {
          type: "text" as const,
          text: JSON.stringify(
            {
              processed_count: processed.length,
              from_status: filterStatus,
              candidates_available: candidates.length,
              processed_ids: processed,
            },
            null,
            2
          ),
        },
      ],
    };
  }
);

// ---- claw_heroes ----
server.tool(
  "claw_heroes",
  "List all hero-tier assets (TASTE score 80+).",
  {
    guardian: z.string().optional().describe("Filter heroes by guardian name"),
  },
  async ({ guardian }) => {
    const manifest = readManifest();
    let heroes = manifest.assets.filter(
      (a) => a.taste_score != null && a.taste_score >= 80
    );

    if (guardian) {
      const g = guardian.toLowerCase();
      heroes = heroes.filter(
        (a) => a.guardian && a.guardian.toLowerCase() === g
      );
    }

    // Sort by score descending
    heroes.sort((a, b) => (b.taste_score || 0) - (a.taste_score || 0));

    return {
      content: [
        {
          type: "text" as const,
          text: JSON.stringify(
            {
              hero_count: heroes.length,
              heroes: heroes.map((a) => ({
                id: a.id,
                file: a.file,
                guardian: a.guardian || null,
                element: a.element || null,
                taste_score: a.taste_score,
                tags: a.tags || [],
                path: a.path,
                status: a.status,
              })),
            },
            null,
            2
          ),
        },
      ],
    };
  }
);

// ---- claw_classify ----
server.tool(
  "claw_classify",
  "Classify unclassified assets using filename/path heuristics (guardian, element, tags).",
  {
    limit: z.number().optional().describe("Max assets to classify (default 100)"),
  },
  async ({ limit }) => {
    const manifest = readManifest();
    const cap = limit || 100;

    // Find unclassified assets (no guardian AND no element)
    const unclassified = manifest.assets.filter(
      (a) => !a.guardian && !a.element
    );
    const toClassify = unclassified.slice(0, cap);

    let classifiedCount = 0;
    const results: Array<{
      id: string;
      file: string;
      guardian: string | null;
      element: string | null;
      tags: string[];
    }> = [];

    for (const asset of toClassify) {
      const classification = classifyByHeuristics(asset.path);

      if (classification.guardian) asset.guardian = classification.guardian;
      if (classification.element) asset.element = classification.element;
      if (classification.tags.length > 0) {
        asset.tags = [...(asset.tags || []), ...classification.tags];
      }

      if (classification.guardian || classification.element) {
        asset.classified_at = new Date().toISOString();
        asset.updated_at = new Date().toISOString();
        classifiedCount++;
      }

      results.push({
        id: asset.id,
        file: asset.file,
        guardian: asset.guardian || null,
        element: asset.element || null,
        tags: asset.tags || [],
      });
    }

    writeManifest(manifest);

    return {
      content: [
        {
          type: "text" as const,
          text: JSON.stringify(
            {
              total_unclassified: unclassified.length,
              attempted: toClassify.length,
              classified: classifiedCount,
              still_unclassified: unclassified.length - classifiedCount,
              results: results.slice(0, 50),
            },
            null,
            2
          ),
        },
      ],
    };
  }
);

// ---- claw_pipeline ----
server.tool(
  "claw_pipeline",
  "Run the full pipeline: scan -> classify -> dedup -> process. Returns pipeline results summary.",
  {
    scan_paths: z
      .array(z.string())
      .optional()
      .describe("Override scan paths"),
    process_limit: z
      .number()
      .optional()
      .describe("Max assets to process (default 20)"),
  },
  async ({ scan_paths, process_limit }) => {
    const results: Record<string, any> = {};

    // Step 1: Scan
    const extensions = getExtensions();
    const ignore = getIgnorePatterns();
    const scanDirs = scan_paths || [
      path.join(CLAW_DIR, ".."),
      path.join(CLAW_DIR, "..", "apps", "web", "public", "guardians"),
    ];

    const manifest = readManifest();
    const existingFiles = new Set(manifest.assets.map((a) => a.path));
    let newCount = 0;

    for (const scanPath of scanDirs) {
      const resolved = path.resolve(scanPath);
      if (!fs.existsSync(resolved)) continue;
      const found = scanDirectory(resolved, extensions, ignore);
      for (const filePath of found) {
        if (existingFiles.has(filePath)) continue;
        const stat = fs.statSync(filePath);
        manifest.assets.push({
          id: generateId(),
          file: path.basename(filePath),
          path: filePath,
          status: "pending",
          size_bytes: stat.size,
          mime: getMime(filePath),
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        });
        existingFiles.add(filePath);
        newCount++;
      }
    }
    manifest.last_scan_at = new Date().toISOString();
    results.scan = { new_files: newCount, total: manifest.assets.length };

    // Step 2: Classify
    let classifiedCount = 0;
    for (const asset of manifest.assets) {
      if (asset.guardian || asset.element) continue;
      const c = classifyByHeuristics(asset.path);
      if (c.guardian) asset.guardian = c.guardian;
      if (c.element) asset.element = c.element;
      if (c.tags.length > 0) {
        asset.tags = [...(asset.tags || []), ...c.tags];
      }
      if (c.guardian || c.element) {
        asset.classified_at = new Date().toISOString();
        asset.updated_at = new Date().toISOString();
        classifiedCount++;
      }
    }
    results.classify = { classified: classifiedCount };

    // Step 3: Dedup (by file hash or path)
    const seen = new Map<string, string>();
    const dupes: string[] = [];
    for (const asset of manifest.assets) {
      const key = asset.hash || asset.path;
      if (seen.has(key)) {
        dupes.push(asset.id);
        asset.status = "rejected";
        asset.tags = [...(asset.tags || []), "duplicate"];
        asset.updated_at = new Date().toISOString();
      } else {
        seen.set(key, asset.id);
      }
    }
    results.dedup = { duplicates_found: dupes.length };

    // Step 4: Process (mark pending as processed)
    const cap = process_limit || 20;
    const pending = manifest.assets.filter((a) => a.status === "pending");
    const toProcess = pending.slice(0, cap);
    for (const asset of toProcess) {
      asset.status = "processed";
      asset.processed_at = new Date().toISOString();
      asset.updated_at = new Date().toISOString();
    }
    results.process = {
      processed: toProcess.length,
      remaining_pending: pending.length - toProcess.length,
    };

    manifest.last_pipeline_at = new Date().toISOString();
    writeManifest(manifest);

    return {
      content: [
        {
          type: "text" as const,
          text: JSON.stringify(
            {
              pipeline: "complete",
              steps: results,
              total_assets: manifest.assets.length,
              timestamp: manifest.last_pipeline_at,
            },
            null,
            2
          ),
        },
      ],
    };
  }
);

// ---------------------------------------------------------------------------
// Utility
// ---------------------------------------------------------------------------

function getMime(filePath: string): string {
  const ext = path.extname(filePath).toLowerCase();
  const mimeMap: Record<string, string> = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".flac": "audio/flac",
  };
  return mimeMap[ext] || "application/octet-stream";
}

// ---- __openclaw_info ----
// OpenClaw convention: every skill MCP server exposes a metadata tool
// so the host can discover capabilities without parsing config files.
server.tool(
  "__openclaw_info",
  "Returns ArcaneaClaw skill metadata for OpenClaw/NanoClaw host integration. Includes version, available tools, skills, and runtime info.",
  {},
  async () => {
    return {
      content: [
        {
          type: "text" as const,
          text: JSON.stringify(
            {
              name: "@arcanea/claw",
              display_name: "ArcaneaClaw -- Creator Media Engine",
              version: "0.1.0",
              runtime: CLAW_RUNTIME,
              description:
                "AI-powered media pipeline: scan, classify, score, process, upload, social. Works standalone, with OpenClaw, or as MCP tools for Claude Code.",
              author: "frankxai",
              homepage: "https://arcanea.ai/claw",
              repository: "https://github.com/frankxai/arcanea-claw",
              license: "MIT",
              tools: [
                "claw_status",
                "claw_scan",
                "claw_inbox",
                "claw_approve",
                "claw_reject",
                "claw_stats",
                "claw_process",
                "claw_heroes",
                "claw_classify",
                "claw_pipeline",
                "__openclaw_info",
              ],
              skills: [
                "media-scan",
                "media-classify",
                "taste-score",
                "media-dedup",
                "media-process",
                "media-upload",
                "social-prep",
                "notify",
              ],
              platforms: ["openclaw", "nanoclaw", "claude-code", "standalone"],
              config: {
                claw_dir: CLAW_DIR,
                manifest_path: MANIFEST_PATH,
                config_path: CONFIG_PATH,
              },
              capabilities: {
                mcp_transport: "stdio",
                scheduled_skills: true,
                on_demand_skills: true,
                health_check: "claw_status",
                memory_format: "markdown",
              },
            },
            null,
            2
          ),
        },
      ],
    };
  }
);

// ---------------------------------------------------------------------------
// Start
// ---------------------------------------------------------------------------

async function main(): Promise<void> {
  const transport = new StdioServerTransport();

  // Startup banner to stderr (does not interfere with stdio MCP transport)
  const runtimeLabel: Record<ClawRuntime, string> = {
    openclaw: "OpenClaw skill",
    nanoclaw: "NanoClaw skill",
    "claude-code": "Claude Code MCP",
    standalone: "standalone",
  };
  process.stderr.write(
    `[ArcaneaClaw] v0.1.0 starting as ${runtimeLabel[CLAW_RUNTIME]} | ` +
      `dir=${CLAW_DIR} | tools=11 | skills=8\n`
  );

  await server.connect(transport);
}

main().catch((err) => {
  console.error("ArcaneaClaw MCP server failed to start:", err);
  process.exit(1);
});
