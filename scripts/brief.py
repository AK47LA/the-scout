"""The week in one place: what came in, what went out, the move, four posts to make, and what the press wrote.

  python3 brief.py OUT.json [--states states-signals.json] [--states states-x.json] [--headlines headlines.json]
                            [--x-report report.json] [--basket basket.json] [--watchlist x-watchlist.json] [--x-weeks N]
                            [--saves saves.json]

Built only from this run's measured files: trendstate.py states, headlines.py, xpublic.py report. Every line keeps the
number it rests on. The move and the four posts are starting points picked by fixed rules from those numbers; the take
is the reader's. Nothing here claims a thing was spotted early or predicted.
"""
import datetime, json, os, re, sys

LABEL = {"wikipedia": "Wikipedia views", "bluesky": "Bluesky posts", "hackernews": "Hacker News stories", "github": "GitHub stars",
         "youtube": "YouTube", "chartmetric": "Chartmetric", "x": "mentions on your X watchlist"}
ORDER = {"NEW": 0, "JUST TRENDING": 1, "RISING": 2, "PEAKING": 3, "STEADY": 4, "FADING": 5, "GONE": 6}
IN, OUT = ("NEW", "JUST TRENDING", "RISING"), ("FADING", "GONE")
CJK = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af\uff00-\uffef]")


def line(r):
    src = LABEL.get(r["source"], r["source"])
    if r["state"] == "NEW":
        return f"new this week in {src} ({r['value']:,.0f})"
    if r["state"] in ("JUST TRENDING", "RISING"):
        pct = r.get("vs_prior4_pct")
        return f"{src} up {pct:,}% on its four-week average" if pct is not None else f"{src} jumped this week"
    if r["state"] == "PEAKING":
        return f"{src} at {r['pct_of_peak']}% of its one-year high"
    if r["state"] == "FADING":
        drop = r.get("vs_prior4_pct")
        return f"{src} down to {r['pct_of_peak']}% of its one-year high" + (f", {abs(drop)}% under its four-week average" if drop and drop < 0 else "")
    if r["state"] == "GONE":
        return f"{src} under 10% of its one-year high"
    return f"{src} steady"


def pick(rows):
    """One row per name: its strongest state; within a state, the biggest change."""
    best = {}
    for r in rows:
        k = r["name"].lower()
        key = (ORDER[r["state"]], -(r.get("vs_prior4_pct") or 0))
        if k not in best or key < best[k][0]:
            best[k] = (key, r)
    return [r for _, r in sorted(best.values(), key=lambda kv: kv[0])]


def short(s, n):
    s = " ".join((s or "").split())
    return s if len(s) <= n else s[: n - 1].rsplit(" ", 1)[0] + "…"


def clipped(title):
    """A title the feed cut short: a quote or bracket opened and never closed ('"Unloveu" (Live f')."""
    return (title.count('"') % 2 == 1 or title.count("“") != title.count("”")
            or title.count("(") > title.count(")") or title.count("[") > title.count("]"))


def spread(items, n):
    """Up to n headlines, one per outlet first, then the rest in their order."""
    first, outlets = [], set()
    for h in items:
        if h["outlet"] not in outlets:
            outlets.add(h["outlet"])
            first.append(h)
    return (first + [h for h in items if h not in first])[:n]


def first_post(posts):
    if not posts:
        return "No posts to suggest from this week's numbers."
    say = posts[0].get("say") or posts[0]["title"]
    count = {1: "One post", 2: "Two posts", 3: "Three posts"}.get(len(posts), "Four posts")
    return f"{count} to make. First: " + say + ("" if say[-1:] in ".?!" else ".")


X_WEEKS_NEEDED = 4  # X history starts at the first pull, so early weeks look like jumps; X joins in or out after four weekly pulls


