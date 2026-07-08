"""MoA 팬아웃 CLI 진입 — 관점을 수집해 현재 세션(집계자)에게 반환."""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import time

import yaml

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from scripts import config as config_module
from scripts import setup as setup_module
from scripts.config import load_config, resolve_preset
from scripts.fanout import run_fanout

_SYNTHESIS_HINT = (
    "\n---\n집계자(현재 세션) 지침: 먼저 각 참조의 핵심 관점을 `Reference N — backend:model` "
    "라벨과 함께 사용자에게 그대로 보여줘라(도구 결과에 묻히지 않게 네 응답 본문에 포함). "
    "그다음 종합하라: 합의점·이견·놓친 점을 대조하고, 이견은 논거로 판정하며, "
    "[failed:]·[skipped:] 참조는 부분 정보로 취급한다. 참조를 맹신하지 말고 "
    "집계자가 최종 판단해 전체 도구로 행동하라.\n"
)


def parse_args(argv):
    p = argparse.ArgumentParser(prog="moa", description="Mixture of Agents 관점 팬아웃")
    p.add_argument("prompt", nargs="+", help="참조들에게 던질 프롬프트")
    p.add_argument("--hard", action="store_true", help="읽기전용 독립세션 팬아웃(codex/claude 포함)")
    p.add_argument("--preset", default=None, help="레지스트리 프리셋 이름")
    p.add_argument("--refs-only", action="store_true", help="집계 지침 없이 관점 묶음만 출력")
    p.add_argument("--config", default=None, help="레지스트리 경로 오버라이드")
    return p.parse_args(argv)


def _parse_setup_args(argv):
    p = argparse.ArgumentParser(prog="moa setup", description="MoA 온보딩 설정")
    p.add_argument("--config", default=None, help="config.yml 경로 오버라이드")
    return p.parse_args(argv)


def run_setup(argv):
    ns = _parse_setup_args(argv)
    path = ns.config or config_module.CONFIG_PATH

    detected = setup_module.detect()
    sys.stdout.write(setup_module.render_report(detected) + "\n")

    cfg = setup_module.recommend_config(detected)

    if os.path.exists(path):
        ts = time.strftime("%Y%m%d-%H%M%S")
        backup_path = f"{path}.bak-{ts}"
        shutil.copyfile(path, backup_path)
        sys.stdout.write(f"기존 설정을 {backup_path}로 백업했습니다.\n")

    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)

    with open(path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(cfg, fh, allow_unicode=True, sort_keys=False)

    sys.stdout.write(
        f"설정을 {path}에 기록했습니다. 변경: /moa setup 재실행 또는 파일 편집.\n"
    )
    return 0


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if argv and argv[0] == "setup":
        return run_setup(argv[1:])

    ns = parse_args(argv)
    prompt = " ".join(ns.prompt)
    mode = "hard" if ns.hard else "soft"
    cfg = load_config(ns.config)
    preset_name, preset = resolve_preset(cfg, ns.preset)
    block = run_fanout(prompt, preset_name, preset, mode=mode, cwd=os.getcwd())
    sys.stdout.write(block)
    if not ns.refs_only:
        sys.stdout.write(_SYNTHESIS_HINT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
