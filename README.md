# openclaw-minirouter

Minimal deterministic OpenClaw routing skill. Local CLI, one-line JSON output, no network/subprocess/file-write behavior at runtime.

## OpenClaw discovery requirements

- Skill folder name should be `minimal-model-router`.
- `SKILL.md` must include YAML frontmatter with `name` and `description`.
- Install into `~/.openclaw/skills/minimal-model-router` (shared) or `<workspace>/skills/minimal-model-router` (workspace-local).
- OpenClaw snapshots eligible skills per session, so start a new session (or refresh skills/restart gateway) after install or edits.
- Run `openclaw skills list` on the same host where OpenClaw is running.

## Install

```bash
mkdir -p ~/.openclaw/skills
rm -rf ~/.openclaw/skills/minimal-model-router
git clone https://github.com/felix-ab/openclaw-minirouter.git ~/.openclaw/skills/minimal-model-router
chmod +x ~/.openclaw/skills/minimal-model-router/minirouter.py
python3 -m pip install --upgrade --user pip
python3 -m pip install --upgrade --user typer orjson
cd ~/.openclaw/skills/minimal-model-router
./minirouter.py test
```

Alternative:

```bash
mkdir -p ~/.openclaw/skills
rm -rf ~/.openclaw/skills/minimal-model-router
cp -R . ~/.openclaw/skills/minimal-model-router
chmod +x ~/.openclaw/skills/minimal-model-router/minirouter.py
python3 -m pip install --upgrade --user pip
python3 -m pip install --upgrade --user typer orjson
cd ~/.openclaw/skills/minimal-model-router
./minirouter.py test
```

## Uninstall

```bash
rm -rf ~/.openclaw/skills/minimal-model-router/
```

## Quick toggles

- `MINIROUTER_NO_CLOUD=1`: hard local-only routing (`ollama/*` for primary and fallbacks).
- `MINIROUTER_DEBUG=1`: include redacted preview text in `text` (otherwise `text` is empty).

## ChatGPT subscription (OpenAI Codex OAuth) setup

```bash
openclaw onboard --auth-choice openai-codex
openclaw models set openai-codex/gpt-5.3-codex
```

The router only outputs model IDs; OpenClaw must already be authenticated for `openai-codex/*` models via OAuth.

No-API-fees path with ChatGPT OAuth models:

- `MINIROUTER_CODE_BEST=openai-codex/gpt-5.3-codex`
- `MINIROUTER_REASON_BEST=openai-codex/gpt-5.2`
- Optional: `MINIROUTER_CLOUD_AUTO=openai-codex/gpt-5.3-codex` (zero OpenRouter usage)

Default remains `MINIROUTER_CLOUD_AUTO=openrouter/auto`.

## OpenRouter + Ollama hybrid setup (default)

```bash
export MINIROUTER_CLOUD_AUTO=openrouter/auto
export MINIROUTER_LOCAL_FAST=ollama/phi4-mini:latest
export MINIROUTER_LOCAL_SUM=ollama/glm4:9b
export MINIROUTER_LOCAL_PRIV=ollama/qwen2.5-coder:32b
export MINIROUTER_CODE_BEST=openai-codex/gpt-5.3-codex
export MINIROUTER_REASON_BEST=openai-codex/gpt-5.2
```

## Commands

```bash
./minirouter.py route <text...>
./minirouter.py selfcheck
./minirouter.py test
```

## Route JSON contract

`route` always returns one-line JSON in this key order:

- `label`
- `mode` (`"OK"` or `"SAFE_MODE"`)
- `tier` (`"local"`, `"cloud"`, or `"safe_mode"`)
- `primary_model`
- `fallbacks`
- `notes` (only when `mode` is `"SAFE_MODE"`)
- `text` (empty unless `MINIROUTER_DEBUG=1`)
- `text_hash` (first 16 hex chars of sha256 input)
- `len_chars`

## Examples

Manual overrides (must be first token):

```bash
./minirouter.py route "/local quick check"
./minirouter.py route "/sum summarize this transcript"
./minirouter.py route "/private rotate this secret"
./minirouter.py route "/auto default route"
./minirouter.py route "/code fix traceback"
./minirouter.py route "/reason compare designs"
```

SAFE_MODE confirm flow (token rotates every ~10 minutes; confirmation must match):

```bash
./minirouter.py route "sudo rm -rf /var/tmp/example"
# use returned notes.confirm_token:
./minirouter.py route "/confirm <confirm_token> sudo rm -rf /var/tmp/example"
```

NO_CLOUD (ollama-only models):

```bash
MINIROUTER_NO_CLOUD=1 ./minirouter.py route "plan migration"
```

DEBUG preview (regex redaction, max 2000 chars):

```bash
MINIROUTER_DEBUG=1 ./minirouter.py route "my api key is sk-exampletoken"
```
