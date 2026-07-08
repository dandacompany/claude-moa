"""MoA Docker 참조 에이전트 — openrouter 모델 + 읽기전용 tool 루프.

컨테이너가 /work 를 :ro 로 마운트하므로 쓰기는 커널이 막는다.
이 루프는 read/list/grep 만 노출하는 '단순 에이전트'로 충분하다 — 격리는 OS가 보장.
stdlib 만 사용(urllib). OPENROUTER_API_KEY 는 env 로 주입된다.

하드닝 포인트(프로토타입 대비):
  1) 강제형 시스템 프롬프트 — tool 사용 없이 추측 답변 금지.
  2) max_turns 도달 시 마지막 모델 텍스트가 있으면 그것을 반환(빈 문자열 대신).
  3) tool arguments 파싱 실패 / 미존재 tool 이름 방어 — 크래시 없이 [tool error: ...] 반환.
  4) 경로 /work 밖 접근 차단(_safe) — 마운트가 이미 :ro 지만 심층 방어로 유지.
"""
import json
import os
import re
import sys
import urllib.error
import urllib.request

WORK = "/work"
_URL = "https://openrouter.ai/api/v1/chat/completions"
_MAX_TURNS = 8

SYSTEM = (
    "You are a read-only reference reviewer running in an isolated container. "
    "The repository is mounted at /work and is READ-ONLY at the kernel level — "
    "you cannot modify anything, so do not try.\n\n"
    "MANDATORY: You MUST call at least one of the tools (list_files, read_file, grep) "
    "to inspect the actual repository contents BEFORE giving any answer. "
    "NEVER answer from assumption, prior training knowledge, or guesswork about what "
    "the code 'probably' looks like. If a question is vague or broad, use list_files "
    "and grep to explore first, then read_file on the relevant files. Only after you "
    "have concrete evidence from the tools may you produce your final analysis — cite "
    "what you actually read (file paths, line numbers, or quoted snippets)."
)

TOOLS = [
    {"type": "function", "function": {
        "name": "list_files", "description": "List files under /work (optional glob).",
        "parameters": {"type": "object", "properties": {"glob": {"type": "string"}}}}},
    {"type": "function", "function": {
        "name": "read_file", "description": "Read a file's text content (path under /work).",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}},
    {"type": "function", "function": {
        "name": "grep", "description": "Search a regex across files under /work.",
        "parameters": {"type": "object", "properties": {"pattern": {"type": "string"}}, "required": ["pattern"]}}},
]


def _safe(path):
    # /work 밖 접근 차단(심층 방어 — 마운트가 이미 :ro 지만 경로 이탈도 막는다)
    p = os.path.realpath(os.path.join(WORK, path.lstrip("/")))
    return p if p == WORK or p.startswith(WORK + os.sep) else None


def _walk():
    out = []
    for root, dirs, files in os.walk(WORK):
        dirs[:] = [d for d in dirs if d != ".git"]
        for f in files:
            out.append(os.path.relpath(os.path.join(root, f), WORK))
    return out


def tool_list_files(args):
    import fnmatch
    files = _walk()
    g = args.get("glob")
    if g:
        files = [f for f in files if fnmatch.fnmatch(f, g)]
    return "\n".join(sorted(files)) or "(no files)"


def tool_read_file(args):
    p = _safe(args.get("path", ""))
    if not p or not os.path.isfile(p):
        return f"[error: not found: {args.get('path')}]"
    with open(p, encoding="utf-8", errors="replace") as fh:
        return fh.read()[:20000]


def tool_grep(args):
    pat = re.compile(args["pattern"])
    hits = []
    for rel in _walk():
        # read_file 과 동일한 심층 방어: 심링크 파일이 /work 밖(예: evil -> /etc/shadow)을
        # 가리키면 realpath 가 /work 를 벗어나므로 skip — 읽기 이탈 유출 차단.
        p = _safe(rel)
        if not p or not os.path.isfile(p):
            continue
        try:
            with open(p, encoding="utf-8", errors="replace") as fh:
                for i, line in enumerate(fh, 1):
                    if pat.search(line):
                        hits.append(f"{rel}:{i}: {line.rstrip()}")
        except OSError:
            pass
    return "\n".join(hits[:100]) or "(no matches)"


DISPATCH = {"list_files": tool_list_files, "read_file": tool_read_file, "grep": tool_grep}


def _post(body):
    req = urllib.request.Request(
        _URL, data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}",
                 "Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"openrouter HTTP {exc.code}: {exc.reason}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"openrouter network error: {exc}") from exc


def _run_tool(fn, raw_args):
    """미존재 tool 이름 / 잘못된 JSON 인자를 방어적으로 처리한다. 절대 예외를 전파하지 않는다."""
    handler = DISPATCH.get(fn)
    if handler is None:
        return f"[tool error: unknown tool '{fn}']"
    try:
        args = json.loads(raw_args) if raw_args else {}
    except (json.JSONDecodeError, TypeError) as exc:
        return f"[tool error: malformed arguments for '{fn}': {exc}]"
    try:
        return handler(args)
    except Exception as exc:  # noqa: BLE001 — tool 실행 실패는 루프를 죽이지 않는다
        return f"[tool error: {fn} failed: {exc}]"


def run(model, prompt):
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}]
    last_text = None
    for _ in range(_MAX_TURNS):
        data = _post({"model": model, "messages": messages, "tools": TOOLS})
        if "choices" not in data:
            raise RuntimeError(f"openrouter error: {str(data)[:300]}")
        msg = data["choices"][0]["message"]
        if msg.get("content"):
            last_text = msg["content"]
        calls = msg.get("tool_calls")
        if not calls:
            return msg.get("content") or "[empty]"
        messages.append(msg)
        for c in calls:
            fn = c["function"]["name"]
            result = _run_tool(fn, c["function"].get("arguments"))
            messages.append({"role": "tool", "tool_call_id": c["id"], "content": result[:8000]})
    # max_turns 도달 — 마지막에 모델이 낸 텍스트가 있으면 그걸 반환(정보 손실 최소화)
    return last_text if last_text else "[max turns reached]"


if __name__ == "__main__":
    print(run(sys.argv[1], sys.argv[2]))
