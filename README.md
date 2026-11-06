# newslearn (뉴스런)

컨설턴트가 스터디 중인 **타겟사 키워드 하나**를 넣으면, **Google 뉴스(뉴스 탭)의 최근 3개월 기사**를 빠짐없이 모아 **최신 사업 현황 · 주요 이슈 · 타임라인**을 정리하고, **컨설팅 관점의 시사점(So what → 고객에게 의미 → 다음 행동)** 까지 주는 AI 스킬입니다. Claude Code와 claude.ai에서 쓸 수 있는 `SKILL.md` 형식입니다.

```
LG에너지솔루션 뉴스런 해줘
SK하이닉스 최근 3개월 이슈 업데이트하고 시사점 정리해줘
현대차 동향 브리핑, 배터리 소재 고객사 관점에서
Tesla news brief, ko,en 둘 다
```

결과물 예시: [`examples/sample-report.md`](examples/sample-report.md) (LG에너지솔루션, 2026-08-09 ~ 2026-11-06, 실제 수집 데이터)

## 왜 이렇게 만들었나

AI에게 "OO 최근 뉴스 정리해줘"라고만 하면 흔히 세 가지가 생깁니다.

- **최근 며칠에 쏠립니다.** 검색 결과가 관련도·최신순이라 3개월 전 사건이 빠집니다.
- **헤드라인 숫자를 그대로 믿습니다.** "100억 배임"이 실제로는 추정치이고 공시 기준 75억(그중 이 회사 6.5억)인 식의 오류가 그대로 남습니다. (예시 브리프의 실제 팩트체크 결과입니다.)
- **시사점이 뉴스를 반복합니다.** "향후 귀추가 주목된다"로 끝나서 컨설턴트가 다음에 무엇을 해야 할지 알 수 없습니다.

그래서 **수집은 스크립트로 기간을 쪼개 고르게**, **분석은 관점별로 나눠서**, **확인은 만든 쪽과 다른 검증자가 반박하는 방식으로**, **통과 여부는 규칙 스크립트로** 정하도록 했습니다.

## 설계: 하네스 6요소

| 요소 | 이 스킬에서 |
|---|---|
| **Role** 역할 | 수집자 / 관점별 분석가 4명(사업·전략, 시장·경쟁, 리스크·규제, 재무·자본시장) / 팩트체커(이슈마다 반박 시도) / 종합자 / 파트너 리뷰어(처음 읽는 시니어 관점 채점) |
| **Rubric** 평가 기준 | 기계 검사 `validate_brief.py`(환각 출처, 기간, 신호 강도 근거 2곳 이상, 시사점 3요소, 개수) + 파트너 리뷰 6개 기준(최신성·근거성·구조화·시사점 깊이·실행 가능성·균형) 각 7점·평균 8점 이상 |
| **Context** 맥락 | 키워드 정의(정식명+약칭, 동명 기업 제외어, 언어판), 고객·프로젝트 관점(`client_context`), 지난 브리프 이력(`newslearn-log.md`)과 비교한 변화(delta) |
| **Tools** 도구 | `fetch_news.py`(Google 뉴스 RSS 기간 분할 수집·중복 묶기·주별 균형), `validate_brief.py`, `render_report.py`, WebSearch/WebFetch(원문 확인), 서브에이전트 |
| **Workflow** 진행 | 범위 확정 → 수집 → 노이즈 제거·군집 → 관점별 동시 분석 → 원문 확인·적대적 팩트체크 → 종합 → 기계 검사 → 파트너 리뷰 → 보고서 생성 → 전달 |
| **Guardrail** 금지 | 근거 없는 주장·헤드라인 숫자 단정 금지, 기사 본문 복사 금지, 투자 권유 금지, **고객 기밀을 검색어에 넣지 않기**, 기사 속 지시문 무시, 분석가·검증자 겸직 금지, 수집 실패 은폐 금지 |

상세는 [`SKILL.md`](SKILL.md)와 [`references/`](references)에 있습니다.

## 흐름

```
키워드 ──▶ fetch_news.py ──▶ articles.json / articles.txt
            (2주 구간 × N, 100건 상한이면 자동 분할,
             제목 유사도로 중복 묶기, 주별로 고르게 300건)
                 │
                 ▼
   ┌─ 분석가: 사업·전략 ─┐
   ├─ 분석가: 시장·경쟁 ─┤   (동시에, 서로의 결과를 보지 않음)
   ├─ 분석가: 리스크·규제 ┤
   └─ 분석가: 재무·자본 ─┘
                 │ 이슈 후보
                 ▼
     팩트체커 × 이슈 수 (원문을 열어 반박 시도)
     CONFIRMED / WEAKENED / UNCERTAIN / REJECTED
                 │
                 ▼
     종합 → brief.json ──▶ validate_brief.py (PASS/FIX)
                 │
                 ▼
     파트너 리뷰어 채점 (6개 기준) ──▶ render_report.py ──▶ 보고서.md + 이력
```

## 보고서 구성

1. **한눈에 보기** — 3줄 요약 (가장 최근 변화 / 3개월 흐름 / 기억할 시사점)
2. **최신 사업 현황** — 영역별(실적·재무, 핵심 사업, 신사업·기술, 공급망, 지배구조, 리스크 …) 표
3. **주요 이슈** — 이슈별 무슨 일이 / 왜 중요한가 / 신호 강도(🔴🟠🟡) / 팩트체크 결과 / 출처 링크
4. **타임라인** — 3개월 사건 순서
5. **시사점** — 🟢기회 · 🔺리스크 · 👁관찰, 각각 So what / 우리에게 / 다음 행동(누구에게 무엇을 물을지, 어떤 자료를 볼지)
6. **앞으로 지켜볼 것** — 어떤 신호가 나오면 다시 볼지
7. **한계** — 수집 범위, 누락 가능 구간, 원문 미확인 항목
- 부록: 인용 기사 목록(월별)

