#!/usr/bin/env python3
"""brief.json(분석 결과)을 articles.json(수집 결과)과 대조해 형식과 근거를 검사하고, 통과 여부를 규칙대로 정한다.

사용법: python3 validate_brief.py work/brief.json work/articles.json
종료 코드: 0 = PASS(오류 없음), 1 = FIX(오류 있음), 2 = 입력 파일 문제
출력(JSON): verdict, errors, warnings, stats

검사하는 것은 '형식과 근거의 연결'이다. 내용이 맞는지는 팩트체커와 파트너 리뷰어의 몫이다.
"""
import json
import re
import sys
from pathlib import Path

LENSES = ("business", "market", "risk", "finance")
SIGNALS = ("high", "medium", "low")
CHECKS = ("CONFIRMED", "WEAKENED", "UNCERTAIN", "REJECTED")
IMPL_TYPES = ("opportunity", "risk", "watch")
CONFIDENCE = ("high", "medium", "low")
CRITERIA = ("recency", "evidence", "structure", "so_what", "actionability", "balance")
PASS_EACH, PASS_AVG = 7, 8.0
FIGURE = re.compile(r"\d[\d,.]*\s*(%|퍼센트|조|억|만|원|달러|\$|GWh|MWh|GW|MW|배|bp|명|건|대|톤|t\b)")
BOUNDS = {  # (최소, 최대). 기사가 적을 때(sparse)는 최소를 낮춘다.
    "summary": ((3, 3), (2, 3)),
    "status": ((3, 8), (2, 8)),
    "issues": ((3, 7), (1, 7)),
    "implications": ((3, 5), (2, 5)),
    "watchlist": ((3, 5), (2, 5)),
    "timeline": ((5, 15), (2, 15)),
}
SPARSE_UNDER = 30


def use_utf8_stdio():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def nonempty(v):
    return isinstance(v, str) and v.strip() != ""