def build(states=(), headlines=None, x_report=None, basket=None, today=None, x_weeks=0, watchlist=None, saves=None):
    today = today or datetime.date.today()
    rows = [r for s in states for r in s.get("rows", [])]
    accounts = {(a.get(k) or "").lower() for a in (watchlist or {}).get("accounts", []) for k in ("handle", "name")} - {""}
    tracked = {(e.get("name") or "").lower() for e in (basket or {}).get("entities", [])} - {""}
    x_note = None
    if any(r["source"] == "x" for r in rows) and x_weeks < X_WEEKS_NEEDED:
        x_note = f"X joins in or out after {X_WEEKS_NEEDED} weekly runs, once it has history to judge against ({x_weeks} so far)."
    rows = [r for r in rows if r["source"] != "x" or (x_weeks >= X_WEEKS_NEEDED and r["name"].lower() not in accounts)]
    saturated = [r for s in states for r in s.get("saturated", [])]
    best = pick(rows)
    # page limits: 3 in, 1 at its high, 2 out fit one 1080x1350 page with room for long names
    came_in = [dict(r, line=line(r)) for r in best if r["state"] in IN][:3]
    peaking = [dict(r, line=line(r)) for r in best if r["state"] == "PEAKING"][:1]
    # going out means falling now: FADING or GONE and at least 10% under its own four-week average
    # (a name flat at a low level after one huge spike, or drifting by a point or two, isn't leaving)
    falling = [r for r in best if r["state"] in OUT and (r.get("vs_prior4_pct") or 0) <= -10]  # a real drop, not a 1% drift
    went_out = [dict(r, line=line(r)) for r in sorted(falling, key=lambda r: r.get("vs_prior4_pct") or 0)][:2]
    hl = headlines or {}
    by_name = hl.get("by_name") or {}
    capped = set(hl.get("capped") or [])  # Google News returns at most 100 items a search: those counts are floors
    xr = x_report or {}

    # The move: one fixed rule, written from the numbers
    if came_in:  # the things the reader chose to track come first
        top = max(came_in, key=lambda r: (r["name"].lower() in tracked, r["state"] != "NEW", r.get("vs_prior4_pct") or 0))
        press = by_name.get(top["name"])
        named = (f", and at least {press} headlines named it this week" if top["name"] in capped
                 else f", and {press} headlines named it this week") if press else ""
        move = {"name": top["name"], "line": f"Post about {top['name']} this week.",
                "why": top["line"][0].upper() + top["line"][1:] + named + "."}
    elif peaking:
        top = peaking[0]
        move = {"name": top["name"], "line": f"Say your piece on {top['name']} now.", "why": top["line"][0].upper() + top["line"][1:] + "."}
    else:
        named = sorted(by_name.items(), key=lambda kv: -kv[1])
        if named and named[0][1]:
            floor = "At least " if named[0][0] in capped else ""
            move = {"name": named[0][0], "line": f"Nothing on your list jumped. The press wrote most about {named[0][0]}.",
                    "why": f"{floor}{named[0][1]} headlines named it this week. Your take on that is the post."}
        else:
            move = {"name": None, "line": "Nothing on your list moved enough to call this week.",
                    "why": "Run it again next week: each run adds a week of history to judge against."}
    # a clear drop, and the press isn't still writing about it: only then is it a name to step back from
    quiet = [r for r in went_out if by_name.get(r["name"], 0) < 10 and (r.get("vs_prior4_pct") or 0) <= -15]
    if quiet:
        move["ease_off"] = f"Ease off {quiet[0]['name']}: {quiet[0]['line']}."

    # Four posts: starting points, each tied to its receipt
    posts = []
    used = set()
    for r in came_in:
        if len(posts) >= 2:
            break
        posts.append({"kind": "EXPLAIN THE JUMP", "title": f"Why is everyone suddenly talking about {r['name']}?",
                      "first_line": f"{r['name']}: {r['line']}. Here's what's behind it.", "receipt": r["line"]})
        used.add(r["name"].lower())
    for r in peaking:
        if len(posts) >= 3:
            break
        posts.append({"kind": "YOUR TAKE", "title": f"My take on {r['name']}, while everyone's watching.",
                      "first_line": f"Everyone's talking about {r['name']}. Here's what I think they're missing.", "receipt": r["line"]})
        used.add(r["name"].lower())
    for r in quiet[:1]:
        if len(posts) >= 3:
            break
        posts.append({"kind": "WHAT'S GOING OUT", "title": f"What {r['name']}'s slide tells us.",
                      "first_line": f"{r['name']}: {r['line']}. Here's where the attention went.", "receipt": r["line"]})
        used.add(r["name"].lower())
    big = {o.get("name") or o.get("rss") for o in (basket or {}).get("outlets", [])} or {o for o, _ in (hl.get("top_outlets") or [])[:5]}
    # English only on the page (the copy check's rule): a headline or post in Chinese, Japanese or Korean script is left out
    # and a title the feed cut short mid-phrase is left out too: half a headline isn't a receipt
    ranked = sorted((h for h in hl.get("headlines", []) if not CJK.search(h["title"]) and not clipped(h["title"])),
                    key=lambda h: h["published"], reverse=True)
    ranked = [h for h in ranked if h["outlet"] in big] + [h for h in ranked if h["outlet"] not in big]  # known outlets first, newest first
    stories = [h for h in ranked if h.get("names")] + [h for h in ranked if not h.get("names")]
    top_posts = sorted((p for lane in (xr.get("top_by_lane") or {}).values() for p in lane if not CJK.search(p.get("text") or "")),  # posts naming a tracked name first
                       key=lambda p: (not any(n in (p.get("text") or "").lower() for n in tracked), -((p.get("metrics") or {}).get("views") or 0)))[:1]
    outlets_used, held = set(), []  # a name or outlet already covered waits until nothing fresher is left
    while len(posts) < 4 and (stories or top_posts or held):
        if top_posts and (len(posts) % 2 == 1 or not (stories or held)):
            p = top_posts.pop(0)
            views = (p.get("metrics") or {}).get("views")
            posts.append({"kind": "REACT", "title": f"Answer {p['author']}: “{short(p.get('text'), 90)}”",
                          "say": f"answer {p['author']} on X",
                          "first_line": f"{p['author']} said it. Here's my read.",
                          "receipt": f"{p['author']} on X" + (f", {views:,} views" if views else "") + f", {p['posted_at'][:10]}"})
        else:
            h = stories.pop(0) if stories else held.pop(0)
            if stories and (any(n.lower() in used for n in h.get("names", [])) or h["outlet"] in outlets_used):
                held.append(h)
                continue
            say = "react to this week's story" if CJK.search(h["outlet"]) else f"react to this week's {h['outlet']} story"  # the narration stays English
            posts.append({"kind": "REACT", "title": f"My read on: {short(h['title'], 90)}", "say": say,
                          "first_line": "This week's story, and what it means for you.", "receipt": f"{h['outlet']}, {h['published'][:10]}"})
            used.update(n.lower() for n in h.get("names", []))
            outlets_used.add(h["outlet"])
    # From your saves: one thing you sent to The Scout this week, as a "why it works" post (English-script previews only)
    sv = saves or {}
    kept = [i for i in sv.get("items", []) if i.get("outcome") == "ok" and i.get("text") and not CJK.search(i["text"])]
    if kept:
        s0 = kept[0]
        who = s0.get("author") or s0.get("site") or "this"
        posts.insert(1 if posts else 0, {"kind": "FROM YOUR SAVES", "title": f"Why this works: “{short(s0['text'], 80)}”",
                                         "say": f"break down why one of the things you saved works",
                                         "first_line": "I saved this. Here's why it works.",
                                         "receipt": f"{who} on {s0.get('site') or 'the web'}" + (f", saved {s0['saved_at'][:10]}" if s0.get("saved_at") else "")})
    posts = posts[:4]

    press_top = spread([h for h in ranked if h.get("names")] + [h for h in ranked if not h.get("names")], 5)  # your names first
    # a name whose search hit the 100 cap can't be ranked against the others: list it first, marked as "100+"
    most_named = [[n, k, n in capped] for n, k in sorted(by_name.items(), key=lambda kv: (kv[0] not in capped, -kv[1])) if k][:3]
    counts = {"headlines": hl.get("read", 0), "outlets": hl.get("outlets", 0), "x_posts": xr.get("recent_posts", 0),
              "names": len((basket or {}).get("entities", [])), "saves": sv.get("read", 0)}
    feeds = hl.get("feeds") or []
    hl_state = "not read" if headlines is None else ("failed" if feeds and all(f.get("outcome") != "ok" for f in feeds) else "ok")
    x_state = "not read" if x_report is None else "ok"

    def stamp(n, state):
        return f"{n:,}" if state == "ok" else ("FAILED" if state == "failed" else "NOT READ")
    stamps = {"headlines": stamp(counts["headlines"], hl_state), "outlets": stamp(counts["outlets"], hl_state),
              "x_posts": stamp(counts["x_posts"], x_state)}

    def names(rs):
        return ", ".join(r["name"] for r in rs)
    if hl_state == "ok":
        cover = f"This week The Scout read {counts['headlines']:,} headlines from {counts['outlets']:,} outlets"
        cover += f" and {counts['x_posts']:,} posts from your X watchlist." if counts["x_posts"] else "."
    else:
        cover = "The headlines didn't come back this run, so this edition runs on the history data."
        cover += f" It read {counts['x_posts']:,} posts from your X watchlist." if counts["x_posts"] else ""
    states_v = (f"Coming in: {names(came_in)}. " if came_in else "Nothing on your list came in this week. ")
    states_v += (f"Going out: {names(went_out)}." if went_out else "Nothing went out.")
    return {"made_at": today.isoformat(), "date": today.strftime("%d %b %Y").upper(), "counts": counts, "stamps": stamps,
            "headlines_state": hl_state, "capped": sorted(capped),
            "saves": {"count": sv.get("read", 0), "found": bool(sv.get("found")),
                      "items": [{"author": i.get("author") or i.get("site"), "text": short(i["text"], 140), "site": i.get("site"),
                                 "saved": (i.get("saved_at") or "")[:10]} for i in kept[:5]]},
            "came_in": came_in, "peaking": peaking, "went_out": went_out, "saturated": saturated[:4],
            "move": move, "posts": posts, "x_note": x_note,
            "press": {"read": counts["headlines"], "outlets": counts["outlets"], "most_named": most_named,
                      "top": [{"title": short(h["title"], 110), "outlet": h["outlet"], "date": h["published"][:10], "url": h.get("url")} for h in press_top]},
            "voice": {"cover": cover, "states": states_v, "move": move["line"] + " " + move["why"],
                      # quoted headlines and X posts stay on the page, never in the narration: their words aren't ours to say
                      "posts": first_post(posts),
                      "saves": (f"From your saves: {sv.get('read', 0):,} things you sent to The Scout this week." if sv.get("read") else
                                "Nothing sent to The Scout this week. Share any post to Send to Scout and it shows up here."),
                      "press": (f"The press wrote most about {most_named[0][0]} this week." if most_named and not most_named[0][2] else
                                f"The press wrote about {most_named[0][0]} at least {most_named[0][1]:,} times this week." if most_named else
                                f"{counts['headlines']:,} headlines this week from {counts['outlets']:,} outlets.")},
            "rule": "In and out use trendstate.py on each item's own history. The move and posts are starting points picked by fixed rules from these numbers."}


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    out = sys.argv[1]
    args = sys.argv[2:]
    get = lambda k: [args[i + 1] for i, a in enumerate(args) if a == k and i + 1 < len(args)]
    load = lambda p: json.load(open(p)) if p and os.path.exists(p) else None
    states = [s for s in (load(p) for p in get("--states")) if s]
    first = lambda k: (get(k) or [None])[0]
    res = build(states, load(first("--headlines")), load(first("--x-report")), load(first("--basket")),
                x_weeks=int(first("--x-weeks") or 0), watchlist=load(first("--watchlist")), saves=load(first("--saves")))
    json.dump(res, open(out, "w"), indent=1, ensure_ascii=False)
    print(f"brief: in {[r['name'] for r in res['came_in']]}, out {[r['name'] for r in res['went_out']]}; move: {res['move']['line']}")


if __name__ == "__main__":
    main()
