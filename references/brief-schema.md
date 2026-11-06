# brief.json 형식

종합 단계(6단계)에서 작성한다. `render_report.py`가 이 파일 하나로 보고서를 만든다. 예시는 [../examples/sample-brief.json](../examples/sample-brief.json).

```json
{
  "keyword": "LG에너지솔루션",
  "client_context": "선택. 프로젝트 관점(예: 배터리 소재 고객사의 공급 전략). 검색어에는 쓰지 않는다",
  "generated_at": "2026-11-06",

  "summary": [
    "가장 최근·가장 중요한 변화 1줄",
    "3개월 흐름(이전 → 지금) 1줄",
    "컨설턴트가 기억할 시사점 1줄"
  ],

  "delta": {
    "previous_date": "2026-08-01",
    "new": ["지난 브리프 이후 새로 등장한 이슈"],
    "changed": ["진전·변화가 있는 이슈"],
    "resolved": ["일단락된 이슈"]
  },

  "status": [
    {"area": "실적·재무", "text": "현황 1~2문장(사실만)", "sources": ["A004", "A120"]}
  ],

  "issues": [
    {
      "id": "I1",
      "title": "3차 ESS 중앙계약시장 입찰 불참",
      "lens": "business",
      "signal": "high",
      "what": "무슨 일이 있었는지(사실)",
      "why": "왜 중요한지(해석, 근거 범위 안에서)",
      "sources": ["A001", "A012", "A025"],
      "first_seen": "2026-11-05",
      "check": "CONFIRMED",
      "check_note": "WEAKENED/UNCERTAIN이면 필수. 열어 본 원문 URL"
    }
  ],

  "timeline": [
    {"date": "2026-08-12", "event": "사건 한 줄", "sources": ["A250"]}
  ],

  "implications": [
    {
      "id": "P1",
      "type": "opportunity | risk | watch",
      "title": "시사점 한 줄",
      "so_what": "그래서 무엇이 달라지는가",
      "for_client": "고객·프로젝트에 대한 의미(client_context가 없으면 '이 회사를 스터디하는 입장에서')",
      "next_action": "누구에게 무엇을 물을지 / 어떤 자료를 볼지 / 어떤 가설을 고칠지",
      "issues": ["I1", "I3"],
      "confidence": "high | medium | low"
    }
  ],

  "watchlist": [
    {"item": "무엇을", "trigger": "어떤 신호가 나오면 브리프를 다시 돌릴지", "by": "시점(예: 2026-12 결과 발표)"}
  ],

  "limitations": [
    "수집 범위·실패 구간·상한 도달일",
    "원문을 열지 못한 이슈",
    "리뷰어/검증자 분리 불가 시 그 사실"
  ],

  "review": {
    "reviewer": "partner-subagent | self",
    "scores": {"recency": 9, "evidence": 8, "structure": 9, "so_what": 8, "actionability": 8, "balance": 8},
    "rounds": 1
  }
}
```

## 필드 규칙

| 필드 | 값 | 비고 |
|---|---|---|
| `lens` | `business` 사업·전략 / `market` 시장·경쟁 / `risk` 리스크·규제 / `finance` 재무·자본시장 | |
| `signal` | `high` / `medium` / `low` | `high`는 언론사 2곳 이상 필수 |
| `check` | `CONFIRMED` / `WEAKENED` / `UNCERTAIN` | `REJECTED`는 넣지 않는다 |
| `status[].area` | 권장 영역: 실적·재무, 핵심 사업, 신사업·투자, 고객·수주, 경쟁 구도, 규제·정책, 조직·지배구조, ESG·평판 | 3~8개, 겹치지 않게 |
| `timeline` | 날짜 오름차순, 기간 안 | 5~15개 |
| `delta` | 선택 | 지난 브리프가 있을 때만 |
| `review.reviewer` | `self`이면 보고서에 "자체 채점"으로 표시 | |
