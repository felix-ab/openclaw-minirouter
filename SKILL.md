---
name: minimal-model-router
description: Deterministic regex-first model routing via minirouter.py for OpenClaw requests.
---

# Minimal Model Router

Use this skill when model selection should be deterministic, low-latency, and driven by local routing rules.

OpenClaw does not auto-run this router. The assistant must execute the script, read the JSON result, then choose models accordingly.

## Commands

```bash
"{baseDir}/minirouter.py" route <text...>
"{baseDir}/minirouter.py" selfcheck
"{baseDir}/minirouter.py" test
```

If executable permission is missing, use:

```bash
python3 "{baseDir}/minirouter.py" route <text...>
```

## Route output contract

`route` returns exactly one JSON line with keys:

- `label`
- `mode` (`"OK"` or `"SAFE_MODE"`)
- `tier`
- `primary_model`
- `fallbacks`
- `notes` (only when `mode` is `"SAFE_MODE"`)
- `text`
- `text_hash`
- `len_chars`

Use `primary_model` first and `fallbacks` in order.

## SAFE_MODE handling

If `mode` is `"SAFE_MODE"`:

1. Do not provide runnable commands.
2. Ask the user to resend the same request with `/confirm <confirm_token> <same request>`.
3. Use the exact token from `notes.confirm_token`.

If `mode` is `"OK"`, continue normally with the selected model route.

## Environment toggles

- `MINIROUTER_NO_CLOUD=1` forces local-only `ollama/*` outputs.
- `MINIROUTER_DEBUG=1` includes a redacted preview in `text`.
