"""New-term finder: words and phrases people suddenly started using, before anyone names them as a trend.

Usage: python3 terms.py OUT.json [--recent-days 21] [--baseline-days 180] [--bluesky "seed one,seed two"] [--x-dir DIR] [--x-manifest PATH]
       [--hn-off]  skip Hacker News (an X-only run)
Reads public text with dates:
  hackernews   front-page and Show HN titles (Algolia), keyless
  bluesky      latest posts for seed topics, keyless (optional; gentle)
  x            post text the Scout saved from its gated X passes (--x-dir: one dated folder per pass, from xpass.py), optional
Compares each word and two- or three-word phrase in the recent window with its own baseline. A term surfaces when
it's new or several times more frequent, with a minimum number of separate posts. Every term carries example posts.
Terms are leads for the Reviewer, then signals.py history and a press novelty check; they are not trends.
"""
import collections, datetime, json, math, re, sys, time, urllib.parse

import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import signals  # noqa: E402

STOP = set("""a about above after again against all also am an and any are as at be because been before being below between both but by can
could did do does doing down during each few for from further had has have having he her here hers him his how i if in into is it its
itself just me more most my no nor not now of off on once only or other our out over own same she should so some such than that the
their them then there these they this those through to too under until up very was we were what when where which while who whom why
will with you your yours via new how why what show ask tell launch hn using use used make made get got one two three first last year
years day days week weeks month months today vs like way ways open source free app apps tool tools based built build building better
best than more less really still want need work works working time thing things people world guide introducing release released""".split())
try:  # ordinary English words never surface alone; names and slang do (agentmaxxing, openclaw, clawdbot)
    DICT = {w.strip().lower() for w in open("/usr/share/dict/words")}
except OSError:
    DICT = set()
WORD = re.compile(r"[a-z0-9][a-z0-9+#.'\-]*[a-z0-9+#]|[a-z0-9]")


def grams(text):
    toks = [re.sub(r"'s$", "", t) for t in WORD.findall(text.lower().replace("’", "'"))]
    out = set()
    for i, t in enumerate(toks):
        if len(t) >= 3 and t not in STOP and not re.fullmatch(r"[\d.,]+", t) and t not in DICT and t.rstrip("s") not in DICT:
            out.add(t)
        for n in (2, 3):
            g = toks[i:i + n]
            if len(g) == n and g[0] not in STOP and g[-1] not in STOP and not any(x.isdigit() for x in g):
                out.add(" ".join(g))
    return out


def hn_docs(start, end):
    """Week by week: Algolia returns at most 1,000 hits per query, so one long window silently truncates."""
    docs, cur = [], start
    while cur < end:
        nxt = min(end, cur + datetime.timedelta(days=7))
        docs += _hn_window(cur, nxt)
        cur = nxt
    seen, out = set(), []
    for x in docs:
        if x["id"] not in seen:
            seen.add(x["id"]); out.append(x)
    return out


def _hn_window(start, end):
    docs = []
    for tag in ("front_page", "show_hn"):
        a, b = int(start.timestamp()), int(end.timestamp())
        page = 0
        while page < 20:
            d, _ = signals.get_json("https://hn.algolia.com/api/v1/search_by_date?" + urllib.parse.urlencode(
                {"tags": tag, "hitsPerPage": 1000, "page": page, "numericFilters": f"created_at_i>={a},created_at_i<{b}"}))
            for h in d.get("hits", []):
                docs.append({"source": "hackernews", "id": h["objectID"], "text": h.get("title") or "", "at": h.get("created_at", "")[:10],
                             "url": f"https://news.ycombinator.com/item?id={h['objectID']}", "points": h.get("points")})
            page += 1
            if page >= d.get("nbPages", 0):
                break
            time.sleep(0.3)
    return docs


def bluesky_docs(seed, start, end, pages=4):
    docs, cursor = [], None
    for _ in range(pages):
        params = {"q": seed, "since": start.strftime("%Y-%m-%dT%H:%M:%SZ"), "until": end.strftime("%Y-%m-%dT%H:%M:%SZ"), "limit": 100, "sort": "latest"}
        if cursor:
            params["cursor"] = cursor
        try:
            d, _ = signals.get_json("https://api.bsky.app/xrpc/app.bsky.feed.searchPosts?" + urllib.parse.urlencode(params))
        except Exception:
            break
        for p in d.get("posts", []):
            h = p.get("author", {}).get("handle")
            docs.append({"source": "bluesky", "id": p["uri"], "author": h, "text": (p.get("record") or {}).get("text", ""), "at": (p.get("record") or {}).get("createdAt", "")[:10],
                         "url": f"https://bsky.app/profile/{h}/post/{p['uri'].rsplit('/', 1)[-1]}"})
        cursor = d.get("cursor")
        if not cursor:
            break
        time.sleep(1.2)
    return docs


def x_docs(manifest_path):
    if not manifest_path or not os.path.exists(manifest_path):
        return []
    m = json.load(open(manifest_path))
    return [{"source": "x", "id": it["id"], "text": it.get("text", ""), "at": (it.get("captured_at") or "")[:10], "url": it.get("url"),
             "author": it.get("author")} for it in m.get("items", []) if it.get("text")]


