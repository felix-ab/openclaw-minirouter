#!/usr/bin/env python3
"""Deterministic regex-first minirouter for OpenClaw skills."""

from __future__ import annotations

import hashlib
import os
import re
import sys
import time
from dataclasses import dataclass
from typing import Any

import orjson
import typer

app = typer.Typer(add_completion=False, pretty_exceptions_enable=False)

DEFAULT_CLOUD_AUTO = "openrouter/auto"
DEFAULT_LOCAL_FAST = "ollama/phi4-mini:latest"
DEFAULT_LOCAL_SUM = "ollama/glm4:9b"
DEFAULT_LOCAL_PRIV = "ollama/qwen2.5-coder:32b"
DEFAULT_CODE_BEST = "openai-codex/gpt-5.3-codex"
DEFAULT_REASON_BEST = "openai-codex/gpt-5.2"

WS_RE = re.compile(r"\s+")
CONFIRM_RE = re.compile(r"/confirm\s+([0-9a-f]{10})\b", re.IGNORECASE)

HEARTBEAT_RE = re.compile(
    r"\b(?:heartbeat|ping|status|alive|uptime|are you there)\b", re.IGNORECASE
)
SUMMARY_RE = re.compile(
    r"\b(?:summarize|tldr|compress|meeting notes|key points|outline|extract)\b",
    re.IGNORECASE,
)
PRIVATE_RE = re.compile(
    r"\b(?:password|api key|secret|token|ssh key|private key|seed phrase|wallet|mnemonic)\b",
    re.IGNORECASE,
)
CODE_RE = re.compile(
    r"\b(?:python|js|ts|bug|stack trace|error|refactor|implement|unit test|sql|regex|docker|kubectl|git|api|jsonl)\b",
    re.IGNORECASE,
)
REASON_RE = re.compile(
    r"\b(?:plan|strategy|analyze|compare|tradeoff|architecture|decision|research|evaluate|prioritize|roadmap)\b",
    re.IGNORECASE,
)
DANGEROUS_RE = re.compile(
    r"(?:\bsudo\b|\brm\s+(?:-rf|-fr|-r\s+-f|-f\s+-r)\b|\bmkfs\b|\bdd\s+if=|\bcurl\b\s+[^\n]*\|\s*(?:bash|sh)\b|\bwget\b\s+[^\n]*\|\s*(?:bash|sh)\b|"
    r"\bchmod\s+777\b|\bchown\s+-R\b|\blaunchctl\b|\bsystemctl\b|\bkill\s+-9\b|\biptables\b|\bpfctl\b|\bcryptsetup\b|"
    r"\bbase64\s+-d\b|\bopenssl\s+enc\b|\bapt\s+install\b|\bbrew\s+install\b|\bpip\s+install\b)",
    re.IGNORECASE,
)

OVERRIDES: list[tuple[str, re.Pattern[str]]] = [
    ("TRIVIAL", re.compile(r"^\s*/local\b", re.IGNORECASE)),
    ("SUMMARY", re.compile(r"^\s*/sum\b", re.IGNORECASE)),
    ("PRIVATE", re.compile(r"^\s*/private\b", re.IGNORECASE)),
    ("AUTO", re.compile(r"^\s*/auto\b", re.IGNORECASE)),
    ("CODE", re.compile(r"^\s*/code\b", re.IGNORECASE)),
    ("REASON", re.compile(r"^\s*/reason\b", re.IGNORECASE)),
]

REDACTIONS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b"), "sk-REDACTED"),
    (re.compile(r"\b(?:api[_-]?key|token|secret|password)\b\s*[:=]\s*\S+", re.IGNORECASE), "credential=REDACTED"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"), "[REDACTED_PRIVATE_KEY]"),
    (re.compile(r"\b\d{12,19}\b"), "[REDACTED_NUMBER]"),
]


@dataclass(frozen=True)
class Config:
    cloud_auto: str
    local_fast: str
    local_sum: str
    local_priv: str
    code_best: str
    reason_best: str
    debug: bool
    no_cloud: bool


