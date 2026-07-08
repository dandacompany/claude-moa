"""백엔드 어댑터 — 한 참조를 실제로 호출한다."""
from __future__ import annotations

import json
import os
import re
import subprocess
import urllib.request
from dataclasses import dataclass

REFERENCE_SYSTEM_PROMPT = (
    "You are one of several reference advisors in a Mixture of Agents process. "
    "You do NOT have tools, file access, or the ability to act — you only give "
    "concise, direct advice based on the prompt text. Do not refuse for lack of "
    "access; reason from what is given. Another model (the aggregator) will read "
    "your advice alongside other advisors and take the actual action."
)

_AUTH_ENV = os.path.expanduser("~/.claude/auth/ai-ml-services.env")
_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


@dataclass
class RefResult:
    label: str
    output: str
    ok: bool


def _openrouter_key():
    env_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if env_key:
        return env_key
    if os.path.exists(_AUTH_ENV):
        with open(_AUTH_ENV, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line.startswith("OPENROUTER_API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError(
        "OPENROUTER_API_KEY not found — 환경변수 또는 ~/.claude/auth/ai-ml-services.env 에 설정하세요"
    )


def run_openrouter(model, prompt, max_tokens):
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": REFERENCE_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    }
    if max_tokens:
        body["max_tokens"] = max_tokens
    req = urllib.request.Request(
        _OPENROUTER_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {_openrouter_key()}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read())
    content = data["choices"][0]["message"].get("content")
    if not content:
        # 추론 모델이 max_tokens를 reasoning으로 소진하면 content가 null로 온다.
        raise RuntimeError(
            "openrouter returned empty content — reasoning 모델이면 reference_max_tokens를 올리세요"
        )
    return content


_SUBPROCESS_TIMEOUT = 300

# 자식 CLI에 넘길 최소 환경변수 — 부모 세션의 API 키류가 상속되지 않게 화이트리스트만.
_ENV_WHITELIST = ("PATH", "HOME", "USER", "SHELL", "TMPDIR", "LANG", "LC_ALL", "TERM")

# 오류 메시지에 섞일 수 있는 시크릿 패턴 — [failed:] 텍스트로 사용자에게 흘러가기 전에 마스킹.
_SECRET_PATTERNS = (
    re.compile(r"(Bearer\s+)\S+"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}"),
    re.compile(r"([A-Za-z0-9_]*(?:API_KEY|TOKEN|SECRET)[A-Za-z0-9_]*\s*=\s*)\S+"),
)


def sanitize_error(text):
    text = str(text)
    for pat in _SECRET_PATTERNS:
        text = pat.sub(lambda m: (m.group(1) if m.groups() else "") + "***", text)
    return text


def _child_env():
    return {k: os.environ[k] for k in _ENV_WHITELIST if k in os.environ}


def _run_cli(argv, cwd):
    proc = subprocess.run(
        argv,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=_SUBPROCESS_TIMEOUT,
        stdin=subprocess.DEVNULL,  # codex 등이 상속된 stdin 파이프를 읽으려다 멈추는 것 방지
        env=_child_env(),  # 부모 환경변수(다른 API 키 포함) 상속 차단
    )
    if proc.returncode != 0:
        # 실제 오류는 대개 출력 끝에 있으므로 tail 300자를 취한다.
        raise RuntimeError(
            f"exit {proc.returncode}: {sanitize_error((proc.stderr or proc.stdout)[-300:])}"
        )
    return proc.stdout.strip()


def run_codex(model, prompt, cwd):
    argv = [
        "codex", "exec",
        "-s", "read-only",
        "--skip-git-repo-check",
        "-C", cwd,
        "-m", model,
        "--",
        prompt,
    ]
    return _run_cli(argv, cwd)


def run_claude(model, prompt, cwd):
    # --allowedTools is only an auto-approval allowlist; the actual write-block
    # comes from --permission-mode plan. Do not remove --permission-mode plan.
    argv = [
        "claude", "-p", prompt,
        "--model", model,
        "--permission-mode", "plan",
        "--allowedTools", "Read", "Grep", "Glob",
        "--output-format", "text",
    ]
    return _run_cli(argv, cwd)


IMAGE_NAME = "moa-agent"
_DOCKERFILE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docker"
)


