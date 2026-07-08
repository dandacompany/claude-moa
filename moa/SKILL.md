---
name: moa
description: Mixture of Agents 관점 팬아웃 — 여러 모델을 병렬 참조로 돌려 분석을 수집하고 현재 Claude 세션이 종합하게 한다. soft는 openrouter 조언, hard는 codex·claude 구독 세션과 openrouter Docker 격리까지. 트리거 moa로 검토, 여러 모델 관점, mixture of agents, moa setup.
---

# moa — Mixture of Agents 관점 팬아웃

## 정체

이 스킬은 **집계자가 아니라 관점 수집기**다. 참조 모델들을 병렬로 돌려 각자의 분석을
모아 **현재 세션(=너, 집계자)에게 반환**한다. 종합·행동은 네가 전체 도구로 한다.

## 언제

- 어려운 문제에 여러 모델 관점을 얹고 싶을 때 — "moa로 검토", "여러 모델로 봐줘".
- soft(기본): 설계·판단 관점. hard: 실제 코드베이스를 읽고 분석.

## 최초 설정 (온보딩)

처음 쓰거나 프로바이더를 바꿀 때 setup을 돌린다 — 어떤 백엔드가 쓸 수 있는지 감지하고
config를 구성한다. **키는 감지만 하고 절대 대화에 입력받지 않는다.**

```bash
python3 ~/.claude/skills/moa/scripts/moa.py setup
```

setup은 docker·openrouter·codex·claude 가용성을 ✅/⚠️로 보고하고, 미설정 항목은
사용자가 **별도 터미널에서** 직접 설정하도록 안내한다(openrouter는 env/파일, codex/claude는
각자 OAuth 로그인). 절대 키 값을 여기(세션)에 붙여넣지 말 것 — 트랜스크립트에 남는다.

## 실행

1. 스크립트를 돌려 관점을 수집한다(cwd = 분석 대상 repo):
   ```bash
   cd <repo> && python3 ~/.claude/skills/moa/scripts/moa.py "<프롬프트>" [--hard] [--preset <이름>] [--refs-only]
   ```
   - 프롬프트가 `setup`이라는 단어로 시작하면 따옴표로 감싼다(`"setup 좀 도와줘"`) — 안 그러면 setup 서브커맨드로 해석된다.

- 대안 실행 폼: `PYTHONPATH=~/.claude/skills/moa python3 -m scripts.moa "..."`.

2. 출력된 `## MoA references` 블록을 읽는다.
3. **각 참조의 관점을 사용자에게 먼저 보여준다** — 도구 결과는 접혀서 사용자 눈에
   안 띈다. 네 응답 본문에 참조별로 `Reference N — backend:model` 라벨을 달아
   핵심 주장을 그대로(길면 충실한 발췌로) 옮겨라. 종합만 보고하는 것은 금지.
4. `--refs-only`가 아니면 하단 집계 지침대로 **네가 종합**한다: 합의·이견·놓친 점을
   대조하고, 이견은 논거로 판정, `[failed:]`·`[skipped:]`는 부분 정보로. 참조를
   맹신하지 말고 최종 판단 후 전체 도구로 행동한다.

## 모드·백엔드 (하이브리드 — 과금이 경로를 가른다)

- **soft** = openrouter 참조만(조언, 종량). codex/claude는 `[skipped: hard 전용]`.
- **hard**:
  - `codex`·`claude` = **구독(OAuth) 네이티브 CLI**로 읽기전용 세션(`-s read-only` / `--permission-mode plan`). 정액제 이점 유지.
  - `openrouter` = 기본은 advisory 강등. 참조에 `isolate: docker`를 주면 **Docker 온디맨드 격리**(`-v repo:/work:ro --read-only`, 커널 강제 읽기전용)로 코드 읽는 에이전트로 격상. 종량 과금이라 격리를 최대로.
- 참조는 어떤 모드·경로에서도 부수효과 불가(읽기 전용). 집계자만 전체 권한.
- Docker 백엔드는 최초 사용 시 스킬의 `docker/` Dockerfile로 `moa-agent` 이미지를 자동 빌드. Docker 미설치 시 그 참조는 `[failed:]`로 격리.

## 레지스트리·인증

- 레지스트리: `~/.claude/moa/config.yml` (`moa setup` 또는 최초 실행 시 생성). 프리셋별
  references·reference_max_tokens·enabled. 참조 필드: `backend`·`model`·`isolate`(openrouter+docker). aggregator 필드 없음(항상 현재 세션).
- **키는 감지만, 수집 안 함** — openrouter 키는 `OPENROUTER_API_KEY` 환경변수(우선) 또는
  `~/.claude/auth/ai-ml-services.env`에 사용자가 직접 설정. codex/claude는 각 CLI 자체 OAuth 인증. moa는 존재 여부만 확인하고 값을 읽거나 출력하지 않는다.

## 출처

NousResearch Hermes Agent MoA(MIT) 로직 이식 — advisory 프롬프트·병렬 팬아웃·실패 격리·
config 스키마.