def check(brief, articles_doc):
    errors, warnings = [], []
    arts = {a["id"]: a for a in articles_doc.get("articles", [])}
    win = articles_doc.get("window", {})
    w0, w1 = win.get("start", "0000-00-00"), win.get("end", "9999-99-99")
    sparse = len(arts) < SPARSE_UNDER
    cited = set()

    def sources_ok(tag, srcs, need=1):
        if not isinstance(srcs, list) or len(srcs) < need:
            errors.append(f"{tag}: sources가 {need}개 이상 필요")
            return []
        found = []
        for s in srcs:
            if s not in arts:
                errors.append(f"{tag}: 없는 기사 id '{s}' (articles.json에 없음 - 환각 출처)")
            else:
                found.append(arts[s])
                cited.add(s)
        return found

    def publishers(found):
        names = set()
        for a in found:
            names.add(a["source"])
            names.update(a.get("also_in", []))
        return names

    for key, (normal, light) in BOUNDS.items():
        lo, hi = light if sparse else normal
        v = brief.get(key)
        if not isinstance(v, list):
            errors.append(f"'{key}' 배열이 없음")
            continue
        if not lo <= len(v) <= hi:
            errors.append(f"'{key}'는 {lo}~{hi}개여야 함 (현재 {len(v)}개{', 기사 적음 기준' if sparse else ''})")

    if not nonempty(brief.get("keyword")):
        errors.append("'keyword' 누락")
    for i, s in enumerate(brief.get("summary") or []):
        if not nonempty(s):
            errors.append(f"summary[{i}]: 빈 문장")
        elif len(s) > 160:
            warnings.append(f"summary[{i}]: {len(s)}자 - 한 줄 요약은 160자 이내 권장")

    for i, st in enumerate(brief.get("status") or []):
        tag = f"status[{i}]"
        if not isinstance(st, dict):
            errors.append(f"{tag}: 객체가 아님")
            continue
        for k in ("area", "text"):
            if not nonempty(st.get(k)):
                errors.append(f"{tag}: '{k}' 누락")
        sources_ok(tag, st.get("sources"))

    issue_ids, lenses_used = set(), set()
    for i, it in enumerate(brief.get("issues") or []):
        tag = f"issues[{i}] {it.get('id', '?') if isinstance(it, dict) else ''}".strip()
        if not isinstance(it, dict):
            errors.append(f"{tag}: 객체가 아님")
            continue
        for k in ("id", "title", "what", "why"):
            if not nonempty(it.get(k)):
                errors.append(f"{tag}: '{k}' 누락")
        if it.get("id") in issue_ids:
            errors.append(f"{tag}: id 중복")
        issue_ids.add(it.get("id"))
        if it.get("lens") not in LENSES:
            errors.append(f"{tag}: lens는 {LENSES} 중 하나")
        lenses_used.add(it.get("lens"))
        if it.get("signal") not in SIGNALS:
            errors.append(f"{tag}: signal은 {SIGNALS} 중 하나")
        chk = it.get("check")
        if chk not in CHECKS:
            errors.append(f"{tag}: check는 {CHECKS} 중 하나(팩트체크 결과를 옮겨 적으세요)")
        if chk == "REJECTED":
            errors.append(f"{tag}: 팩트체크에서 REJECTED된 이슈는 보고서에 넣지 않음")
        if chk in ("WEAKENED", "UNCERTAIN") and not nonempty(it.get("check_note")):
            errors.append(f"{tag}: {chk}이면 check_note(무엇이 약한지/무엇이 있으면 확인되는지) 필요")
        found = sources_ok(tag, it.get("sources"))
        pubs = publishers(found)
        if it.get("signal") == "high" and len(pubs) < 2:
            errors.append(f"{tag}: signal=high는 서로 다른 언론사 2곳 이상 근거 필요(현재 {len(pubs)}곳) - medium으로 낮추거나 출처 보강")
        if it.get("signal") == "high" and chk != "CONFIRMED":
            warnings.append(f"{tag}: signal=high인데 팩트체크가 {chk} - 신호 강도를 다시 보세요")
        text = f"{it.get('what', '')} {it.get('why', '')}"
        if FIGURE.search(text) and chk != "CONFIRMED":
            warnings.append(f"{tag}: 수치가 있는데 팩트체크가 {chk} - 보고서에 '수치 미확인'으로 표시됨")
        for a in found:
            if not (w0 <= a["published"] <= w1):
                errors.append(f"{tag}: 기사 {a['id']}({a['published']})가 분석 기간 {w0}~{w1} 밖")

    missing_lens = [l for l in LENSES if l not in lenses_used]
    if len(missing_lens) >= 2 and not sparse:
        warnings.append(f"이슈가 {len(LENSES) - len(missing_lens)}개 관점에만 있음(빠진 관점: {', '.join(missing_lens)}) - 관점별 분석 결과를 다시 보세요")

    used_issue = set()
    for i, im in enumerate(brief.get("implications") or []):
        tag = f"implications[{i}] {im.get('id', '?') if isinstance(im, dict) else ''}".strip()
        if not isinstance(im, dict):
            errors.append(f"{tag}: 객체가 아님")
            continue
        for k in ("id", "title", "so_what", "for_client", "next_action"):
            if not nonempty(im.get(k)):
                errors.append(f"{tag}: '{k}' 누락 - 시사점은 'so what → 고객에게 의미 → 다음 행동'이 모두 있어야 함")
        if im.get("type") not in IMPL_TYPES:
            errors.append(f"{tag}: type은 {IMPL_TYPES} 중 하나")
        if im.get("confidence") not in CONFIDENCE:
            errors.append(f"{tag}: confidence는 {CONFIDENCE} 중 하나")
        refs = im.get("issues")
        if not isinstance(refs, list) or not refs:
            errors.append(f"{tag}: 근거 이슈(issues) 1개 이상 필요")
            refs = []
        for r in refs:
            if r not in issue_ids:
                errors.append(f"{tag}: 없는 이슈 id '{r}'")
            used_issue.add(r)
        if nonempty(im.get("so_what")) and nonempty(im.get("title")) and im["so_what"].strip() == im["title"].strip():
            errors.append(f"{tag}: so_what이 제목을 반복함 - '그래서 무엇이 달라지는가'를 쓰세요")
    types = {im.get("type") for im in brief.get("implications") or [] if isinstance(im, dict)}
    if "risk" not in types and "watch" not in types:
        warnings.append("시사점이 모두 기회(opportunity) - 균형을 위해 리스크/관찰 시사점을 검토하세요")
    for iid in issue_ids - used_issue:
        warnings.append(f"이슈 {iid}가 어떤 시사점에도 쓰이지 않음 - 시사점에 연결하거나 왜 중요한지 다시 보세요")

    prev = ""
    for i, t in enumerate(brief.get("timeline") or []):
        tag = f"timeline[{i}]"
        if not isinstance(t, dict):
            errors.append(f"{tag}: 객체가 아님")
            continue
        d = t.get("date", "")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(d)):
            errors.append(f"{tag}: date는 YYYY-MM-DD")
        elif not (w0 <= d <= w1):
            errors.append(f"{tag}: {d}가 분석 기간 {w0}~{w1} 밖")
        elif prev and d < prev:
            errors.append(f"{tag}: 날짜 오름차순이 아님")
        prev = d if isinstance(d, str) else prev
        if not nonempty(t.get("event")):
            errors.append(f"{tag}: event 누락")
        sources_ok(tag, t.get("sources"))

    for i, w in enumerate(brief.get("watchlist") or []):
        tag = f"watchlist[{i}]"
        if not isinstance(w, dict) or not nonempty(w.get("item")) or not nonempty(w.get("trigger")):
            errors.append(f"{tag}: item(무엇을)과 trigger(어떤 신호가 나오면) 필요")

    lim = brief.get("limitations")
    if not isinstance(lim, list) or not any(nonempty(x) for x in lim):
        errors.append("'limitations' 1개 이상 필요(수집 범위, 못 읽은 원문, 미확인 수치 등)")
    if articles_doc.get("errors") and not any("실패" in x or "누락" in x for x in lim or [] if isinstance(x, str)):
        warnings.append("수집 단계에 실패/건너뛴 구간이 있음 - limitations에 적으세요")
    if articles_doc.get("capped_days") and not any("상한" in x or "누락" in x for x in lim or [] if isinstance(x, str)):
        warnings.append(f"하루 100건 상한에 걸린 날({', '.join(articles_doc['capped_days'])})이 있음 - limitations에 적으세요")

    months = {arts[s]["published"][:7] for s in cited}
    if len(months) < 2 and not sparse:
        warnings.append(f"인용 기사가 {len(months)}개 달에만 있음 - 3개월 전체 흐름을 반영했는지 보세요")

    rv = brief.get("review")
    scores = rv.get("scores") if isinstance(rv, dict) else None
    avg = None
    if not isinstance(scores, dict):
        errors.append("'review.scores' 없음 - 파트너 리뷰어 채점(6개 기준)을 거친 뒤 넣으세요")
    else:
        vals = []
        for c in CRITERIA:
            v = scores.get(c)
            if not isinstance(v, (int, float)) or not 1 <= v <= 10:
                errors.append(f"review.scores.{c}: 1~10 숫자 필요")
            else:
                vals.append(v)
                if v < PASS_EACH:
                    errors.append(f"review.scores.{c}={v} < {PASS_EACH}: 해당 부분을 고친 뒤 다시 채점")
        if len(vals) == len(CRITERIA):
            avg = round(sum(vals) / len(vals), 2)
            if avg < PASS_AVG:
                errors.append(f"review 평균 {avg} < {PASS_AVG}: 약한 기준을 고친 뒤 다시 채점")
        if rv.get("reviewer") == "self":
            warnings.append("리뷰어 분리 불가 - 자체 채점(보고서에 표시됨)")

    stats = {
        "articles_kept": len(arts),
        "articles_cited": len(cited),
        "months_cited": sorted(months),
        "issues": len(issue_ids),
        "lenses": sorted(l for l in lenses_used if l),
        "review_avg": avg,
        "sparse_mode": sparse,
    }
    return errors, warnings, stats


def main(argv=None):
    use_utf8_stdio()
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        brief = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
        articles = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(json.dumps({"verdict": "INPUT_ERROR", "error": str(e)}, ensure_ascii=False))
        return 2
    if not isinstance(brief, dict):
        print(json.dumps({"verdict": "INPUT_ERROR", "error": "brief.json은 객체여야 함"}, ensure_ascii=False))
        return 2
    errors, warnings, stats = check(brief, articles)
    out = {"verdict": "PASS" if not errors else "FIX", "errors": errors, "warnings": warnings, "stats": stats}
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
