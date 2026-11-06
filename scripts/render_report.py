#!/usr/bin/env python3
"""검사를 통과한 brief.json과 articles.json으로 뉴스런 브리프(마크다운)를 만든다.

사용법:
  python3 render_report.py work/brief.json work/articles.json --out newslearn-<키워드>-<날짜>.md
  python3 render_report.py ... --log newslearn-log.md   # 이력 한 줄 추가(다음 브리프의 '지난번 대비' 비교용)
  python3 render_report.py ... --force                  # 검사 오류가 있어도 만든다(보고서 맨 위에 경고 표시)

출력은 정해진 섹션 순서를 그대로 따른다. 보고서를 손으로 다시 쓰지 말고 brief.json을 고쳐서 다시 만든다.
"""
import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import validate_brief  # noqa: E402

SIGNAL = {"high": "🔴 강", "medium": "🟠 중", "low": "🟡 약"}
LENS = {"business": "사업·전략", "market": "시장·경쟁", "risk": "리스크·규제", "finance": "재무·자본시장"}
CHECK = {"CONFIRMED": "✅ 확인", "WEAKENED": "⚠️ 일부 확인", "UNCERTAIN": "❔ 확인 필요"}
IMPL = {"opportunity": "🟢 기회", "risk": "🔺 리스크", "watch": "👁 관찰"}
CONF = {"high": "높음", "medium": "중간", "low": "낮음"}
CRIT = {"recency": "최신성", "evidence": "근거성", "structure": "구조화", "so_what": "시사점 깊이",
        "actionability": "실행 가능성", "balance": "균형"}


def use_utf8_stdio():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def esc(s):
    return str(s).replace("|", "\\|").replace("\n", " ").strip()


def cite(ids, arts, limit=3):
    found = [arts[i] for i in ids if i in arts]
    parts = [f"[{esc(a['source'])} {a['published'][5:].replace('-', '/')}]({a['link']})" for a in found[:limit]]
    extra = len(found) - limit
    return " · ".join(parts) + (f" 외 {extra}건" if extra > 0 else "")


