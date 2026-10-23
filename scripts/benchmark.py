"""Benchmark search for a ledger row: enumerate each fixed outlet's sitemap for a window, then read candidate pages.

Usage: python3 benchmark.py OUTLETS.json QUERY.json OUT.json
OUTLETS.json: [{"id", "name", "sitemaps": ["https://site/post-sitemap{yyyymm}.xml", "https://site/entries/{yyyy}/{mm}"]}]
QUERY.json:   {"row": "id", "window_start": "YYYY-MM-DD", "window_end": "YYYY-MM-DD", "slug_patterns": ["regex", ...]}
Coverage per outlet is "enumerated" only when every sitemap loaded and its dates reach back past window_start;
otherwise "partial". Slug filtering can miss an article whose URL lacks the keywords, so pair this with a content
search and record both. Read-only.
"""
import datetime, gzip, html, json, re, sys, time, urllib.error, urllib.request

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"


def get(url, timeout=40):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read()
        status = r.status
    if body[:2] == b"\x1f\x8b":
        body = gzip.decompress(body)
    return status, body.decode("utf-8", "replace")


def _month_key(url):
    m = re.search(r"(20\d\d)[-/]?(\d\d)(?!\d)", url)
    return m.group(0).replace("/", "").replace("-", "") if m else url


def months_between(a, b):
    y, m = a.year, a.month
    while (y, m) <= (b.year, b.month):
        yield y, m
        m += 1
        if m == 13:
            y, m = y + 1, 1


def parse_sitemap(xml):
    if "<sitemapindex" in xml:
        return "index", re.findall(r"<loc>\s*([^<]+?)\s*</loc>", xml)
    urls = []
    for block in re.findall(r"<url>(.*?)</url>", xml, re.S):
        loc = re.search(r"<loc>\s*([^<]+?)\s*</loc>", block)
        if not loc:
            continue
        lm = re.search(r"<lastmod>\s*([^<]+?)\s*</lastmod>", block)
        pub = re.search(r"<news:publication_date>\s*([^<]+?)\s*</news:publication_date>", block)
        urls.append({"url": html.unescape(loc.group(1)), "lastmod": lm.group(1) if lm else None,
                     "news_published": pub.group(1) if pub else None})
    return "urlset", urls


def url_date(url):
    m = re.search(r"/(20\d\d)/(\d\d)/(\d\d)/", url)
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None


def page_meta(url):
    try:
        status, body = get(url)
    except urllib.error.HTTPError as e:
        return {"fetch": f"HTTP {e.code}", "published": url_date(url), "date_source": "url path" if url_date(url) else None}
    except Exception as e:  # recorded, never treated as absence
        return {"fetch": str(e)[:120], "published": url_date(url), "date_source": "url path" if url_date(url) else None}
    title = (re.search(r'<meta[^>]+property="og:title"[^>]+content="([^"]*)"', body)
             or re.search(r"<title>([^<]*)</title>", body))
    pub = (re.search(r'<meta[^>]+property="article:published_time"[^>]+content="([^"]*)"', body)
           or re.search(r'"datePublished"\s*:\s*"([^"]+)"', body)
           or re.search(r'<time[^>]+datetime="([^"]+)"', body))
    return {"fetch": f"HTTP {status}", "title": html.unescape(title.group(1)).strip() if title else None,
            "published": pub.group(1) if pub else url_date(url), "date_source": "page" if pub else ("url path" if url_date(url) else None)}


def continuous_from(urls):
    """Earliest day from which every day up to the newest has at least one URL by lastmod."""
    days = sorted({u["lastmod"][:10] for u in urls if u["lastmod"]})
    if not days:
        return None
    have, d = set(days), datetime.date.fromisoformat(days[-1])
    while (d - datetime.timedelta(days=1)).isoformat() in have:
        d -= datetime.timedelta(days=1)
    return d.isoformat()


