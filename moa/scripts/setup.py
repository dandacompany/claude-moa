"""`/moa setup` 온보딩 — 프로바이더 감지 + config 추천 + 안내 리포트.

보안 원칙: API 키 "값"은 절대 읽거나 저장하거나 출력하지 않는다. 오직 존재 여부(bool)만 판단한다.
"""
from __future__ import annotations

import copy
import os
import shutil
import subprocess

from scripts.config import DEFAULT_PRESET

_AUTH_ENV = os.path.expanduser("~/.claude/auth/ai-ml-services.env")
_CODEX_AUTH = os.path.expanduser("~/.codex/auth.json")
_DOCKER_TIMEOUT = 5


def _detect_docker():
    if not shutil.which("docker"):
        return False
    try:
        proc = subprocess.run(
            ["docker", "version"],
            capture_output=True,
            timeout=_DOCKER_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0


def _detect_openrouter():
    # 존재 여부만 판단 — 값은 어떤 변수에도 보관하지 않는다.
    if bool(os.environ.get("OPENROUTER_API_KEY", "").strip()):
        return True
    if os.path.exists(_AUTH_ENV):
        with open(_AUTH_ENV, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line.startswith("OPENROUTER_API_KEY=") and line.split("=", 1)[1].strip():
                    return True
    return False


def _detect_codex():
    return os.path.exists(_CODEX_AUTH)


def _detect_claude():
    return bool(shutil.which("claude"))


def detect():
    """각 프로바이더의 사용 가능 여부를 bool로만 판단한다 (키 값은 절대 다루지 않음)."""
    return {
        "docker": _detect_docker(),
        "openrouter": _detect_openrouter(),
        "codex": _detect_codex(),
        "claude": _detect_claude(),
    }


def recommend_config(detected):
    """감지 결과로 normalize_config 형태의 config dict를 추천한다."""
    presets = {
        "default": copy.deepcopy(DEFAULT_PRESET),
    }

    review_refs = []
    if detected.get("claude"):
        review_refs.append({"backend": "claude", "model": "claude-opus-4-8"})
    if detected.get("codex"):
        review_refs.append({"backend": "codex", "model": "gpt-5.5"})
    if detected.get("openrouter"):
        isolate = "docker" if detected.get("docker") else "none"
        review_refs.append(
            {"backend": "openrouter", "model": "z-ai/glm-5.2", "isolate": isolate}
        )

    if review_refs:
        presets["review"] = {
            "references": review_refs,
            "reference_max_tokens": 2000,
            "enabled": True,
        }

    return {
        "default_preset": "default",
        "presets": presets,
    }


_GUIDANCE = {
    "openrouter": (
        "OPENROUTER_API_KEY가 감지되지 않았습니다. 별도 터미널에서 쉘 프로필(예: ~/.zshrc)에 "
        "`export OPENROUTER_API_KEY=...`를 추가하거나, ~/.claude/auth/ai-ml-services.env 파일에 "
        "`OPENROUTER_API_KEY=...` 줄을 추가하세요. 이 대화창에는 키 값을 붙여넣지 마세요."
    ),
    "codex": (
        "codex CLI 로그인이 감지되지 않았습니다. ChatGPT 구독이 있다면 별도 터미널에서 "
        "`codex login`을 실행해 로그인하세요."
    ),
    "claude": (
        "claude CLI가 감지되지 않았습니다. Claude 구독이 있다면 별도 터미널에서 Claude Code에 "
        "로그인/설치 후 다시 확인하세요."
    ),
    "docker": (
        "docker가 감지되지 않았습니다. Docker Desktop을 설치하거나 데몬을 시작한 뒤 "
        "별도 터미널에서 `docker version`으로 확인하세요."
    ),
}

_LABELS = {
    "docker": "Docker",
    "openrouter": "OpenRouter",
    "codex": "Codex CLI",
    "claude": "Claude Code CLI",
}


def render_report(detected):
    """감지 결과를 사람이 읽을 리포트 문자열로 렌더링한다. 키 값은 절대 포함하지 않는다."""
    lines = []
    for key in ("docker", "openrouter", "codex", "claude"):
        ok = bool(detected.get(key))
        mark = "✅" if ok else "⚠️"
        lines.append(f"{mark} {_LABELS[key]}: {'감지됨' if ok else '미감지'}")

    missing = [k for k in ("docker", "openrouter", "codex", "claude") if not detected.get(k)]
    if missing:
        lines.append("")
        lines.append("설정 안내:")
        for key in missing:
            lines.append(f"- {_GUIDANCE[key]}")

    return "\n".join(lines)
