"""팬아웃 오케스트레이션 — 모드 게이팅·병렬·실패 격리·포맷."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from scripts.adapters import RefResult, dispatch, eligible, sanitize_error

_MAX_WORKERS = 8


def call_one(ref, prompt, mode, cwd, max_tokens):
    label = f"{ref['backend']}:{ref['model']}"
    if ref.get("isolate") == "docker" and mode == "hard" and ref["backend"] == "openrouter":
        label += " (docker)"
    if not eligible(ref["backend"], mode):
        return RefResult(label, f"[skipped: {ref['backend']}는 hard 전용]", False)
    try:
        out = dispatch(ref, prompt, mode, cwd, max_tokens)
        return RefResult(label, out, True)
    except Exception as exc:  # noqa: BLE001 — 격리가 목적
        return RefResult(label, f"[failed: {sanitize_error(exc)}]", False)


def format_block(preset_name, mode, results):
    lines = [f"## MoA references — preset: {preset_name}, mode: {mode}", ""]
    for i, r in enumerate(results, start=1):
        lines.append(f"### Reference {i} — {r.label}")
        lines.append(r.output)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def run_fanout(prompt, preset_name, preset, mode, cwd):
    if not preset.get("enabled", True):
        return f"[MoA] preset '{preset_name}' enabled:false — 팬아웃 생략, 집계자 단독 진행.\n"
    refs = preset["references"]
    if not any(eligible(r["backend"], mode) for r in refs):
        return (
            f"[MoA] preset '{preset_name}' (mode: {mode}) 에서 실행할 참조 없음 — "
            "--hard 를 쓰거나 openrouter 참조를 추가하세요.\n"
        )
    max_tokens = preset.get("reference_max_tokens")
    workers = min(_MAX_WORKERS, len(refs))
    results = [None] * len(refs)
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(call_one, ref, prompt, mode, cwd, max_tokens): i for i, ref in enumerate(refs)}
        for fut, i in futs.items():
            results[i] = fut.result()
    return format_block(preset_name, mode, results)
