---
name: codex-bridge
domain: meta
description: |
  [TOOL] Direct MCP integration with Codex CLI as agency tool. Codex (GPT-5-class) is
  available as MCP server, exposing tools `mcp__codex__codex` (start session)
  and `mcp__codex__codex-reply` (continue). Use Codex for: image generation,
  UI mockups, vision/multimodal review, cross-family second opinion. Reference-
  only — loaded by visual designers (design-visual-designer, marketing-banner-
  designer, design-ui-designer, design-presentation-designer) and adversary
  scripts via skill frontmatter.
---

# Codex bridge — direct MCP integration

## What Codex is and what it brings

Codex CLI (`codex` on PATH, or `%LOCALAPPDATA%\OpenAI\Codex\bin\codex.exe` on Windows; v0.129.0-alpha.15+) runs as an MCP server (`codex mcp-server`), connected to Claude Code via project-level `.mcp.json`. Authenticated via the user's ChatGPT subscription (no separate API key needed).

Through MCP, two tools are exposed:
- `mcp__codex__codex` — start a Codex session with prompt + config
- `mcp__codex__codex-reply` — continue a thread by id + new prompt

Underlying model: GPT-5-based coding agent with capabilities:
- **Image generation and editing** (DALL-E 3 / gpt-image-1 class)
- Web lookup
- PowerShell shell access (read-only by default, configurable)
- Local image viewing (multimodal vision)
- MCP resource reading
- Sub-agents (only on explicit delegation)

## When to use Codex (vs Gemini, vs Claude tools, vs static SVG)

| Task | Use Codex? | Alternative |
|---|---|---|
| Logo generation (raster, multi-style) | ✅ primary | Gemini if Codex offline |
| UI mockups (full-screen, realistic) | ✅ primary | none — Codex unique here |
| Banner / ad creative | ✅ primary | Gemini for fast iterations |
| Photo composition (people, scenes) | ✅ primary | none |
| Icons (SVG-style) | ⚠️ Codex raster→trace OR Gemini direct SVG | Gemini for direct SVG |
| Charts / data visualization | ❌ no — use Chart.js HTML→screenshot | HTML→screenshot |
| Multimodal review (look at screenshot, judge UX) | ✅ primary | Claude can read images but Codex stronger on visual judgement |
| Cross-family adversary review (text task) | ✅ primary | required for L-tier consilium |
| Wireframes (low-fi) | ❌ no — Claude SVG sufficient | Claude SVG |
| Code generation | ⚠️ Claude is the primary agent here; Codex only for cross-family second opinion | Claude (default) |

**Rule of thumb:** if the deliverable benefits from photorealism, complex visual composition, or cross-family second opinion, use Codex. If structural / data-driven / tokenizable, use Claude tools.

## Direct invocation pattern

Specialist agent calls the MCP tool directly. The tool spawns a fresh Codex session, sends the prompt, returns the result.

### Image generation — basic call

```python
# Pseudocode for tool call structure (the actual call is via MCP tool invocation)
mcp__codex__codex({
    "prompt": (
        "Generate a 1024x1024 PNG: minimalist FinTech logo, "
        "blue (#0066cc) circle with white inner geometric mark, "
        "flat style, no text. "
        "Save to engagement/codex-outputs/logo-v1.png. "
        "Output one line: SAVED: <path>"
    ),
    "approval-policy": "never",
    "sandbox": "workspace-write",
    "cwd": "/path/to/working/dir"
})
```

Codex will:
1. Generate the image using its internal image-gen tool
2. Save to the specified path (path must be under `cwd` if `sandbox: workspace-write`)
3. Reply with `SAVED: <path>` confirmation

### Required arguments

| Arg | Default | When to override |
|---|---|---|
| `prompt` | required | always — your task description |
| `approval-policy` | uses Codex config | `"never"` for unattended automation; `"untrusted"` to require human approval per shell command |
| `sandbox` | uses Codex config | `"workspace-write"` to write files in cwd; `"read-only"` for analysis-only; `"danger-full-access"` to lift sandbox (rarely needed) |
| `cwd` | current dir | absolute path to engagement/ when generating engagement assets |
| `model` | Codex default (uses ChatGPT subscription) | DO NOT pass `gpt-5` — not supported via ChatGPT subscription. Leave default. |

### Multi-turn refinement

For iterative work (refine output, generate variants):

```python
# First call returns a thread_id in the response
result = mcp__codex__codex({...})
thread_id = parse_thread_id(result)

# Subsequent refinements use codex-reply with thread_id
mcp__codex__codex-reply({
    "thread_id": thread_id,
    "prompt": "Variant 2: same composition but with a square mark instead of geometric inner shape."
})
```

## Engagement integration: codex-outputs/ artefact

Generated assets live in `engagement/codex-outputs/` (whitelisted directory). Specialist agent:

1. Calls `mcp__codex__codex` with `cwd=engagement/` and explicit save path under `codex-outputs/`.
2. Verifies the file exists via Read tool (multimodal — confirms image roughly matches prompt).
3. Logs in `engagement/validation-log.md` under specialist's section:
   ```markdown
   ### codex-bridge invocations (iter N)
   - logo-v1.png (1024x1024 PNG, prompt: "minimalist FinTech logo...") — verified ✓
   - banner-instagram-v1.png — verified ✓ (3 variants requested via codex-reply)
   ```
4. Integrates the asset into the deliverable (handoff §2 or domain-specific dir).

## Vision review (multimodal)

Codex can look at images and judge them — useful for design review where Claude's text-based reasoning misses visual issues:

