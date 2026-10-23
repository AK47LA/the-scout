"""Keep the X search list on what is trending: add this week's strongest new names and terms, drop the ones that went quiet.

  python3 xkeywords.py update KEYWORDS.json [--states STATES_X.json] [--terms TERMS.json] [--posts POSTS.jsonl] [--max 6] [--keep-days 21]
Adds at most --max searches a week to the "auto" lane, from:
  states   items trendstate.py called NEW or JUST TRENDING on X, strongest first
  terms    phrases terms.py found jumping on Hacker News
An auto search that is not seen again within --keep-days is removed, so the list stays short. Hand-written lanes are never touched.
"""
import datetime, json, re, sys

NOISE = re.compile(r"^(link in bio|read more|thank you|happy|new york|los angeles|breaking|watch|live|today|out now|new music|music video|official video|"
                   r"pre-?save|global spotify|us spotify|billboard hot 100|billboard 200|hot 100)$", re.I)


def generic(name):
    """Only ordinary English words and no digits: a phrase, not a name worth searching."""
    import os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import terms
    words = re.findall(r"[a-z0-9.']+", name.lower())
    return not any(re.search(r"\d", w) for w in words) and all(w in terms.DICT or w.rstrip("s") in terms.DICT for w in words)


CORE = {"owner", "owner-named", "owner-follows", "labs", "builders", "ai-news-and-analysis", "creative-ai", "music-industry"}


def spread(posts_p, name):
    """Which lanes and how many accounts named it in the last week."""
    if not posts_p:
        return None
    cut = (datetime.date.today() - datetime.timedelta(days=7)).isoformat()
    pat = re.compile(r"(?<![\w])" + re.escape(name) + r"(?![\w])", re.I)
    lanes, accts = set(), set()
    for l in open(posts_p):
        r = json.loads(l)
        if r["posted_at"][:10] >= cut and pat.search(r["text"]):
            lanes.add(r.get("lane")); accts.add(r["account"].lower())
    return lanes, accts


def candidates(states_p, terms_p, posts_p=None):
    out = []
    if states_p:
        for r in json.load(open(states_p)).get("rows", []):
            if r["state"] in ("NEW", "JUST TRENDING") and r.get("value", 0) >= 5:
                sp = spread(posts_p, r["name"])
                if sp and not (sp[0] & CORE or len(sp[1]) >= 3):  # culture gossip needs three separate accounts
                    continue
                out.append((r["name"], r["value"], "x " + r["state"].lower()))
    if terms_p:
        for t in json.load(open(terms_p)).get("sources", {}).get("hackernews", {}).get("terms", [])[:15]:
            if len(t["term"]) > 4 and not re.fullmatch(r"[\d.]+", t["term"]) and " " in t["term"]:  # single words are rarely news
                out.append((t["term"], t.get("recent_docs", 0), "hacker news jump"))
    seen, uniq = set(), []
    out.sort(key=lambda x: (-len(x[0]), -x[1]))  # longer phrases first, so "mac menu bar" swallows "mac menu"
    for name, score, why in sorted(out, key=lambda x: -x[1]):
        k = name.lower()
        if k in seen or NOISE.match(name) or len(name) < 4 or generic(name) or any(k in s2 and k != s2 for s2 in seen):
            continue
        seen.add(k)
        uniq.append((name, score, why))
    return uniq


def update(path, states_p=None, terms_p=None, max_new=6, keep_days=21, posts_p=None):
    kw = json.load(open(path))
    today = datetime.date.today().isoformat()
    auto = {a["query"].strip('"').lower(): a for a in kw.get("auto", [])}
    hand = " ".join(q.lower() for qs in kw.get("lanes", {}).values() for q in qs)
    added = 0
    for name, score, why in candidates(states_p, terms_p, posts_p):
        k = name.lower()
        if k in auto:
            auto[k]["last_seen"] = today
            continue
        if k in hand or added >= max_new:
            continue
        auto[k] = {"query": f'"{name}"', "added": today, "last_seen": today, "why": f"{why}, {score:g} this week"}
        added += 1
    cutoff = (datetime.date.today() - datetime.timedelta(days=keep_days)).isoformat()
    dropped = [a["query"] for a in auto.values() if a["last_seen"] < cutoff]
    kw["auto"] = [a for a in auto.values() if a["last_seen"] >= cutoff]
    kw["updated"] = today
    json.dump(kw, open(path, "w"), indent=1, ensure_ascii=False)
    return {"added": added, "dropped": dropped, "auto_now": [a["query"] for a in kw["auto"]]}


if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[1] != "update":
        sys.exit(__doc__)
    arg = lambda k, d=None: sys.argv[sys.argv.index(k) + 1] if k in sys.argv else d
    print(json.dumps(update(sys.argv[2], arg("--states"), arg("--terms"), int(arg("--max", 6)), int(arg("--keep-days", 21)), arg("--posts")), indent=1))