def render(brief, adoc, errors=None):
    arts = {a["id"]: a for a in adoc.get("articles", [])}
    w = adoc.get("window", {})
    c = adoc.get("counts", {})
    L = []
    title = brief.get("keyword", "")
    L.append(f"# 뉴스런 브리프: {title}")
    L.append("")
    meta = [f"기간 **{w.get('start')} ~ {w.get('end')}** (최근 {w.get('days')}일)",
            f"Google 뉴스 {', '.join(adoc.get('langs', []))}판",
            f"분석 기사 {c.get('kept', len(arts))}건 · 출처 {c.get('sources', '?')}곳",
            f"작성 {brief.get('generated_at', date.today().isoformat())}"]
    L.append("> " + " · ".join(meta))
    if brief.get("client_context"):
        L.append(f"> 관점: {esc(brief['client_context'])}")
    if errors:
        L.append("")
        L.append(f"> ⚠️ **검사 미통과 상태로 생성됨** ({len(errors)}건). 공유 전에 brief.json을 고쳐 다시 만드세요.")
    L.append("")

    L.append("## 한눈에 보기")
    L.append("")
    for s in brief.get("summary", []):
        L.append(f"- {s}")
    L.append("")

    delta = brief.get("delta")
    if isinstance(delta, dict) and (delta.get("new") or delta.get("resolved") or delta.get("changed")):
        L.append(f"## 지난 브리프({delta.get('previous_date', '?')}) 이후 달라진 점")
        L.append("")
        for k, lab in (("new", "🆕 새로 등장"), ("changed", "🔄 진전·변화"), ("resolved", "✔️ 일단락")):
            for x in delta.get(k) or []:
                L.append(f"- {lab}: {x}")
        L.append("")

    L.append("## 1. 최신 사업 현황")
    L.append("")
    L.append("| 영역 | 현황 | 근거 |")
    L.append("|---|---|---|")
    for st in brief.get("status", []):
        L.append(f"| {esc(st.get('area'))} | {esc(st.get('text'))} | {cite(st.get('sources', []), arts, 2)} |")
    L.append("")

    L.append("## 2. 주요 이슈")
    L.append("")
    L.append("| # | 이슈 | 관점 | 신호 | 팩트체크 |")
    L.append("|---|---|---|---|---|")
    for it in brief.get("issues", []):
        L.append(f"| {esc(it.get('id'))} | {esc(it.get('title'))} | {LENS.get(it.get('lens'), '?')} | "
                 f"{SIGNAL.get(it.get('signal'), '?')} | {CHECK.get(it.get('check'), '?')} |")
    L.append("")
    for it in brief.get("issues", []):
        L.append(f"### {it.get('id')}. {it.get('title')}")
        L.append("")
        L.append(f"- **무슨 일이:** {it.get('what')}")
        L.append(f"- **왜 중요한가:** {it.get('why')}")
        fig = validate_brief.FIGURE.search(f"{it.get('what', '')} {it.get('why', '')}")
        chk = CHECK.get(it.get("check"), "?")
        note = f" — {it['check_note']}" if it.get("check_note") else ""
        if fig and it.get("check") != "CONFIRMED":
            note += " (수치 미확인: 원문으로 확인 전 인용 주의)"
        L.append(f"- **팩트체크:** {chk}{note}")
        L.append(f"- **출처:** {cite(it.get('sources', []), arts, 4)}")
        L.append("")

    L.append("## 3. 타임라인")
    L.append("")
    L.append("| 날짜 | 사건 | 출처 |")
    L.append("|---|---|---|")
    for t in brief.get("timeline", []):
        L.append(f"| {t.get('date')} | {esc(t.get('event'))} | {cite(t.get('sources', []), arts, 1)} |")
    L.append("")

    L.append("## 4. 시사점")
    L.append("")
    for im in brief.get("implications", []):
        L.append(f"### {im.get('id')}. {im.get('title')}  {IMPL.get(im.get('type'), '')}")
        L.append("")
        L.append(f"- **So what:** {im.get('so_what')}")
        L.append(f"- **우리(고객·프로젝트)에게:** {im.get('for_client')}")
        L.append(f"- **다음 행동:** {im.get('next_action')}")
        L.append(f"- 근거 이슈: {', '.join(im.get('issues', []))} · 확신도: {CONF.get(im.get('confidence'), '?')}")
        L.append("")

    L.append("## 5. 앞으로 지켜볼 것")
    L.append("")
    L.append("| 무엇을 | 어떤 신호가 나오면 | 시점 |")
    L.append("|---|---|---|")
    for x in brief.get("watchlist", []):
        L.append(f"| {esc(x.get('item'))} | {esc(x.get('trigger'))} | {esc(x.get('by', '-'))} |")
    L.append("")

    L.append("## 6. 한계와 확인하지 못한 것")
    L.append("")
    for x in brief.get("limitations", []):
        L.append(f"- {x}")
    L.append("- 이 브리프는 공개 뉴스 보도를 정리한 것이며 회사의 공식 입장이나 투자 권유가 아닙니다.")
    L.append("")

    rv = brief.get("review") or {}
    sc = rv.get("scores") or {}
    if sc:
        avg = round(sum(v for v in sc.values() if isinstance(v, (int, float))) / max(1, len(sc)), 1)
        who = "자체 채점(리뷰어 분리 불가)" if rv.get("reviewer") == "self" else "파트너 리뷰어"
        L.append(f"<sub>품질 점검({who}): " + " · ".join(f"{CRIT.get(k, k)} {v}" for k, v in sc.items())
                 + f" · 평균 {avg}/10</sub>")
        L.append("")

    L.append("<details><summary>부록: 인용 기사 목록</summary>")
    L.append("")
    cited = []
    seen = set()
    for sec in ("status", "issues", "timeline"):
        for x in brief.get(sec, []):
            for s in x.get("sources", []):
                if s in arts and s not in seen:
                    seen.add(s)
                    cited.append(arts[s])
    month = None
    for a in sorted(cited, key=lambda a: a["published"]):
        if a["published"][:7] != month:
            month = a["published"][:7]
            L.append("")
            L.append(f"**{month}**")
            L.append("")
        dup = f" (외 {a['dup_count'] - 1}곳)" if a.get("dup_count", 1) > 1 else ""
        L.append(f"- {a['published']} · {esc(a['source'])} · [{esc(a['title'])}]({a['link']}){dup}")
    L.append("")
    L.append("</details>")
    L.append("")
    return "\n".join(L)


def log_line(brief, adoc, out_path):
    w = adoc.get("window", {})
    top = "; ".join(f"{i.get('id')} {i.get('title')}" for i in brief.get("issues", [])[:5])
    return (f"- {brief.get('generated_at', date.today().isoformat())} · {brief.get('keyword')} · "
            f"{w.get('start')}~{w.get('end')} · 기사 {len(adoc.get('articles', []))}건 · 이슈: {top} · 파일: {out_path}\n")


def main(argv=None):
    use_utf8_stdio()
    p = argparse.ArgumentParser(description="뉴스런 브리프 마크다운 생성")
    p.add_argument("brief")
    p.add_argument("articles")
    p.add_argument("--out", help="저장 경로(없으면 표준 출력)")
    p.add_argument("--log", help="이력 파일 경로(한 줄 추가)")
    p.add_argument("--force", action="store_true", help="검사 오류가 있어도 생성")
    a = p.parse_args(argv)
    try:
        brief = json.loads(Path(a.brief).read_text(encoding="utf-8"))
        adoc = json.loads(Path(a.articles).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"입력 파일 문제: {e}", file=sys.stderr)
        return 2
    errors, _, _ = validate_brief.check(brief, adoc)
    if errors and not a.force:
        print(f"검사 오류 {len(errors)}건 - validate_brief.py 결과를 고친 뒤 다시 실행하세요(--force로 강제 가능).", file=sys.stderr)
        for e in errors[:10]:
            print(f"  - {e}", file=sys.stderr)
        return 1
    md = render(brief, adoc, errors if errors else None)
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(md, encoding="utf-8")
        print(f"저장: {a.out}", file=sys.stderr)
    else:
        print(md)
    if a.log and not errors:
        with open(a.log, "a", encoding="utf-8") as f:
            f.write(log_line(brief, adoc, a.out or "(stdout)"))
        print(f"이력 추가: {a.log}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
