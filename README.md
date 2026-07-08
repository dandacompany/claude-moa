# claude-moa

**A Mixture of Agents skill for Claude Code — fan out a question to several models in parallel, then let your current session synthesize their perspectives.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![skills.sh](https://img.shields.io/badge/skills.sh-claude--moa-blue)](https://skills.sh/dandacompany/claude-moa)

한국어 문서: [README.ko.md](./README.ko.md)

Unlike a model-provider gateway that silently blends models beneath your agent, this skill sits *inside* Claude Code as an ordinary skill. It never pretends to be the aggregator: reference models only advise (soft) or read code read-only (hard), and the final judgment and action always stay with your live Claude session. It is a **perspective gatherer**, not a decision maker.

The MoA logic — advisory reframing, parallel fan-out, failure isolation, and the config schema — is ported from NousResearch [Hermes Agent](https://github.com/NousResearch/Hermes-Agent) (MIT). Synthesis is deliberately left out: the script returns a labeled block of perspectives, and your session reconciles them with full tools.

## Why MoA

Combining several models' perspectives on a hard problem beats any single model (HermesBench: a 2-model MoA scored 0.8202 vs. 0.7607 for a single top model). This skill brings that pattern to Claude Code natively — no separate gateway, no provider shim.

## Two modes

| | **soft** (default) | **hard** |
| --- | --- | --- |
| Reference nature | advice from prompt text only | independent session with read-only tools |
| Code access | ❌ prompt context only | ✅ real repo exploration (read-only) |
| Backends run | `openrouter` only | `codex` · `claude` (subscription) + `openrouter` (advisory, or Docker-isolated) |
| Use for | ideas, design, judgment | actual codebase analysis / review |

References cannot cause side effects in **any** mode: `codex` is spawned with `-s read-only`, `claude` with `--permission-mode plan`, an `openrouter` docker reference runs inside a kernel-enforced read-only container, and every child process receives a minimal environment (no inherited API keys). Only the aggregator — your session — holds full permissions.

### Hybrid backends — billing decides the path

The three backends differ in how they're billed, and that determines how they run:

- **`codex` / `claude` — subscription (OAuth).** Run via their native CLIs on the host, using your ChatGPT / Claude subscription. Flat-rate, so no reason to route them elsewhere.
- **`openrouter` — metered (per token).** In `soft` mode it advises from prompt text. In `hard` mode it's advisory by default, but a reference marked `isolate: docker` is promoted to a real code-reading agent inside an **on-demand Docker container** — the repo is mounted `:ro`, the root filesystem is `--read-only`, so writes are refused by the kernel, not merely by a flag. Since it's metered anyway, isolation is maxed out. This works for any of OpenRouter's models (Claude, GPT, Gemini, DeepSeek, …) via one key.

## Requirements

- **Python 3** with **PyYAML** (`pip install pyyaml`) — the only dependency.
- **OpenRouter API key**: `OPENROUTER_API_KEY` (env var, preferred) or `~/.claude/auth/ai-ml-services.env`.
- **Docker** (optional, for `isolate: docker` references): the `moa-agent` image is built lazily from the shipped Dockerfile on first use.
- **Codex CLI** (optional, hard mode): [openai/codex](https://github.com/openai/codex), logged in.
- **Claude Code CLI** (optional, hard mode): logged in.

Missing backends are isolated as `[failed: ...]` — the rest of the fan-out still runs.

## First-run setup

`moa setup` detects which backends are available and writes a recommended config. It **never asks for an API key** — it only checks presence and guides you to set missing ones yourself, in a separate terminal:

```bash
python3 ~/.claude/skills/moa/scripts/moa.py setup
```

Never paste an API key into the Claude session — it would land in the transcript. Set `OPENROUTER_API_KEY` in your shell profile (or the auth file); log into `codex` / Claude Code for the subscription backends.

## Install

### Option A — clone + copy (recommended)

```bash
git clone https://github.com/dandacompany/claude-moa.git ~/src/claude-moa
rsync -rlpt ~/src/claude-moa/moa/ ~/.claude/skills/moa/
pip install pyyaml
```

### Option B — skills CLI

```bash
skills add dandacompany/claude-moa@moa -g --copy -a claude-code
```

### Verify

```bash
export OPENROUTER_API_KEY=sk-or-...
cd <any-repo> && python3 ~/.claude/skills/moa/scripts/moa.py "why is this slow?"
```

## Usage

From a Claude Code session:

```
/moa review the trade-offs of this architecture choice        # soft, default preset
/moa --hard --preset review analyze this module's concurrency  # hard, real code analysis
```

Or directly:

```bash
cd <target-repo>
python3 ~/.claude/skills/moa/scripts/moa.py "<prompt>" [--hard] [--preset <name>] [--refs-only]
```

The output is a `## MoA references` block (one section per reference) followed by a synthesis instruction. `--refs-only` returns just the perspectives, without the synthesis hint.

## Configuration

`~/.claude/moa/config.yml` (created automatically on first run):

```yaml
default_preset: default
presets:
  default:                     # soft — openrouter advice
    references:
      - { backend: openrouter, model: z-ai/glm-5.2 }
      - { backend: openrouter, model: openai/gpt-5.5 }
    reference_max_tokens: null # null = unlimited, or an int to cap reference length
    enabled: true
  review:                      # hard code review — subscription sessions + Docker-isolated openrouter
    references:
      - { backend: claude, model: claude-opus-4-8 }                   # subscription (OAuth)
      - { backend: codex, model: gpt-5.5 }                            # subscription (OAuth)
      - { backend: openrouter, model: z-ai/glm-5.2, isolate: docker } # metered; kernel-isolated, reads code
    reference_max_tokens: 2000
    enabled: true
```

| Field | Rule |
| --- | --- |
| `backend` | one of `openrouter` / `codex` / `claude`; anything else (including a recursive `moa`) is dropped |
| `model` | non-empty string; backend-specific model id |
| `isolate` | `docker` promotes an `openrouter` hard reference to a kernel-isolated code-reading agent; honored only for `openrouter` (else `none`) |
| `reference_max_tokens` | positive int, else `null` (unlimited); applies to advisors |
| `enabled` | `false` skips the fan-out and lets the aggregator act alone |

Notes:

- In soft mode only `openrouter` references run; `codex`/`claude` show as `[skipped: hard only]`.
- `isolate: docker` needs Docker running; the `moa-agent` image builds on first use. A docker-isolated reference shows as `openrouter:model (docker)` in the output so you can tell code-reading refs from advisory ones.
- Up to 8 references run in parallel; one failure is isolated as `[failed: <reason>]` and the rest continue.
- For reasoning-heavy models (deepseek, glm, …) set `reference_max_tokens` to 2000+ — too low and the budget is spent on reasoning, yielding empty content.
- A malformed YAML file falls back to the default preset (with a warning).

## Design notes

Small modules, one responsibility each:

- `config.py` — registry load + normalization (pure functions)
- `adapters.py` — one reference call per backend; read-only enforcement; error/secret sanitization; Docker isolation
- `fanout.py` — parallel orchestration, mode gating, failure isolation, output formatting
- `setup.py` — provider detection + config recommendation (never collects key values)
- `moa.py` — CLI entry (argument parsing, `setup` subcommand, mode wiring, synthesis hint)
- `docker/` — the `moa-agent` read-only reference container (stdlib tool loop, path-confined)

Synthesis is not ported — the returned block is meant to be reconciled by the calling session.

## Security

References run untrusted models, so the skill enforces a read-only invariant and limits what leaves the machine:

- **No side effects.** `codex` runs under `-s read-only`; `claude` under `--permission-mode plan` with `--allowedTools Read Grep Glob`. The actual write-block comes from plan mode, not the allowlist — do not remove it.
- **Kernel-enforced isolation for `isolate: docker`.** The container mounts the repo `:ro`, runs `--read-only` with a `--tmpfs /tmp`, non-root, memory/pid capped. Writes are refused by the kernel, not by an app flag. The in-container agent has only read/list/grep tools (no write/exec) and confines every file access — including through symlinks — to the mounted repo. On a host timeout the container is `docker kill`ed so a metered API call can't run unsupervised.
- **Keys are never collected.** `moa setup` only detects credential *presence* (a boolean) — it never reads, prints, stores, or transmits a key value. In `run_docker` the key is passed to the container via env (`-e OPENROUTER_API_KEY`, name only), never on the command line.
- **Minimal child environment.** Every child process (CLI or container build/run) receives only a whitelist (`PATH`, `HOME`, `USER`, `SHELL`, `TMPDIR`, `LANG`, `LC_ALL`, `TERM`) so parent API keys are never inherited. `stdin` is closed to prevent CLIs from hanging on an inherited pipe.
- **Secret masking.** Error text surfaced to the user (`[failed: ...]`) is run through a sanitizer that masks `Bearer` tokens, `sk-` keys, and `*_API_KEY=` / `*_TOKEN=` / `*_SECRET=` patterns.

Known limits, stated honestly: write-blocking for `codex`/`claude` is delegated to the child CLI's flags — there is no in-process sandbox or post-run verification (the Docker path *is* kernel-enforced). Any reference sends prompt text — and, for docker/CLI refs, the code it reads — to a remote model, so `:ro` stops writes but not network egress; avoid putting secrets in the prompt.

## Attribution

Ports the Mixture of Agents logic from NousResearch [Hermes Agent](https://github.com/NousResearch/Hermes-Agent) (MIT) — advisory system prompt, parallel fan-out, failure isolation, and the preset/config schema. The aggregator-is-the-current-session design and read-only enforcement are specific to this skill.

## License

[MIT](./LICENSE) © Dante Labs

---

<div align="center">

**Dante Labs** · **YouTube** [@dante-labs](https://youtube.com/@dante-labs) · **Email** [dante@dante-labs.com](mailto:dante@dante-labs.com) · **Discord** [Dante Labs Community](https://discord.com/invite/rXyy5e9ujs) · **Support** [Buy Me a Coffee](https://buymeacoffee.com/dante.labs)

</div>
