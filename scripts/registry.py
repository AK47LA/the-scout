"""Early-mover registry: the people who posted about a breakout before the benchmark press named it.

Usage: python3 registry.py BACKTEST_DIR REGISTRY.json [--per-case 25]
Reads BACKTEST_DIR/backtest.json and cases.json. For every case with a dated first benchmark headline, finds the
earliest public posts on Bluesky and Hacker News before that date and credits their authors with the lead.
Every score links to the post and the benchmark article it beat. X accounts enter only through the Scout's own
gated browser work, never by scraping. Merges into an existing registry without losing earlier evidence.
"""
import datetime, json, os, statistics, sys, time, urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import signals  # noqa: E402


def bluesky_earliest(q, since, until, n):
    """Walk back to the oldest posts in the window: Bluesky returns newest first."""
    posts, cursor, pages, refused = [], None, 0, False
    while pages < 6:
        params = {"q": q, "since": f"{since}T00:00:00Z", "until": f"{until}T00:00:00Z", "limit": 100, "sort": "latest"}
        if cursor:
            params["cursor"] = cursor
        try:
            d, _ = signals.get_json("https://api.bsky.app/xrpc/app.bsky.feed.searchPosts?" + urllib.parse.urlencode(params))
        except Exception:
            if posts:  # keep what we have; a refused later page is recorded, not fatal
                refused = True
                break
            raise
        posts += d.get("posts", [])
        cursor, pages = d.get("cursor"), pages + 1
        if not cursor:
            break
        time.sleep(1.2)
    out = []
    for p in posts:
        a = p.get("author", {})
        rkey = p["uri"].rsplit("/", 1)[-1]
        out.append({"platform": "bluesky", "handle": a.get("handle"), "profile_url": f"https://bsky.app/profile/{a.get('handle')}",
                    "post_url": f"https://bsky.app/profile/{a.get('handle')}/post/{rkey}",
                    "posted_at": (p.get("record") or {}).get("createdAt", "")[:10], "text": ((p.get("record") or {}).get("text") or "")[:160],
                    "likes": p.get("likeCount"), "reposts": p.get("repostCount")})
    out.sort(key=lambda x: x["posted_at"])
    return out[:n], {"pages": pages, "truncated": bool(cursor), "later_page_refused": refused}


def hn_earliest(q, since, until, n):
    a = int(datetime.datetime.fromisoformat(f"{since}T00:00:00+00:00").timestamp())
    b = int(datetime.datetime.fromisoformat(f"{until}T00:00:00+00:00").timestamp())
    hits, page = [], 0
    while page < 5:
        d, _ = signals.get_json("https://hn.algolia.com/api/v1/search_by_date?" + urllib.parse.urlencode(
            {"query": signals.hn_query(q), "tags": "(story,comment)", "hitsPerPage": 100, "page": page, "typoTolerance": "false",
             "numericFilters": f"created_at_i>={a},created_at_i<{b}"}))
        hits += d.get("hits", [])
        page += 1
        if page >= d.get("nbPages", 0):
            break
    out = [{"platform": "hackernews", "handle": h.get("author"), "profile_url": f"https://news.ycombinator.com/user?id={h.get('author')}",
            "post_url": f"https://news.ycombinator.com/item?id={h.get('objectID')}", "posted_at": (h.get("created_at") or "")[:10],
            "text": (h.get("title") or h.get("comment_text") or "")[:160], "points": h.get("points")} for h in hits if h.get("author")]
    out.sort(key=lambda x: x["posted_at"])
    return out[:n], {"pages": page, "total": len(hits)}


