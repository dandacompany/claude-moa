# claude-moa

**Claude Code용 Mixture of Agents 스킬 — 여러 모델에 질문을 병렬로 팬아웃하고, 현재 세션이 그 관점들을 종합한다.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![skills.sh](https://img.shields.io/badge/skills.sh-claude--moa-blue)](https://skills.sh/dandacompany/claude-moa)

English: [README.md](./README.md)

에이전트 아래에서 모델을 몰래 섞는 모델-프로바이더 게이트웨이와 달리, 이 스킬은 Claude Code 안에 평범한 스킬로 앉는다. 스스로 집계자인 척하지 않는다 — 참조 모델은 조언(soft)하거나 코드를 읽기전용(hard)으로 볼 뿐이고, 최종 판단과 행동은 언제나 현재 Claude 세션에 남는다. 이것은 **관점 수집기**이지 의사결정자가 아니다.

MoA 로직 — advisory 재프레이밍, 병렬 팬아웃, 실패 격리, config 스키마 — 은 NousResearch [Hermes Agent](https://github.com/NousResearch/Hermes-Agent)(MIT)에서 이식했다. 종합은 의도적으로 이식하지 않았다: 스크립트는 라벨이 붙은 관점 묶음을 반환하고, 현재 세션이 전체 도구로 그것을 종합한다.

## 왜 MoA인가

어려운 문제에서 여러 모델의 관점을 종합하면 단일 모델보다 품질이 오른다(HermesBench: 2-모델 MoA 0.8202 > 단일 상위 모델 0.7607). 이 스킬은 그 패턴을 별도 게이트웨이나 프로바이더 shim 없이 Claude Code 네이티브로 가져온다.

## 두 모드

| | **soft** (기본) | **hard** |
| --- | --- | --- |
| 참조 성격 | 프롬프트 텍스트만 보고 조언 | 읽기전용 도구를 가진 독립 세션 |
| 코드 접근 | ❌ 프롬프트 문맥만 | ✅ 실제 repo 탐색 (읽기 전용) |
| 실행 백엔드 | `openrouter`만 | `codex` · `claude` + `openrouter`(조언 강등) |
| 용도 | 아이디어·설계·판단 | 코드베이스 실제 분석·리뷰 |

참조는 **어떤 모드에서도** 부수효과를 낼 수 없다: `codex`는 `-s read-only`, `claude`는 `--permission-mode plan`으로 spawn되고, 자식 프로세스에는 최소 환경변수만 전달된다(부모 API 키 미상속). 전체 권한을 가진 것은 집계자 — 현재 세션 — 뿐이다.

## 요구 사항

- **Python 3** + **PyYAML** (`pip install pyyaml`) — 유일한 의존성.
- soft 모드용 **OpenRouter API 키**: `OPENROUTER_API_KEY`(환경변수 우선) 또는 `~/.claude/auth/ai-ml-services.env`.
- **Codex CLI** (선택, hard 모드): [openai/codex](https://github.com/openai/codex), 로그인 필요.
- **Claude Code CLI** (선택, hard 모드): 로그인 필요.

미설치 백엔드는 `[failed: ...]`로 격리될 뿐, 나머지 팬아웃은 계속된다.

## 설치

### Option A — clone + copy (권장)

```bash
git clone https://github.com/dandacompany/claude-moa.git ~/src/claude-moa
rsync -rlpt ~/src/claude-moa/moa/ ~/.claude/skills/moa/
pip install pyyaml
```

### Option B — skills CLI

```bash
skills add dandacompany/claude-moa@moa -g --copy -a claude-code
```

### 확인

```bash
export OPENROUTER_API_KEY=sk-or-...
cd <아무-repo> && python3 ~/.claude/skills/moa/scripts/moa.py "왜 느린가?"
```

## 사용

Claude Code 세션에서:

```
/moa 이 아키텍처 선택의 트레이드오프를 검토해줘              # soft, default 프리셋
/moa --hard --preset review 이 모듈의 동시성 약점을 분석해   # hard, 코드 실제 분석
```

또는 직접:

```bash
cd <대상-repo>
python3 ~/.claude/skills/moa/scripts/moa.py "<프롬프트>" [--hard] [--preset <이름>] [--refs-only]
```

출력은 `## MoA references` 블록(참조별 관점)과 종합 지침이다. `--refs-only`는 종합 지침 없이 관점 묶음만 반환한다.

## 설정

`~/.claude/moa/config.yml` (최초 실행 시 자동 생성):

```yaml
default_preset: default
presets:
  default:                     # soft — openrouter 조언
    references:
      - { backend: openrouter, model: z-ai/glm-5.2 }
      - { backend: openrouter, model: openai/gpt-5.5 }
    reference_max_tokens: null # null=무제한, 숫자=참조 응답 길이 제한
    enabled: true
  review:                      # hard 코드검토 — 읽기전용 세션 3종
    references:
      - { backend: claude, model: claude-opus-4-8 }
      - { backend: codex, model: gpt-5.5 }
      - { backend: openrouter, model: z-ai/glm-5.2 }
    reference_max_tokens: 2000
    enabled: true
```

| 필드 | 규칙 |
| --- | --- |
| `backend` | `openrouter` / `codex` / `claude` 중 하나. 그 외(재귀 `moa` 포함)는 드롭 |
| `model` | non-empty 문자열, 백엔드별 모델 id |
| `reference_max_tokens` | 양의 정수, 아니면 `null`(무제한). 조언자에만 적용 |
| `enabled` | `false`면 팬아웃 생략, 집계자 단독 진행 |

메모:

- soft 모드에서는 `openrouter` 참조만 실행되고, `codex`/`claude`는 `[skipped: hard 전용]`으로 표시된다.
- 참조는 최대 8개 병렬. 하나가 실패해도 `[failed: <이유>]`로 격리되고 나머지는 계속된다.
- 추론 성향 모델(deepseek, glm 등)은 `reference_max_tokens`를 2000 이상으로 — 너무 낮으면 reasoning으로 소진돼 빈 응답이 된다.
- YAML이 깨져도 기본 프리셋으로 폴백한다(경고만 출력).

## 구조

파일당 하나의 책임, 4개 모듈:

- `config.py` — 레지스트리 로드 + 정규화 (순수 함수)
- `adapters.py` — 백엔드별 참조 호출 1건; 읽기전용 강제; 오류·시크릿 마스킹
- `fanout.py` — 병렬 오케스트레이션, 모드 게이팅, 실패 격리, 출력 포맷
- `moa.py` — CLI 진입 (인자 파싱, 모드 배선, 종합 지침)

종합은 이식하지 않았다 — 반환된 블록은 호출한 세션이 종합하도록 설계됐다.

## 보안

참조는 신뢰할 수 없는 모델을 실행하므로, 스킬은 읽기전용 불변식을 강제하고 머신 밖으로 나가는 것을 제한한다:

- **부수효과 없음.** `codex`는 `-s read-only`, `claude`는 `--permission-mode plan` + `--allowedTools Read Grep Glob`으로 실행된다. 실제 쓰기 차단은 allowlist가 아니라 plan 모드에서 오므로 제거하지 말 것.
- **최소 자식 환경.** 서브프로세스에는 화이트리스트(`PATH`, `HOME`, `USER`, `SHELL`, `TMPDIR`, `LANG`, `LC_ALL`, `TERM`)만 전달돼 부모 API 키가 상속되지 않는다. `stdin`은 닫혀 있어 CLI가 상속된 파이프에서 멈추는 것을 방지한다.
- **시크릿 마스킹.** 사용자에게 노출되는 오류 텍스트(`[failed: ...]`)는 `Bearer` 토큰·`sk-` 키·`*_API_KEY=` / `*_TOKEN=` / `*_SECRET=` 패턴을 마스킹하는 sanitizer를 거친다.

정직하게 밝히는 한계: `codex`/`claude`의 쓰기 차단은 자식 CLI의 플래그에 위임돼 있다 — in-process 샌드박스나 실행 후 검증은 없다. soft 모드 `openrouter` 호출은 프롬프트 텍스트를 그대로 외부 API로 보내므로, 프롬프트에 시크릿을 넣지 말 것.

## 출처 (Attribution)

NousResearch [Hermes Agent](https://github.com/NousResearch/Hermes-Agent)(MIT)의 Mixture of Agents 로직을 이식했다 — advisory 시스템 프롬프트, 병렬 팬아웃, 실패 격리, 프리셋·config 스키마. "집계자 = 현재 세션" 설계와 읽기전용 강제는 이 스킬 고유의 것이다.

## 라이선스

[MIT](./LICENSE) © Dante Labs

---

<div align="center">

**Dante Labs** · **YouTube** [@dante-labs](https://youtube.com/@dante-labs) · **Email** [dante@dante-labs.com](mailto:dante@dante-labs.com) · **Discord** [Dante Labs Community](https://discord.com/invite/rXyy5e9ujs) · **Support** [Buy Me a Coffee](https://buymeacoffee.com/dante.labs)

</div>
