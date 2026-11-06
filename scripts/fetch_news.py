#!/usr/bin/env python3
"""Google 뉴스(뉴스 탭) 검색 결과를 기간별로 나눠 모으고, 중복 기사를 묶어 articles.json으로 저장한다.

Google 뉴스 RSS는 한 번에 최대 100건만 주고 관련도 순이라, 3개월을 한 번에 검색하면 최근 몇 주에 몰린다.
그래서 기간을 여러 구간(after:/before:)으로 나눠 구간마다 따로 받는다.

사용법:
  python3 fetch_news.py "삼성전자" --out work/articles.json
  python3 fetch_news.py "LG에너지솔루션" --alias "LG엔솔" --exclude "채용" --days 90 --lang ko,en
  python3 fetch_news.py "삼성전자" --fixture tests/fixtures/sample_feed.xml   # 네트워크 없이 시험

출력:
  --out 경로에 articles.json, 같은 폴더에 articles.txt(에이전트가 읽기 좋은 한 줄 목록)
  표준 오류에 수집 통계
종료 코드: 0 = 정상, 1 = 수집 결과 0건, 2 = 인자/네트워크 문제
외부 패키지 없음(Python 3.9+).
"""
import argparse
import email.utils
import json
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

RSS_URL = "https://news.google.com/rss/search"
EDITIONS = {
    "ko": {"hl": "ko", "gl": "KR", "ceid": "KR:ko"},
    "en": {"hl": "en-US", "gl": "US", "ceid": "US:en"},
    "ja": {"hl": "ja", "gl": "JP", "ceid": "JP:ja"},
    "zh": {"hl": "zh-CN", "gl": "CN", "ceid": "CN:zh-Hans"},
}
UA = "Mozilla/5.0 (compatible; newslearn-skill/1.0; +personal feed reader)"
DUP_THRESHOLD = 0.72  # 제목 문자 바이그램 자카드 유사도. 이 이상이면 같은 기사로 묶는다.


def use_utf8_stdio():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def log(msg):
    print(msg, file=sys.stderr)


# ---------- 질의 ----------

def quote_term(term):
    term = term.strip()
    if not term:
        return ""
    return f'"{term}"' if (" " in term or not term.isascii()) and not term.startswith('"') else term


def build_query(keyword, aliases=(), excludes=(), after=None, before=None):
    terms = [quote_term(t) for t in [keyword, *aliases] if t.strip()]
    q = terms[0] if len(terms) == 1 else "(" + " OR ".join(terms) + ")"
    for ex in excludes:
        if ex.strip():
            q += f" -{quote_term(ex)}"
    if after:
        q += f" after:{after.isoformat()}"
    if before:
        q += f" before:{before.isoformat()}"
    return q


