---
name: codex-bridge
domain: meta
description: |
  [TOOL] Direct MCP integration with Codex CLI as agency tool. Codex (frontier OpenAI
  coding model, currently GPT-6-Astra) is
  available as MCP server, exposing tools `mcp__codex__codex` (start session)
  and `mcp__codex__codex-reply` (continue). Use Codex for: image generation,
  UI mockups, vision/multimodal review, cross-family second opinion. Reference-
  only — loaded by visual designers (design-visual-designer, marketing-banner-
  designer, design-ui-designer, design-presentation-designer) and adversary
  scripts via skill frontmatter.
---

# Codex bridge — direct MCP integration

## What Codex is and what it brings

Codex CLI runs as an MCP server (`codex mcp-server`), connected to Claude Code via project-level `.mcp.json` plus the user-level `mcpServers` entry in `~/.claude.json`. Authenticated via the user's ChatGPT subscription (no separate API key needed).

**Binary path — one source of truth.** Both registrations MUST point at the npm-global install, the same binary `adversary_lg.py` resolves through `shutil.which("codex")`:

```
<npm-global>/node_modules/@openai/codex/node_modules/@openai/codex-win32-x64/vendor/x86_64-pc-windows-msvc/bin/codex.exe
```

Resolve it once with `npm root -g` (or `where codex` / `which codex`) and use that same path in
both registrations. Worth re-checking on a schedule: probe what the MCP client would actually
launch (an `initialize` handshake plus `tools/list`), compare that binary's version against the one
the consilium resolves through PATH, and confirm `codex login status`. A registration pointing at a
binary that no longer matches is the failure this section exists to prevent.

Do NOT point them at `%LOCALAPPDATA%\OpenAI\Codex\bin\codex.exe`. That is the Codex desktop app's launcher; it lags the app's real binary (which lives in a per-version hash subdirectory that changes on every update), so it silently rots into an old release that rejects config keys the current app writes. That divergence is the 2026-08-27 breakage: `codex exec` kept working on the npm binary while the MCP server died on the stale one, taking every visual specialist offline without touching the adversary consilium. See `memory/codex-mcp-config.md` for the diagnostic sequence.

Through MCP, two tools are exposed:
- `mcp__codex__codex` — start a Codex session with prompt + config
- `mcp__codex__codex-reply` — continue a thread by id + new prompt

Underlying model: whatever `model` is set to in `~/.codex/config.toml` — currently
`gpt-6-astra`. The agency deliberately does NOT pin a model at the call site (neither
`adversary_lg.py` nor any workflow passes one), so one config line moves both the MCP
and the `codex exec` path together. Capabilities:
- **Image generation and editing** (DALL-E 3 / gpt-image-1 class)
- Web lookup
- PowerShell shell access (read-only by default, configurable)
- Local image viewing (multimodal vision)
- MCP resource reading
- Sub-agents (only on explicit delegation)

## Codex as the default creative director for visual work

For ANY visual-creative deliverable — logo / brand identity, hi-fi UI visuals, campaign banners, presentation slide visuals, photography / imagery, art direction, "give me N bold directions" — **Codex is the default creative engine, not a fallback or an afterthought.** The Claude specialist does NOT hand-author the visual concept; it ORCHESTRATES Codex and integrates the result.

Division of labour (the standing default for every design/visual engagement — baked into the visual agents + their methodology skills, NOT a per-engagement choice):

| Step | Owner |
|---|---|
| Creative direction / concept / "N bold visual directions" | **Codex** (`mcp__codex__codex`) — more divergent, more interesting visuals than Claude |
| Art direction, composition, imagery, raster / photoreal generation | **Codex** |
| Orchestration: brief → Codex prompt, variant iteration (`codex-reply`), choosing the direction | Claude specialist |
| Brand-alignment judgement + asset verification (Read the output, confirm it matches the brief) | Claude specialist |
| Spec / tokens / component code / responsive / dark-mode / accessibility / HTML+Chart.js assembly | Claude specialist (NEVER Codex — structural / engineering) |
| Copy, messaging, UX flow / IA logic | Claude (structure / text) |