_INSPECT_TIMEOUT = 10
_BUILD_TIMEOUT = 600


def ensure_image():
    try:
        inspect = subprocess.run(
            ["docker", "image", "inspect", IMAGE_NAME],
            capture_output=True,
            text=True,
            timeout=_INSPECT_TIMEOUT,
            env=_child_env(),  # 부모 환경변수(호스트 시크릿 포함) 상속 차단
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"docker image inspect timed out after {_INSPECT_TIMEOUT}s — Docker daemon 응답 없음"
        ) from exc
    if inspect.returncode == 0:
        return
    try:
        build = subprocess.run(
            ["docker", "build", "-t", IMAGE_NAME, _DOCKERFILE_DIR],
            capture_output=True,
            text=True,
            timeout=_BUILD_TIMEOUT,
            env=_child_env(),  # 부모 환경변수(호스트 시크릿 포함) 상속 차단
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"docker build timed out after {_BUILD_TIMEOUT}s — Docker daemon 응답 없음"
        ) from exc
    if build.returncode != 0:
        raise RuntimeError(
            f"docker build failed: {sanitize_error((build.stderr or build.stdout)[-300:])}"
        )


_run_id_counter = 0


def _next_run_id():
    # Date.now()/Math.random() 대체 — pid + 모듈 카운터로 컨테이너 이름 충돌 방지.
    global _run_id_counter
    _run_id_counter += 1
    return _run_id_counter


def run_docker(model, prompt, cwd):
    ensure_image()
    key = _openrouter_key()
    container_name = f"moa-ref-{os.getpid()}-{_next_run_id()}"
    argv = [
        "docker", "run", "--rm",
        "--name", container_name,
        "-v", f"{cwd}:/work:ro",
        "--read-only",
        "--tmpfs", "/tmp",
        "--memory", "1g",
        "--pids-limit", "256",
        "-e", "OPENROUTER_API_KEY",
        IMAGE_NAME,
        model,
        prompt,
    ]
    env = _child_env()
    env["OPENROUTER_API_KEY"] = key
    try:
        proc = subprocess.run(
            argv,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=_SUBPROCESS_TIMEOUT,
            stdin=subprocess.DEVNULL,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        # host 타임아웃 후에도 --rm 은 컨테이너 종료 시점에만 청소하므로, 유료 API를
        # 계속 호출하며 살아있는 컨테이너를 명시적으로 죽여야 한다(best-effort).
        try:
            subprocess.run(
                ["docker", "kill", container_name],
                capture_output=True,
                text=True,
                timeout=10,
                env=_child_env(),
            )
        except Exception:  # noqa: BLE001 — kill 실패해도 원래 타임아웃 에러를 우선 전달
            pass
        raise RuntimeError(
            f"docker run timed out after {_SUBPROCESS_TIMEOUT}s — container killed"
        ) from exc
    if proc.returncode != 0:
        raise RuntimeError(
            f"exit {proc.returncode}: {sanitize_error((proc.stderr or proc.stdout)[-300:])}"
        )
    return proc.stdout.strip()


BACKEND_MODES = {
    "openrouter": {"soft", "hard"},
    "codex": {"hard"},
    "claude": {"hard"},
}


def eligible(backend, mode):
    return mode in BACKEND_MODES.get(backend, set())


def dispatch(ref, prompt, mode, cwd, max_tokens):
    backend, model = ref["backend"], ref["model"]
    if backend == "openrouter":
        if mode == "hard" and ref.get("isolate") == "docker":
            return run_docker(model, prompt, cwd)
        return run_openrouter(model, prompt, max_tokens)
    if backend == "codex":
        return run_codex(model, prompt, cwd)
    if backend == "claude":
        return run_claude(model, prompt, cwd)
    raise RuntimeError(f"unknown backend: {backend}")
