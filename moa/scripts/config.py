"""MoA 레지스트리 로드 + 정규화/검증 (순수 함수)."""
from __future__ import annotations

import copy
import os
import shutil
import sys

import yaml

VALID_BACKENDS = {"openrouter", "codex", "claude"}

DEFAULT_PRESET = {
    "references": [
        {"backend": "openrouter", "model": "z-ai/glm-5.2"},
        {"backend": "openrouter", "model": "openai/gpt-5.5"},
    ],
    "reference_max_tokens": None,
    "enabled": True,
}

CONFIG_PATH = os.path.expanduser("~/.claude/moa/config.yml")


def clean_ref(raw):
    if not isinstance(raw, dict):
        return None
    backend = str(raw.get("backend", "")).strip().lower()
    model = str(raw.get("model", "")).strip()
    if backend not in VALID_BACKENDS or not model:
        return None
    return {"backend": backend, "model": model}


def _coerce_int_or_none(v):
    try:
        n = int(v)
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def normalize_preset(raw):
    raw = raw if isinstance(raw, dict) else {}
    refs_in = raw.get("references")
    if isinstance(refs_in, dict):
        refs_in = [refs_in]
    if not isinstance(refs_in, list):
        refs_in = []
    refs = [r for r in (clean_ref(x) for x in refs_in) if r]
    if not refs:
        refs = copy.deepcopy(DEFAULT_PRESET["references"])
    return {
        "references": refs,
        "reference_max_tokens": _coerce_int_or_none(raw.get("reference_max_tokens")),
        "enabled": bool(raw.get("enabled", True)),
    }


def normalize_config(raw):
    raw = raw if isinstance(raw, dict) else {}
    presets_in = raw.get("presets")
    if not isinstance(presets_in, dict) or not presets_in:
        presets_in = {"default": copy.deepcopy(DEFAULT_PRESET)}
    presets = {name: normalize_preset(p) for name, p in presets_in.items()}
    default = raw.get("default_preset")
    if default not in presets:
        default = next(iter(presets))
    return {"default_preset": default, "presets": presets}


def resolve_preset(config, name):
    presets = config["presets"]
    if not name or name not in presets:
        name = config["default_preset"]
    return name, presets[name]


def load_config(path=None):
    path = path or CONFIG_PATH
    if not os.path.exists(path):
        example = os.path.join(os.path.dirname(os.path.dirname(__file__)), "presets.example.yml")
        if os.path.exists(example) and path == CONFIG_PATH:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            shutil.copyfile(example, path)
    raw = {}
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as fh:
                raw = yaml.safe_load(fh) or {}
        except yaml.YAMLError as exc:
            reason = str(exc).splitlines()[0] if str(exc) else repr(exc)
            print(
                f"[MoA] config.yml 파싱 실패 — 기본 프리셋으로 진행: {reason}",
                file=sys.stderr,
            )
            raw = {}
    return normalize_config(raw)