def x_passes(x_dir):
    """Every dated X pass (x_dir/YYYY-MM-DD/manifest.json): the newest is recent, the ones before it are the baseline."""
    if not x_dir or not os.path.isdir(x_dir):
        return None, [], []
    days = sorted(d for d in os.listdir(x_dir) if re.fullmatch(r"\d{4}-\d{2}-\d{2}", d)
                  and os.path.exists(os.path.join(x_dir, d, "manifest.json")))
    if not days:
        return None, [], []
    base = [doc for d in days[:-1] for doc in x_docs(os.path.join(x_dir, d, "manifest.json"))]
    return days[-1], x_docs(os.path.join(x_dir, days[-1], "manifest.json")), base


def dedupe(docs, per_author=2):
    """Spam reposts the same text many times and one account can flood a seed: keep distinct texts, two per author."""
    seen, by_author, out = set(), collections.Counter(), []
    for d in docs:
        sig = re.sub(r"https?://\S+|[^a-z0-9 ]", "", d["text"].lower())[:90].strip()
        a = d.get("author")
        if not sig or sig in seen or (a and by_author[a] >= per_author):
            continue
        seen.add(sig)
        if a:
            by_author[a] += 1
        out.append(d)
    return out


def surface(recent, base, min_docs, ratio_min=3.0, top=40):
    rc, bc = collections.Counter(), collections.Counter()
    ex = collections.defaultdict(list)
    recent, base = dedupe(recent), dedupe(base)
    for d in recent:
        for g in grams(d["text"]):
            rc[g] += 1
            if len(ex[g]) < 3:
                ex[g].append({"text": d["text"][:140], "url": d["url"], "at": d["at"]})
    for d in base:
        for g in grams(d["text"]):
            bc[g] += 1
    nr, nb = max(1, len(recent)), max(1, len(base))
    rows = []
    for g, r in rc.items():
        if r < min_docs:
            continue
        b = bc.get(g, 0)
        ratio = (r / nr) / ((b + 0.5) / nb)
        if b == 0 or ratio >= ratio_min:
            rows.append({"term": g, "recent_docs": r, "baseline_docs": b, "lift": round(ratio, 1), "new": b == 0,
                         "score": round(r * math.log(1 + ratio), 2), "examples": ex[g]})
    rows.sort(key=lambda x: -x["score"])
    # drop phrases contained in a stronger phrase with the same documents
    kept = []
    for row in rows:
        if any(row["term"] in k["term"] and k["recent_docs"] >= row["recent_docs"] * 0.8 for k in kept):
            continue
        kept.append(row)
    return kept[:top]


def main():
    out = sys.argv[1]
    arg = lambda k, d: sys.argv[sys.argv.index(k) + 1] if k in sys.argv else d
    rdays, bdays = int(arg("--recent-days", 21)), int(arg("--baseline-days", 180))
    now = datetime.datetime.now(datetime.timezone.utc).replace(minute=0, second=0, microsecond=0)
    r0, b0 = now - datetime.timedelta(days=rdays), now - datetime.timedelta(days=rdays + bdays)
    res = {"generated_at": now.isoformat(), "recent": [r0.date().isoformat(), now.date().isoformat()],
           "baseline": [b0.date().isoformat(), r0.date().isoformat()], "sources": {}}
    if "--hn-off" not in sys.argv:
        hn_recent, hn_base = hn_docs(r0, now), hn_docs(b0, r0)
        res["sources"]["hackernews"] = {"recent_docs": len(hn_recent), "baseline_docs": len(hn_base),
                                        "terms": surface(hn_recent, hn_base, min_docs=int(arg("--min-hn", 4)))}
    seeds = [s.strip() for s in arg("--bluesky", "").split(",") if s.strip()]
    for seed in seeds:
        rec = bluesky_docs(seed, r0, now)
        base = bluesky_docs(seed, b0, r0)
        res["sources"][f"bluesky:{seed}"] = {"recent_docs": len(rec), "baseline_docs": len(base),
                                             "terms": surface(rec, base, min_docs=int(arg("--min-bsky", 6)))}
    latest, xr, xb = x_passes(arg("--x-dir", None))
    if xr:
        note = (f"X pass {latest} against {len(xb)} posts from earlier passes" if xb else
                f"First X pass ({latest}): no X baseline yet, so these are the most repeated terms, not jumps. A second pass makes them comparable.")
        res["sources"]["x"] = {"recent_docs": len(xr), "baseline_docs": len(xb), "pass": latest, "note": note,
                               "terms": surface(xr, xb, min_docs=int(arg("--min-x", 3)))}
    xd = x_docs(arg("--x-manifest", None))
    if xd and not xr:
        res["sources"]["x"] = {"docs": len(xd), "note": "X text from saved gated captures; no baseline until a second pass exists",
                               "terms": surface(xd, [], min_docs=2)}
    json.dump(res, open(out, "w"), indent=1)
    for src, s in res["sources"].items():
        print(f"== {src}: {s.get('recent_docs', s.get('docs'))} recent posts vs {s.get('baseline_docs', 0)} baseline" + (f"  ({s['note']})" if s.get("note") else ""))
        for t in s["terms"][:25]:
            print(f"   {t['term']:<34} recent {t['recent_docs']:>3}  before {t['baseline_docs']:>4}  {'NEW' if t['new'] else str(t['lift']) + 'x'}")


if __name__ == "__main__":
    main()