def run(outlets, query):
    ws = datetime.date.fromisoformat(query["window_start"])
    we = datetime.date.fromisoformat(query["window_end"])
    pats = [re.compile(p, re.I) for p in query["slug_patterns"]]
    out = {"row": query["row"], "window": [query["window_start"], query["window_end"]],
           "slug_patterns": query["slug_patterns"], "searched_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
           "method": "Full sitemap enumeration for the window, slug-pattern candidates, each candidate page read for title and publish time.",
           "outlets": []}
    for o in outlets:
        rec = {"id": o["id"], "name": o["name"], "sitemaps": [], "urls_in_window": 0, "candidates": []}
        queue = []
        for y, m in months_between(ws, we):  # month by month across every template, oldest first
            for tmpl in o["sitemaps"]:
                if "{" in tmpl:
                    queue.append(tmpl.format(yyyymm=f"{y}{m:02d}", yyyy=y, mm=f"{m:02d}", m=m))  # {m}: unpadded month
        queue += [t for t in o["sitemaps"] if "{" not in t]
        seen, urls, ok = set(), [], True
        stop_after_match, last_month = query.get("earliest_only", False), None
        while queue:
            if (stop_after_match and urls and _month_key(queue[0]) != last_month
                    and any(any(p.search(u["url"]) for p in pats) for u in urls)):
                rec["stopped_early"] = "earliest_only: later months not needed once a month has matches"
                break
            sm = queue.pop(0)
            last_month = _month_key(sm)
            if sm in seen:
                continue
            seen.add(sm)
            try:
                status, xml = get(sm)
                kind, items = parse_sitemap(xml)
                if kind == "index":
                    # follow only children that could cover the window
                    keep = [u for u in items if any(f"{y}{m:02d}" in u or f"{y}/{m:02d}" in u or f"{y}-{m:02d}" in u
                                                    for y, m in months_between(ws, we))] or items
                    queue += keep
                    rec["sitemaps"].append({"url": sm, "status": status, "kind": "index", "children_followed": len(keep)})
                else:
                    lms = sorted(u["lastmod"][:10] for u in items if u["lastmod"])
                    rec["sitemaps"].append({"url": sm, "status": status, "kind": "urlset", "urls": len(items),
                                            "oldest_lastmod": lms[0] if lms else None, "newest_lastmod": lms[-1] if lms else None})
                    urls += items
            except urllib.error.HTTPError as e:
                ok = False
                rec["sitemaps"].append({"url": sm, "status": e.code, "error": f"HTTP {e.code}"})
            except Exception as e:
                ok = False
                rec["sitemaps"].append({"url": sm, "status": None, "error": str(e)[:160]})
            time.sleep(0.5)
        templated = any("{" in t for t in o["sitemaps"])
        if templated:
            in_win = urls  # month sitemaps hold the URLs published that month
        else:
            in_win = [u for u in urls if not u["lastmod"] or u["lastmod"][:10] >= query["window_start"]]
        rec["urls_in_window"] = len(in_win)
        cont = None if templated else continuous_from(urls)
        reaches = templated or bool(cont and cont <= query["window_start"])
        rec["coverage"] = "enumerated" if ok and urls and reaches else "partial"
        if not reaches and urls:
            rec["coverage_note"] = f"Flat sitemap is continuous only from {cont}, after the window start."
        matched = [u for u in in_win if any(p.search(u["url"]) for p in pats)]
        cap = query.get("max_candidates", 60)
        if len(matched) > cap:
            rec["candidates_capped"] = f"{len(matched)} slug matches; read the {cap} with the earliest month or lastmod"
            matched = sorted(matched, key=lambda u: (url_date(u["url"]) or u["lastmod"] or "9"))[:cap]
        for u in matched:
            meta = page_meta(u["url"])
            rec["candidates"].append(dict(u, **meta))
            time.sleep(0.5)
        out["outlets"].append(rec)
    return out


if __name__ == "__main__":
    outlets = json.load(open(sys.argv[1]))
    query = json.load(open(sys.argv[2]))
    res = run(outlets, query)
    json.dump(res, open(sys.argv[3], "w"), indent=1)
    for r in res["outlets"]:
        print(f"{r['name']:<28} {r['coverage']:<10} in-window {r['urls_in_window']:>5}  candidates {len(r['candidates'])}")
        for c in r["candidates"]:
            print(f"    {(c.get('published') or c.get('news_published') or c.get('lastmod') or '')[:16]}  {(c.get('title') or c['url'])[:110]}")