def main():
    bdir, reg_path = sys.argv[1], sys.argv[2]
    per = int(sys.argv[sys.argv.index("--per-case") + 1]) if "--per-case" in sys.argv else 25
    bt = json.load(open(os.path.join(bdir, "backtest.json")))
    cases = {c["id"]: c for c in json.load(open(os.path.join(bdir, "cases.json")))["cases"]}
    reg = json.load(open(reg_path)) if os.path.exists(reg_path) else {"accounts": {}, "receipts": []}
    for row in bt["cases"]:
        fb = row.get("first_benchmark")
        if not fb or row["kind"] != "breakout":
            continue
        ent = cases[row["id"]]["entity"]
        bench = fb["published"][:10]
        for src, fn in (("bluesky", bluesky_earliest), ("hackernews", hn_earliest)):
            qs = ent.get(src)
            if not qs:
                continue
            # The run-up: eight weeks before this source's first flag, never past the first headline.
            known = (row.get("per_source", {}).get(src) or {}).get("flag_known_at")
            anchor = min(known, bench) if known else bench
            since = (datetime.date.fromisoformat(anchor) - datetime.timedelta(days=63)).isoformat()
            until = min(bench, (datetime.date.fromisoformat(anchor) + datetime.timedelta(days=7)).isoformat())
            for q in (qs if isinstance(qs, list) else [qs]):
                try:
                    posts, info = fn(q, since, until, per)
                except Exception as e:
                    reg["receipts"].append({"case": row["id"], "source": src, "query": q, "outcome": "failed", "error": str(e)[:160]})
                    continue
                reg["receipts"].append({"case": row["id"], "source": src, "query": q, "outcome": "ok", "window": [since, until], **info})
                for p in posts:
                    if not p["posted_at"] or not p["handle"]:
                        continue
                    lead = (datetime.date.fromisoformat(bench) - datetime.date.fromisoformat(p["posted_at"])).days
                    if lead <= 0:
                        continue
                    key = f"{p['platform']}:{p['handle']}"
                    acc = reg["accounts"].setdefault(key, {"platform": p["platform"], "handle": p["handle"], "profile_url": p["profile_url"],
                                                          "lanes": [], "evidence": []})
                    if row["lane"] not in acc["lanes"]:
                        acc["lanes"].append(row["lane"])
                    if not any(e["post_url"] == p["post_url"] for e in acc["evidence"]):
                        acc["evidence"].append({"case": row["id"], "post_url": p["post_url"], "posted_at": p["posted_at"],
                                                "benchmark_url": fb["url"], "benchmark_outlet": fb["outlet"], "benchmark_date": bench,
                                                "lead_days": lead, "text": p["text"]})
                time.sleep(2)
    import re as _re
    feedlike = _re.compile(r"news|feed|bot|rss|aggregat|alerts?|digest|daily|trending|brid\.gy|activitypub|awakari|mirror|repost", _re.I)
    for acc in reg["accounts"].values():
        acc["likely_feed"] = bool(feedlike.search(acc["handle"] or ""))  # flagged for the Reviewer, not deleted
        cases_hit = {e["case"] for e in acc["evidence"]}
        acc["cases_early"] = len(cases_hit)
        acc["median_lead_days"] = statistics.median([max(e["lead_days"] for e in acc["evidence"] if e["case"] == c) for c in cases_hit])
    ranked = sorted(reg["accounts"].values(), key=lambda a: (-a["cases_early"], -a["median_lead_days"]))
    reg["ranked"] = [f"{a['platform']}:{a['handle']}" for a in ranked]
    reg["updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    reg["method"] = ("Earliest public Bluesky posts and Hacker News stories or comments naming each breakout in the run-up: "
                     "the nine weeks before that source's first flag (or the first headline, if earlier), up to one week after the flag. "
                     "Lead = benchmark date minus post date. Accounts early on more than one case rank first.")
    json.dump(reg, open(reg_path, "w"), indent=1)
    print(f"{len(reg['accounts'])} accounts; multi-case early movers: {sum(1 for a in ranked if a['cases_early'] > 1)}")
    for a in ranked[:15]:
        print(f"  {a['platform']:<10} {a['handle'][:32]:<32} cases {a['cases_early']}  median lead {a['median_lead_days']}d  {a['lanes']}")


if __name__ == "__main__":
    main()