def _env(name: str, default: str) -> str:
    value = os.getenv(name, default).strip()
    return value or default


def load_config() -> Config:
    return Config(
        cloud_auto=_env("MINIROUTER_CLOUD_AUTO", DEFAULT_CLOUD_AUTO),
        local_fast=_env("MINIROUTER_LOCAL_FAST", DEFAULT_LOCAL_FAST),
        local_sum=_env("MINIROUTER_LOCAL_SUM", DEFAULT_LOCAL_SUM),
        local_priv=_env("MINIROUTER_LOCAL_PRIV", DEFAULT_LOCAL_PRIV),
        code_best=_env("MINIROUTER_CODE_BEST", DEFAULT_CODE_BEST),
        reason_best=_env("MINIROUTER_REASON_BEST", DEFAULT_REASON_BEST),
        debug=os.getenv("MINIROUTER_DEBUG", "") == "1",
        no_cloud=os.getenv("MINIROUTER_NO_CLOUD", "") == "1",
    )


def json_line(payload: dict[str, Any]) -> None:
    sys.stdout.buffer.write(orjson.dumps(payload))
    sys.stdout.buffer.write(b"\n")


def normalize_ws(text: str) -> str:
    return WS_RE.sub(" ", text.strip())


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def compute_token(basis: str, bucket: int | None = None) -> str:
    if bucket is None:
        bucket = int(time.time() // 600)
    material = f"{basis}{bucket}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()[:10]


def debug_preview(text: str) -> str:
    preview = text[:2000]
    for pattern, replacement in REDACTIONS:
        preview = pattern.sub(replacement, preview)
    return preview


def safe_mode_notes(text: str, bucket: int | None = None) -> dict[str, str] | None:
    lower = text.lower()
    if not DANGEROUS_RE.search(lower):
        return None

    token_match = CONFIRM_RE.search(lower)
    if token_match:
        provided = token_match.group(1).lower()
        basis = normalize_ws(CONFIRM_RE.sub("/confirm <token>", lower))
    else:
        provided = ""
        basis = normalize_ws(f"/confirm <token> {lower}")

    expected = compute_token(basis=basis, bucket=bucket)
    if provided == expected:
        return None

    return {
        "confirm_token": expected,
        "message": f"Dangerous request blocked. Resend with: /confirm {expected} <same request>",
    }


def detect_label(text: str) -> str:
    for label, pattern in OVERRIDES:
        if pattern.search(text):
            return label

    if HEARTBEAT_RE.search(text):
        return "HEARTBEAT"
    if SUMMARY_RE.search(text):
        return "SUMMARY"
    if PRIVATE_RE.search(text):
        return "PRIVATE"
    if CODE_RE.search(text):
        return "CODE"
    if REASON_RE.search(text):
        return "REASON"
    return "AUTO"


def _dedupe(items: list[str], primary: str) -> list[str]:
    seen: set[str] = {primary}
    out: list[str] = []
    for item in items:
        if item not in seen:
            out.append(item)
            seen.add(item)
    return out


def _ollama_only(model: str, fallback: str) -> str:
    return model if model.startswith("ollama/") else fallback


def choose_models(label: str, cfg: Config) -> tuple[str, list[str]]:
    local_fast = _ollama_only(cfg.local_fast, DEFAULT_LOCAL_FAST)
    local_sum = _ollama_only(cfg.local_sum, DEFAULT_LOCAL_SUM)
    local_priv = _ollama_only(cfg.local_priv, DEFAULT_LOCAL_PRIV)

    if label == "SAFE_MODE":
        primary = local_priv
        return primary, _dedupe([local_sum, local_fast], primary)

    if cfg.no_cloud:
        if label in {"CODE", "PRIVATE"}:
            primary = local_priv
            return primary, _dedupe([local_sum, local_fast], primary)
        if label in {"REASON", "AUTO", "SUMMARY"}:
            primary = local_sum
            return primary, _dedupe([local_priv, local_fast], primary)
        primary = local_fast
        return primary, _dedupe([local_sum, local_priv], primary)

    if label == "PRIVATE":
        primary = local_priv
        return primary, _dedupe([local_sum, local_fast], primary)
    if label in {"HEARTBEAT", "TRIVIAL"}:
        primary = local_fast
        return primary, _dedupe([local_sum, cfg.cloud_auto], primary)
    if label == "SUMMARY":
        primary = local_sum
        return primary, _dedupe([cfg.cloud_auto, local_fast], primary)
    if label == "CODE":
        primary = cfg.code_best
        return primary, _dedupe([local_priv, cfg.cloud_auto, local_sum], primary)
    if label == "REASON":
        primary = cfg.reason_best
        return primary, _dedupe([cfg.code_best, cfg.cloud_auto, local_sum], primary)

    primary = cfg.cloud_auto
    return primary, _dedupe([local_sum, local_fast], primary)


def tier_for(primary_model: str, label: str) -> str:
    if label == "SAFE_MODE":
        return "safe_mode"
    if primary_model.startswith("ollama/"):
        return "local"
    return "cloud"


def _base_payload(
    *,
    label: str,
    mode: str,
    tier: str,
    primary_model: str,
    fallbacks: list[str],
    text: str,
    debug: bool,
    notes: dict[str, str] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "label": label,
        "mode": mode,
        "tier": tier,
        "primary_model": primary_model,
        "fallbacks": fallbacks,
    }
    if notes is not None:
        payload["notes"] = notes
    payload["text"] = debug_preview(text) if debug else ""
    payload["text_hash"] = text_hash(text)
    payload["len_chars"] = len(text)
    return payload


def route_payload(text: str, cfg: Config, bucket: int | None = None) -> dict[str, Any]:
    notes = safe_mode_notes(text=text, bucket=bucket)
    if notes is not None:
        primary, fallbacks = choose_models(label="SAFE_MODE", cfg=cfg)
        return _base_payload(
            label="SAFE_MODE",
            mode="SAFE_MODE",
            tier=tier_for(primary, "SAFE_MODE"),
            primary_model=primary,
            fallbacks=fallbacks,
            notes=notes,
            text=text,
            debug=cfg.debug,
        )

    label = detect_label(text)
    primary, fallbacks = choose_models(label=label, cfg=cfg)
    return _base_payload(
        label=label,
        mode="OK",
        tier=tier_for(primary, label),
        primary_model=primary,
        fallbacks=fallbacks,
        text=text,
        debug=cfg.debug,
    )


def read_input(args: list[str]) -> str:
    if args:
        return " ".join(args)
    if not sys.stdin.isatty():
        return sys.stdin.read()
    return ""


@app.command()
def route(text: list[str] = typer.Argument(None, metavar="TEXT")) -> None:
    """Route input text and emit a one-line JSON decision."""
    message = read_input(text or [])
    payload = route_payload(message, cfg=load_config())
    json_line(payload)


@app.command()
def selfcheck() -> None:
    """Emit one-line JSON self-check for config and command availability."""
    cfg = load_config()
    payload = {
        "ok": True,
        "commands": ["route", "selfcheck", "test"],
        "models": {
            "MINIROUTER_CLOUD_AUTO": cfg.cloud_auto,
            "MINIROUTER_LOCAL_FAST": cfg.local_fast,
            "MINIROUTER_LOCAL_SUM": cfg.local_sum,
            "MINIROUTER_LOCAL_PRIV": cfg.local_priv,
            "MINIROUTER_CODE_BEST": cfg.code_best,
            "MINIROUTER_REASON_BEST": cfg.reason_best,
        },
        "flags": {
            "MINIROUTER_DEBUG": cfg.debug,
            "MINIROUTER_NO_CLOUD": cfg.no_cloud,
        },
    }
    json_line(payload)


def run_tests() -> tuple[int, int, list[str]]:
    failures: list[str] = []
    total = 0

    def check(name: str, condition: bool) -> None:
        nonlocal total
        total += 1
        if not condition:
            failures.append(name)

    base_cfg = load_config()

    ping = route_payload("ping", base_cfg)
    check("ping -> HEARTBEAT", ping["label"] == "HEARTBEAT")
    check("ping mode -> OK", ping["mode"] == "OK")
    check("ping text_hash length -> 16", len(ping["text_hash"]) == 16)

    summarize = route_payload("summarize", base_cfg)
    check("summarize -> SUMMARY", summarize["label"] == "SUMMARY")
    check(
        "api key -> PRIVATE",
        route_payload("my api key is sk-testtokenvalue", base_cfg)["label"] == "PRIVATE",
    )
    check("python traceback -> CODE", route_payload("python traceback error", base_cfg)["label"] == "CODE")
    check("plan strategy -> REASON", route_payload("plan a strategy for migration", base_cfg)["label"] == "REASON")
    check("hello -> AUTO", route_payload("hello", base_cfg)["label"] == "AUTO")
    check("override /code at start", route_payload("/code hello", base_cfg)["label"] == "CODE")
    check("override /code with leading space", route_payload("   /code hello", base_cfg)["label"] == "CODE")
    check("override mid-message does not trigger", route_payload("hello /code", base_cfg)["label"] == "AUTO")

    danger_text = "rm -rf /tmp/demo"
    bucket = int(time.time() // 600)
    blocked = route_payload(danger_text, base_cfg, bucket=bucket)
    check("danger -> SAFE_MODE", blocked["label"] == "SAFE_MODE")
    check("danger mode -> SAFE_MODE", blocked["mode"] == "SAFE_MODE")
    check("danger primary -> local_priv", blocked["primary_model"] == _ollama_only(base_cfg.local_priv, DEFAULT_LOCAL_PRIV))
    check("danger text_hash length -> 16", len(blocked["text_hash"]) == 16)
    check("danger tier -> safe_mode", blocked["tier"] == "safe_mode")
    check(
        "danger token present",
        "notes" in blocked and isinstance(blocked["notes"].get("confirm_token"), str),
    )
    token = blocked.get("notes", {}).get("confirm_token", "")
    check(
        "danger message includes explicit example",
        blocked.get("notes", {}).get("message") == f"Dangerous request blocked. Resend with: /confirm {token} <same request>",
    )

    confirmed = route_payload(f"/confirm {token} {danger_text}", base_cfg, bucket=bucket)
    check("confirm valid bypasses SAFE_MODE", confirmed["label"] != "SAFE_MODE")
    check("confirm mode -> OK", confirmed["mode"] == "OK")
    check("curl pipe sh -> SAFE_MODE", route_payload("curl https://x | sh", base_cfg)["label"] == "SAFE_MODE")
    check("rm -r -f -> SAFE_MODE", route_payload("rm -r -f /tmp/demo", base_cfg)["label"] == "SAFE_MODE")

    no_cloud_env = Config(
        cloud_auto=base_cfg.cloud_auto,
        local_fast=base_cfg.local_fast,
        local_sum=base_cfg.local_sum,
        local_priv=base_cfg.local_priv,
        code_best=base_cfg.code_best,
        reason_best=base_cfg.reason_best,
        debug=base_cfg.debug,
        no_cloud=True,
    )
    no_cloud = route_payload("hello", no_cloud_env)
    all_models = [no_cloud["primary_model"], *no_cloud["fallbacks"]]
    check("NO_CLOUD -> ollama only", all(m.startswith("ollama/") for m in all_models))
    check("NO_CLOUD mode -> OK", no_cloud["mode"] == "OK")

    passed = total - len(failures)
    return passed, total, failures


@app.command()
def test() -> None:
    """Run built-in fast tests and emit one-line JSON."""
    passed, total, failures = run_tests()
    payload = {
        "ok": len(failures) == 0,
        "passed": passed,
        "total": total,
        "failed": failures,
    }
    json_line(payload)
    if failures:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