def split_windows(start, end, n):
    """[start, end] 날짜 구간을 n개로 나눈다. Google의 before:는 그날을 포함하지 않으므로 끝을 하루 늘린다."""
    n = max(1, n)
    total = (end - start).days + 1
    step = max(1, -(-total // n))
    windows = []
    cur = start
    while cur <= end:
        nxt = min(cur + timedelta(days=step - 1), end)
        windows.append((cur, nxt))
        cur = nxt + timedelta(days=1)
    return windows


def rss_url(query, lang):
    params = {"q": query, **EDITIONS[lang]}
    return RSS_URL + "?" + urllib.parse.urlencode(params)


def http_get(url, timeout, retries=3, backoff=4.0):
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/rss+xml"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode("utf-8", errors="replace")
            if body.lstrip().startswith("<?xml") or "<rss" in body[:500]:
                return body
            last = "RSS가 아닌 응답(요청이 많아 Google이 잠시 막은 것일 수 있음)"
        except Exception as e:  # noqa: BLE001 - 네트워크 오류는 모두 재시도 대상
            last = f"{type(e).__name__}: {e}"
        if attempt < retries - 1:
            time.sleep(backoff * (2 ** attempt))
    raise RuntimeError(last or "알 수 없는 오류")


# ---------- 파싱 ----------

def parse_feed(xml_text, lang):
    root = ET.fromstring(xml_text)
    items = []
    for it in root.iter("item"):
        raw_title = (it.findtext("title") or "").strip()
        src_el = it.find("source")
        source = (src_el.text or "").strip() if src_el is not None else ""
        source_url = src_el.get("url", "") if src_el is not None else ""
        title = raw_title
        while source and title.endswith(" - " + source):
            title = title[: -(len(source) + 3)].strip()
        pub = it.findtext("pubDate") or ""
        try:
            published = email.utils.parsedate_to_datetime(pub).astimezone(timezone.utc)
        except (TypeError, ValueError):
            continue
        items.append({
            "title": unicodedata.normalize("NFC", title),
            "source": source or "(출처 미상)",
            "source_url": source_url,
            "link": (it.findtext("link") or "").strip(),
            "published": published,
            "lang": lang,
        })
    return items


# ---------- 중복 묶기 ----------

def norm_title(t):
    t = re.sub(r"^\s*[\[【(<][^\]】)>]{1,12}[\]】)>]\s*", "", t)  # [단독], [속보] 같은 말머리
    t = re.sub(r"[^\w]+", "", t.lower())
    return t


def bigrams(s):
    return {s[i:i + 2] for i in range(len(s) - 1)} or {s}


def similarity(a, b):
    A, B = bigrams(a), bigrams(b)
    return len(A & B) / len(A | B) if A and B else 0.0


def dedupe(items, threshold=DUP_THRESHOLD):
    """비슷한 제목을 하나로 묶는다. 대표는 가장 먼저 보도된 기사, 나머지 출처는 also_in에 남긴다.
    같은 사건을 여러 언론이 다뤘다는 것(dup_count)은 이슈의 무게를 가늠하는 신호로 쓴다."""
    clusters = []
    for item in sorted(items, key=lambda x: x["published"]):
        key = norm_title(item["title"])
        kb = bigrams(key)
        home = None
        for c in clusters:
            if c["_key"] == key or (len(kb & c["_bg"]) / len(kb | c["_bg"]) >= threshold):
                home = c
                break
        if home is None:
            clusters.append({**item, "_key": key, "_bg": kb, "also_in": [], "_links": {item["link"]}})
        elif item["link"] not in home["_links"]:
            home["_links"].add(item["link"])
            if item["source"] != home["source"] and item["source"] not in home["also_in"]:
                home["also_in"].append(item["source"])
            home.setdefault("_dups", 0)
            home["_dups"] += 1
    out = []
    for c in clusters:
        c["dup_count"] = 1 + c.pop("_dups", 0)
        for k in ("_key", "_bg", "_links"):
            c.pop(k)
        out.append(c)
    return out


def balance(items, cap):
    """기사가 cap보다 많으면 주(週)별로 고르게 남긴다. 최근 기사가 몰려 과거 이슈가 묻히는 것을 막는다.
    주마다 같은 몫을 주고, 남는 몫은 기사가 많은 주로 돌린다. 주 안에서는 여러 곳이 보도한 기사를 먼저 남긴다."""
    if cap <= 0 or len(items) <= cap:
        return items, 0
    weeks = {}
    for a in items:
        weeks.setdefault(a["published"].isocalendar()[:2], []).append(a)
    for v in weeks.values():
        v.sort(key=lambda x: (-x["dup_count"], x["published"]))
    quota = {k: 0 for k in weeks}
    left = cap
    while left > 0:
        open_weeks = [k for k in weeks if quota[k] < len(weeks[k])]
        if not open_weeks:
            break
        share = max(1, left // len(open_weeks))
        for k in open_weeks:
            add = min(share, len(weeks[k]) - quota[k], left)
            quota[k] += add
            left -= add
            if left == 0:
                break
    kept = [a for k, v in weeks.items() for a in v[: quota[k]]]
    return kept, len(items) - len(kept)


# ---------- 메인 ----------

def collect(args, today):
    end = today
    start = today - timedelta(days=args.days - 1)
    langs = [l.strip() for l in args.lang.split(",") if l.strip()]
    for l in langs:
        if l not in EDITIONS:
            raise SystemExit(f"지원하지 않는 언어: {l} (가능: {', '.join(EDITIONS)})")
    raw, errors, requests, capped_days = [], [], [], []
    if args.fixture:
        text = Path(args.fixture).read_text(encoding="utf-8")
        raw.extend(parse_feed(text, langs[0]))
        requests.append({"query": "(fixture)", "lang": langs[0], "count": len(raw)})
    else:
        queue = [(lang, w) for lang in langs for w in split_windows(start, end, args.windows)]
        first = True
        while queue:
            lang, (w0, w1) = queue.pop(0)
            q = build_query(args.keyword, args.alias, args.exclude, after=w0 - timedelta(days=1),
                            before=w1 + timedelta(days=1))
            if len(requests) + len(errors) >= args.max_requests:
                errors.append({"query": q, "lang": lang, "error": "요청 한도(--max-requests) 도달로 건너뜀"})
                log(f"  [{lang}] {w0}~{w1}: 요청 한도 도달로 건너뜀")
                continue
            if not first:
                time.sleep(args.delay)
            first = False
            try:
                items = parse_feed(http_get(rss_url(q, lang), args.timeout), lang)
            except Exception as e:  # noqa: BLE001
                errors.append({"query": q, "lang": lang, "error": str(e)})
                log(f"  [{lang}] {w0}~{w1}: 실패 - {e}")
                continue
            raw.extend(items)
            requests.append({"query": q, "lang": lang, "from": w0.isoformat(), "to": w1.isoformat(),
                             "count": len(items)})
            capped = len(items) >= 100
            if capped and w0 < w1:
                mid = w0 + timedelta(days=(w1 - w0).days // 2)
                queue[0:0] = [(lang, (w0, mid)), (lang, (mid + timedelta(days=1), w1))]
                log(f"  [{lang}] {w0}~{w1}: {len(items)}건 (상한 도달 → 구간을 나눠 다시 받음)")
            else:
                log(f"  [{lang}] {w0}~{w1}: {len(items)}건{' (하루 구간도 상한 - 일부 누락 가능)' if capped else ''}")
                if capped:
                    capped_days.append(w0.isoformat())
    start_dt = datetime(start.year, start.month, start.day, tzinfo=timezone.utc)
    in_window = [x for x in raw if x["published"] >= start_dt]
    if args.exclude:
        exl = [e.lower() for e in args.exclude]
        in_window = [x for x in in_window if not any(e in x["title"].lower() for e in exl)]
    unique = dedupe(in_window)
    unique, dropped = balance(unique, args.max_articles)
    unique.sort(key=lambda x: (x["published"], x["dup_count"]), reverse=True)
    by_month = {}
    for i, a in enumerate(unique, 1):
        a["id"] = f"A{i:03d}"
        a["published"] = a["published"].strftime("%Y-%m-%d")
        m = a["published"][:7]
        by_month[m] = by_month.get(m, 0) + 1
    sources = {a["source"] for a in unique}
    return {
        "keyword": args.keyword,
        "aliases": args.alias,
        "excludes": args.exclude,
        "langs": langs,
        "window": {"start": start.isoformat(), "end": end.isoformat(), "days": args.days},
        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "counts": {"raw": len(raw), "in_window": len(in_window), "unique": len(unique) + dropped,
                   "kept": len(unique), "dropped_by_balance": dropped, "sources": len(sources)},
        "by_month": dict(sorted(by_month.items())),
        "requests": requests,
        "errors": errors,
        "capped_days": capped_days,
        "articles": [{k: a[k] for k in ("id", "published", "source", "title", "dup_count", "also_in",
                                         "lang", "link", "source_url")} for a in unique],
    }


def to_text(data):
    w = data["window"]
    c = data["counts"]
    lines = [f"# {data['keyword']} | {w['start']} ~ {w['end']} | 고유 {c['unique']}건 중 {c['kept']}건 · 출처 {c['sources']}곳",
             "# id | 날짜 | 언론사 | 제목 | (xN = N곳 보도)"]
    for a in data["articles"]:
        dup = f" (x{a['dup_count']})" if a["dup_count"] > 1 else ""
        lines.append(f"{a['id']} | {a['published']} | {a['source']} | {a['title']}{dup}")
    return "\n".join(lines) + "\n"


def main(argv=None):
    use_utf8_stdio()
    p = argparse.ArgumentParser(description="Google 뉴스 최근 N일 기사 수집")
    p.add_argument("keyword", help="타겟사 또는 주제 키워드")
    p.add_argument("--alias", action="append", default=[], help="같은 대상을 가리키는 다른 이름(OR 검색). 여러 번 지정 가능")
    p.add_argument("--exclude", action="append", default=[], help="제외할 단어(동명 기업, 채용 공고 등). 여러 번 지정 가능")
    p.add_argument("--days", type=int, default=90, help="최근 며칠(기본 90일 = 약 3개월)")
    p.add_argument("--windows", type=int, default=6, help="기간을 몇 구간으로 나눠 받을지(기본 6 = 약 2주 단위)")
    p.add_argument("--lang", default="ko", help="뉴스 판: ko, en, ja, zh. 쉼표로 여러 개(예: ko,en)")
    p.add_argument("--out", default="work/articles.json", help="저장 경로(기본 work/articles.json)")
    p.add_argument("--delay", type=float, default=2.0, help="요청 사이 대기 초(기본 2초, 차단 방지)")
    p.add_argument("--max-articles", type=int, default=300, help="남길 최대 기사 수(기본 300, 주별로 고르게). 0이면 제한 없음")
    p.add_argument("--max-requests", type=int, default=24, help="최대 요청 수(기본 24). 상한에 걸린 구간을 나눌 때 늘어난다")
    p.add_argument("--timeout", type=float, default=20.0, help="요청 제한 시간 초")
    p.add_argument("--fixture", help="네트워크 대신 읽을 RSS 파일(시험용)")
    p.add_argument("--today", help="기준일 YYYY-MM-DD(시험용, 기본 오늘)")
    args = p.parse_args(argv)
    if args.days < 1 or args.days > 365:
        log("--days는 1~365 사이여야 합니다.")
        return 2
    today = datetime.strptime(args.today, "%Y-%m-%d").date() if args.today else datetime.now(timezone.utc).date()
    log(f"수집: {build_query(args.keyword, args.alias, args.exclude)} · 최근 {args.days}일 · {args.lang}")
    data = collect(args, today)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    out.with_suffix(".txt").write_text(to_text(data), encoding="utf-8")
    c = data["counts"]
    log(f"완료: 원본 {c['raw']}건 → 기간 내 {c['in_window']}건 → 중복 제거 {c['unique']}건 → 주별 균형 {c['kept']}건 · 출처 {c['sources']}곳 · 월별 {data['by_month']}")
    log(f"저장: {out} , {out.with_suffix('.txt')}")
    if data["errors"] and not data["articles"]:
        log("모든 요청이 실패했습니다. 네트워크(news.google.com 접근)를 확인하세요.")
        return 2
    if data["errors"]:
        log(f"경고: {len(data['errors'])}개 구간 수집 실패 - 보고서의 '한계'에 적으세요.")
    return 0 if data["articles"] else 1


if __name__ == "__main__":
    sys.exit(main())
