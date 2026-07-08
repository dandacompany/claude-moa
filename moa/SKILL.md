---
name: moa
description: Mixture of Agents 관점 팬아웃 — 여러 모델을 병렬 참조로 돌려 분석을 수집하고 현재 Claude 세션이 종합하게 한다. soft는 openrouter 조언 전용, hard는 codex·claude 읽기전용 독립세션까지. 트리거 moa로 검토, 여러 모델 관점, mixture of agents.
---

# moa — Mixture of Agents 관점 팬아웃

## 정체

이 스킬은 **집계자가 아니라 관점 수집기**다. 참조 모델들을 병렬로 돌려 각자의 분석을
모아 **현재 세션(=너, 집계자)에게 반환**한다. 종합·행동은 네가 전체 도구로 한다.

## 언제

- 어려운 문제에 여러 모델 관점을 얹고 싶을 때 — "moa로 검토", "여러 모델로 봐줘".
- soft(기본): 설계·판단 관점. hard: 실제 코드베이스를 읽고 분석.

## 실행

1. 스크립트를 돌려 관점을 수집한다(cwd = 분석 대상 repo):
   ```bash
   cd <repo> && python3 ~/.claude/skills/moa/scripts/moa.py "<프롬프트>" [--hard] [--preset <이름>] [--refs-only]
   ```

- 대안 실행 폼: `PYTHONPATH=~/.claude/skills/moa python3 -m scripts.moa "..."`.

2. 출력된 `## MoA references` 블록을 읽는다.
3. **각 참조의 관점을 사용자에게 먼저 보여준다** — 도구 결과는 접혀서 사용자 눈에
   안 띈다. 네 응답 본문에 참조별로 `Reference N — backend:model` 라벨을 달아
   핵심 주장을 그대로(길면 충실한 발췌로) 옮겨라. 종합만 보고하는 것은 금지.
4. `--refs-only`가 아니면 하단 집계 지침대로 **네가 종합**한다: 합의·이견·놓친 점을
   대조하고, 이견은 논거로 판정, `[failed:]`·`[skipped:]`는 부분 정보로. 참조를
   맹신하지 말고 최종 판단 후 전체 도구로 행동한다.

## 모드·백엔드

- soft = openrouter 참조만(조언). hard = codex·claude 읽기전용 독립세션 + openrouter(강등).
- 참조는 어떤 모드에서도 부수효과 불가(읽기 전용). 집계자만 전체 권한.

## 레지스트리·인증

- 레지스트리: `~/.claude/moa/config.yml` (최초 실행 시 presets.example.yml 복사). 프리셋별
  references·reference_max_tokens·enabled. aggregator 필드 없음(항상 현재 세션).
- openrouter 키: `OPENROUTER_API_KEY` 환경변수(우선) 또는
  `~/.claude/auth/ai-ml-services.env`. codex/claude는 각 CLI 자체 인증 사용.

## 출처

NousResearch Hermes Agent MoA(MIT) 로직 이식 — advisory 프롬프트·병렬 팬아웃·실패 격리·
config 스키마.