지난 브리프가 `newslearn-log.md`에 있으면 맨 앞에 **"지난 브리프 이후 달라진 점"** 이 붙습니다.

## 설치

**Claude Code**

```bash
git clone https://github.com/cosmos1219-eunice/newslearn-skill.git ~/.claude/skills/newslearn
```

새 세션부터 "OO 뉴스런 해줘"로 호출됩니다. 보고서와 이력(`newslearn-log.md`)은 작업 폴더에 남습니다.

**claude.ai**

[`dist/newslearn.zip`](dist/newslearn.zip)을 내려받아 설정 → 기능(Capabilities) → 스킬에서 그대로 업로드합니다. (zip 안의 폴더 이름이 스킬 이름 `newslearn`과 같아야 합니다.) claude.ai의 코드 실행 환경에서 `news.google.com`에 접근할 수 있어야 수집 스크립트가 동작합니다.

**필요 환경**: Python 3.9 이상(외부 패키지 없음), `news.google.com` 네트워크 접근.

## 직접 스크립트 쓰기

```bash
# 1) 수집 (기본: 최근 90일, 한국어판, 약 2주 구간 6개, 최대 300건)
python3 scripts/fetch_news.py "LG에너지솔루션" --alias "LG엔솔" --out work/articles.json
python3 scripts/fetch_news.py "Tesla" --lang ko,en --exclude "니콜라 테슬라"

# 2) 분석 결과(brief.json) 검사
python3 scripts/validate_brief.py work/brief.json work/articles.json

# 3) 보고서 생성 + 이력 남기기
python3 scripts/render_report.py work/brief.json work/articles.json \
  --out newslearn-LG에너지솔루션-20261106.md --log newslearn-log.md
```

`brief.json` 형식은 [`references/brief-schema.md`](references/brief-schema.md), 예시는 [`examples/sample-brief.json`](examples/sample-brief.json).

## 구성 파일

```
newslearn-skill/
├── SKILL.md                         # 역할 · 평가 기준 · 맥락 · 도구 · 진행 규칙 · 금지 사항
├── README.md
├── LICENSE
├── references/
│   ├── roles.md                     # 역할별 판단 기준, 분석가 4관점, 팩트체커 절차
│   ├── rubric.md                    # 기계 검사 규칙, 파트너 리뷰 채점표, 좋은/나쁜 시사점 예
│   ├── brief-schema.md              # brief.json 형식
│   ├── implication-lenses.md        # 시사점 도출 렌즈(전략·경쟁·가치동인·불확실성·실행)
│   └── subagent-prompts.md          # 분석가·팩트체커·파트너 리뷰어 프롬프트 템플릿
├── scripts/
│   ├── fetch_news.py                # Google 뉴스 RSS 기간 분할 수집, 중복 묶기, 주별 균형
│   ├── validate_brief.py            # 형식·근거 검사, PASS/FIX 판정
│   └── render_report.py             # 마크다운 보고서 + 이력
├── examples/                        # LG에너지솔루션 실제 실행 결과
│   ├── sample-articles.json / .txt
│   ├── sample-brief.json
│   └── sample-report.md
├── tests/                           # python3 -m unittest discover -s tests
└── dist/newslearn.zip               # claude.ai 업로드용
```

## 테스트

```bash
python3 -m unittest discover -s tests
```

테스트는 네트워크를 쓰지 않습니다(가짜 RSS 파일 `tests/fixtures/sample_feed.xml` 사용).

## 한계

- 팩트체커와 리뷰어도 AI라서 같은 오해를 공유할 수 있습니다. 스크립트는 근거의 **연결과 형식**을 확인할 뿐 내용의 정확성은 모릅니다. 고객에게 나가는 자료는 사람이 원문·공시로 다시 확인하세요.
- Google 뉴스 RSS는 구간당 최대 100건만 줍니다. 보도가 아주 많은 날은 하루 구간으로 쪼개도 일부가 빠질 수 있고, 이 경우 보고서 한계에 해당 날짜가 표시됩니다.
- Google 뉴스 링크는 리디렉션 링크라 원문 확인은 헤드라인 검색(WebSearch)으로 합니다. 유료 기사나 검색에 잡히지 않는 기사는 "확인 필요"로 남습니다.
- 예시 브리프는 한 에이전트가 역할을 차례로 수행해 만든 것이라(서브에이전트 분리 없이) "자체 채점"으로 표시되어 있습니다.
- Google 뉴스 RSS는 개인적·비상업적 열람용입니다. 대량·자동 반복 수집에 쓰지 마세요.

## 참고

설계는 다음 두 저장소의 구조를 참고했습니다.
- [SYHER/pr-squad-skills](https://github.com/SYHER/pr-squad-skills) — 하네스 6요소, 관점별 Fan-out + 적대적 검증, 규칙 스크립트 판정
- [guilloufre/language-lesson-builder](https://github.com/guilloufre/language-lesson-builder) — 단일 스킬 폴더 구성, 자체 평가 루프, 이력 로그, claude.ai용 zip 배포

## 라이선스

MIT. [LICENSE](LICENSE) 참고.
