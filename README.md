# claude-moa — Mixture of Agents 스킬

Claude Code에서 **여러 모델의 관점을 병렬로 수집**해 현재 세션이 종합하게 하는 스킬입니다.
참조 모델들은 조언(soft) 또는 읽기전용 코드 분석(hard)만 하고, 최종 판단·행동은 항상
현재 Claude 세션(집계자)이 합니다.

> 이 스킬은 집계자가 아니라 **관점 수집기**입니다. NousResearch [Hermes Agent](https://github.com/NousResearch/Hermes-Agent)의
> MoA 구현(MIT)에서 advisory 프롬프트·병렬 팬아웃·실패 격리·config 스키마를 이식했습니다.

## 왜 MoA인가

어려운 문제에서 여러 모델의 관점을 종합하면 단일 모델보다 품질이 오릅니다
(HermesBench: 2-모델 MoA 0.8202 > 단일 opus 0.7607). 이 스킬은 그 패턴을
Claude Code 네이티브로 — 별도 게이트웨이 없이 — 가져옵니다.

## 두 모드

| | **soft** (기본) | **hard** |
|---|---|---|
| 참조 성격 | 프롬프트만 보고 조언 | 읽기전용 도구를 가진 독립 세션 |
| 코드 접근 | ❌ | ✅ 실제 repo 탐색 (읽기 전용) |
| 실행 백엔드 | openrouter만 | codex·claude + openrouter(조언 강등) |
| 용도 | 아이디어·설계·판단 | 코드베이스 실제 분석·리뷰 |

참조는 어떤 모드에서도 **부수효과를 낼 수 없습니다** — codex는 `-s read-only`,
claude는 `--permission-mode plan`으로 spawn되고, 자식 프로세스에는 최소 환경변수만
전달됩니다.

## 설치

```bash
# 1) 스킬 복사
git clone https://github.com/dandacompany/claude-moa.git
rsync -rlpt claude-moa/moa/ ~/.claude/skills/moa/

# 2) 의존성 (PyYAML만)
pip install pyyaml

# 3) OpenRouter 키 (soft 모드 필수)
export OPENROUTER_API_KEY=sk-or-...
```

- **codex 백엔드** (hard, 선택): [Codex CLI](https://github.com/openai/codex) 설치 + 로그인
- **claude 백엔드** (hard, 선택): Claude Code CLI 설치 + 로그인
- 미설치 백엔드는 `[failed: ...]`로 격리될 뿐 전체 실행은 계속됩니다.

## 사용

Claude Code 세션에서:

```
/moa 이 아키텍처 선택의 트레이드오프를 검토해줘          # soft, default 프리셋
/moa --hard --preset review 이 모듈의 동시성 약점을 분석해  # hard, 코드 실제 분석
```

또는 직접 실행:

```bash
cd <분석할-repo>
python3 ~/.claude/skills/moa/scripts/moa.py "<프롬프트>" [--hard] [--preset <이름>] [--refs-only]
```

출력은 `## MoA references` 블록(참조별 관점) + 집계 지침입니다. `--refs-only`는
집계 지침 없이 관점 묶음만 출력합니다.

## 레지스트리 설정

`~/.claude/moa/config.yml` (최초 실행 시 자동 생성):

```yaml
default_preset: default
presets:
  default:                     # soft 기본 — openrouter 조언
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

**규칙:**

- `backend`는 `openrouter` / `codex` / `claude`만 유효. 그 외(재귀 `moa` 포함)는 드롭.
- soft에서는 openrouter 참조만 실행 — codex/claude는 `[skipped: hard 전용]`으로 표시.
- 참조는 최대 8개 병렬. 하나가 실패해도 `[failed: <이유>]`로 격리되고 나머지는 계속.
- 추론 성향 모델(deepseek, glm 등)은 `reference_max_tokens`를 2000 이상으로 —
  너무 낮으면 reasoning으로 소진돼 빈 응답이 됩니다.
- YAML이 깨져도 기본 프리셋으로 폴백합니다(경고만 출력).

## 라이선스

MIT — NousResearch Hermes Agent의 MoA 로직(MIT)을 이식했습니다. [LICENSE](LICENSE) 참조.