```python
mcp__codex__codex({
    "prompt": (
        "Look at the screenshot at engagement/screens/iter-1/dashboard-dark.png "
        "and the criteria from engagement/criteria.md. List 3 specific UX issues "
        "you observe in the screenshot, with severity. Be concrete about where in "
        "the image (top-left, center, etc.). Output JSON only."
    ),
    "approval-policy": "never",
    "sandbox": "read-only",
    "cwd": "/path/to/engagement"
})
```

Codex returns structured findings the agent can integrate into validation-log.md or pass to consilium-synth.

## Cross-family coverage map (where Codex IS and is NOT used)

| Layer | Tier | Codex used? | How |
|---|---|---|---|
| Validators (code-reviewer, security-auditor, reality-checker, skeptic, etc.) | S/M/L | ❌ NO — Anthropic-only | Single-family validators run via Task tool / `validator_lg.py`. Codex cross-family check comes ONE LEVEL UP in the adversary phase (L only) |
| Adversary consilium | S | ❌ NO — no adversary on S | — |
| Adversary consilium | M | ❌ NO — peer-Opus only (single-family) | `adversary_lg.py --consilium M` |
| Adversary consilium | L | ✅ YES — 2× Codex (blind + informed) | `adversary_lg.py --consilium L` — 5 reviewers: peer-Opus + Codex-blind + Codex-informed + Sonnet + Haiku |
| Director judge | S | N/A (no director) | — |
| Director judge | M | ❌ — single-family judge | Domain director adjudicates |
| Director judge | L | ❌ — single-family judge | Domain director adjudicates |
| Visual asset generation | any | ✅ YES — primary tool for logo/CIP/banner/icons | Direct `mcp__codex__codex` from visual specialists |

**Why this map matters:** the audit (`agency_chains_audit.md` Section E) initially suggested promoting Codex to standard cross-family validator at L-tier. On review, this duplicates what L-tier adversary already does: adversary on L runs 2 Codex reviewers seeing the same artefacts validators saw. The Codex cross-check happens — just at the adversary stage, not the validator stage. Adding a second Codex pass at validator level would burn budget without adding signal.

**The one genuine gap:** the director's JUDGE phase is single-family even on L-tier. The supreme-judge (human) step partially compensates by introducing a third viewpoint, but if you want truly cross-family adjudication, a future `director_lg.py` could include an optional Codex co-adjudicator on the L-tier verdict. Not implemented now — flagged as Wave 4+ opportunistic per migration roadmap.

## Adversary integration (cross-family second opinion)

`adversary_lg.py` already supports `codex-blind` and `codex-informed` reviewer roles via subprocess invocation. With MCP available, an alternative path is to call `mcp__codex__codex` directly from a specialist agent's review workflow:

```python
# Cross-family adversary review of a deliverable
mcp__codex__codex({
    "prompt": (
        "You are an adversarial reviewer. Read engagement/criteria.md and "
        "engagement/handoff.md. Find what is wrong, missing, or insufficient. "
        "Output JSON: {verdict: satisfied|rework_required|suspicious_too_clean, "
        "findings: [...], summary: '...'}."
    ),
    "approval-policy": "never",
    "sandbox": "read-only",
    "cwd": "/path/to/engagement"
})
```

This is functionally equivalent to `adversary_lg.py --role codex-blind` but with native MCP tool integration (no Python subprocess overhead).

## Anti-patterns

- **Don't pass `model: "gpt-5"`** — ChatGPT subscription rejects it. Leave model unset (Codex picks compatible default).
- **Don't use sandbox `danger-full-access`** unless engagement explicitly requires write outside engagement/ (extremely rare).
- **Don't generate images directly into `engagement/brand/` or `engagement/ui/`** — pair structure: generate to `engagement/codex-outputs/`, then specialist promotes to final location after verification.
- **Don't skip the verification step** — agent must Read the generated image and confirm it roughly matches the prompt before integrating.
- **Don't accept "looks close enough"** — if output doesn't satisfy acceptance criteria, refine via `codex-reply` (max 3 refinement rounds before escalating).
- **Don't put Codex prompts in handoff.md prose** — they're embedded in tool calls; audit trail goes to validation-log.md.
- **Don't expect Codex to know your engagement context** — every call is fresh; pass full criteria/constraints in the prompt.

## Iteration on Codex outputs

If output doesn't satisfy criteria after first call:

1. Call `mcp__codex__codex-reply` with thread_id and refinement prompt.
2. Max 3 refinement rounds per asset before escalating to user (or trying alternative tool, e.g. Gemini).
3. Each refinement round logged in validation-log.md with `## Refinement N` heading and brief delta.

## Permissions and approval

Codex tools (`mcp__codex__codex`, `mcp__codex__codex-reply`) need to be allowlisted in Claude Code permissions for unattended use. First invocation will prompt for approval per Claude Code's MCP permission UX. Once approved, subsequent calls in the same session run without prompts.

For automated agency engagements, consider adding to user settings.json `permissions.allow`:
```json
"mcp__codex__codex",
"mcp__codex__codex-reply"
```

## Cost and rate limits

Uses ChatGPT subscription quota. No separate billing if subscription is active. If quota exhausts mid-engagement, Codex returns an error response — specialist agent should detect, log, and either fall back to alternative tool (Gemini) or escalate to user.

## Quick reference

```
Tool name (MCP):         mcp__codex__codex
Continue same session:   mcp__codex__codex-reply (with thread_id)

Must-pass args:          prompt, approval-policy, sandbox, cwd
Don't pass:              model: "gpt-5" (ChatGPT subscription rejects)

Where outputs go:        engagement/codex-outputs/{slug}.png
Audit log:               engagement/validation-log.md → ## codex-bridge invocations
Refinement budget:       3 rounds per asset
```