**Why:** this Claude model family is comparatively weak at visual-creative divergence; Codex / ChatGPT (gpt-image class) is stronger and more interesting. The creative *idea* comes from Codex; Claude conducts and builds.

**Graceful fallback (never a silent quality downgrade):** if Codex is offline or quota-exhausted, fall back to Gemini (the `design-assets-guide` / `banner-design-guide` scripts) or escalate to the user — and SAY the creative path was downgraded. Do not quietly substitute a weaker Claude-authored visual and present it as the intended quality.

The `## When to use Codex` table below is the per-deliverable routing UNDER this default (structural / data-driven / tokenizable work stays Claude; SVG icons may stay Gemini). Read it as "when does a fallback or a structured-Claude path apply", not "should I use Codex at all for the creative".

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
| `model` | `~/.codex/config.toml` (rides the ChatGPT subscription) | Leave unset. The account gates which ids it will serve — an unavailable one fails the whole call. Change the model in the config, not here, so both Codex paths move together. |

### Multi-turn refinement

For iterative work (refine output, generate variants):

```python
# First call returns a thread id in the response
result = mcp__codex__codex({...})
thread_id = parse_thread_id(result)

# Subsequent refinements use codex-reply
mcp__codex__codex-reply({
    "threadId": thread_id,
    "prompt": "Variant 2: same composition but with a square mark instead of geometric inner shape."
})
```

The parameter is `threadId`. `conversationId` still works but its own schema marks it DEPRECATED.
There is no `thread_id` argument: the schema declares only `prompt` as required, so a snake_case key
is dropped silently and the call opens a session that never saw the first prompt. That reads as
"Codex ignored the refinement", not as an error. Re-probe the live schema (`codex mcp-server`,
`tools/list`) after a Codex update rather than trusting this line.

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

- **Don't pass `model` at all.** The ChatGPT subscription serves only some ids, and a call naming one it does not serve fails outright. Set the model once in `~/.codex/config.toml`; every call inherits it.
- **After changing the model, restart the session.** The MCP roster is fixed at session start, so a running session keeps the binary it started with — and a model newer than that binary fails per-invocation with "requires a newer version of Codex" even though the config is correct.
- **Don't use sandbox `danger-full-access`** unless engagement explicitly requires write outside engagement/ (extremely rare).
- **Don't generate images directly into `engagement/brand/` or `engagement/ui/`** — pair structure: generate to `engagement/codex-outputs/`, then specialist promotes to final location after verification.
- **Don't skip the verification step** — agent must Read the generated image and confirm it roughly matches the prompt before integrating.
- **Don't accept "looks close enough"** — if output doesn't satisfy acceptance criteria, refine via `codex-reply` (max 3 refinement rounds before escalating).
- **Don't put Codex prompts in handoff.md prose** — they're embedded in tool calls; audit trail goes to validation-log.md.
- **Don't expect Codex to know your engagement context** — every call is fresh; pass full criteria/constraints in the prompt.

## Iteration on Codex outputs

If output doesn't satisfy criteria after first call:

1. Call `mcp__codex__codex-reply` with `threadId` and refinement prompt.
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
Continue same session:   mcp__codex__codex-reply (with threadId)
Binary both paths use:   %APPDATA%\npm\node_modules\@openai\codex\...\bin\codex.exe (npm-global)
Health check:            codex login status  →  "Logged in using ChatGPT", exit 0
                         echo '{"jsonrpc":"2.0","id":1,"method":"initialize", ...}' | codex mcp-server

Must-pass args:          prompt, approval-policy, sandbox, cwd
Don't pass:              model (set it in ~/.codex/config.toml instead)

Where outputs go:        engagement/codex-outputs/{slug}.png
Audit log:               engagement/validation-log.md → ## codex-bridge invocations
Refinement budget:       3 rounds per asset
```
