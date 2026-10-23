"""Keyless discovery: things gaining attention fast, before a call is considered.

Usage: python3 discover.py OUT.json [--days 28] [--lanes music,entertainment,tech]
Feeds:
  github      new repositories created in the last N days, ranked by stars (AI tools and creative tech)
  wikipedia   articles in today's most-viewed list that were absent N days ago, filtered to the lanes by their
              Wikipedia short description
Each candidate carries its evidence. Discovery is a lead list, not a finding: candidates still need the Reviewer,
a novelty check against the benchmark press and a dated call.
"""
import datetime, json, os, re, sys, time, urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import signals  # noqa: E402

LANES = {
    "music": r"\b(singer|rapper|band|album|song|single|musician|dj|record producer|music|composer|k-pop|girl group|boy group)\b",
    "entertainment": r"\b(film|television|tv series|series|show|video game|game|actor|actress|youtuber|streamer|anime|manga|meme|toy|podcast|comedian|influencer|reality)\b",
    "tech": r"\b(software|artificial intelligence|ai|app|application|chatbot|company|startup|programming|language model|robot|device|platform|website)\b",
}
SKIP = re.compile(r"^(Main_Page|Special:|Wikipedia:|Portal:|File:|Help:|Talk:|Category:|Template:)|^Deaths_in_|^\d{4}_in_|_\(disambiguation\)$")


def github_rising(days, per_page=50):
    since = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
    q = f"created:>{since} stars:>200"
    hdr = {"Accept": "application/vnd.github+json"}
    tok = signals.key("github")
    if tok:
        hdr["Authorization"] = f"Bearer {tok}"
    d, _ = signals.get_json("https://api.github.com/search/repositories?" +
                            urllib.parse.urlencode({"q": q, "sort": "stars", "order": "desc", "per_page": per_page}), hdr)
    out = []
    for r in d.get("items", []):
        age = max(1, (datetime.date.today() - datetime.date.fromisoformat(r["created_at"][:10])).days)
        out.append({"feed": "github", "name": r["full_name"], "url": r["html_url"], "description": r.get("description"),
                    "created_at": r["created_at"][:10], "stars": r["stargazers_count"], "stars_per_day": round(r["stargazers_count"] / age, 1),
                    "topics": r.get("topics", [])[:8]})
    return {"query": q, "authenticated": bool(tok), "items": out}


def top_articles(day):
    url = f"https://wikimedia.org/api/rest_v1/metrics/pageviews/top/en.wikipedia/all-access/{day:%Y/%m/%d}"
    d, _ = signals.get_json(url)
    return {a["article"]: a["views"] for a in d["items"][0]["articles"] if not SKIP.search(a["article"])}


def description(title):
    try:
        d, _ = signals.get_json("https://en.wikipedia.org/api/rest_v1/page/summary/" + urllib.parse.quote(title, safe=""))
        return d.get("description") or "", d.get("extract", "")[:240]
    except Exception:
        return "", ""


def wikipedia_rising(days, lanes):
    end = datetime.date.today() - datetime.timedelta(days=2)  # top lists publish a day or two behind
    recent = {}
    for i in range(3):
        for t, v in top_articles(end - datetime.timedelta(days=i)).items():
            recent[t] = recent.get(t, 0) + v
        time.sleep(0.5)
    before = {}
    for i in range(3):
        for t, v in top_articles(end - datetime.timedelta(days=days + i)).items():
            before[t] = before.get(t, 0) + v
        time.sleep(0.5)
    new = sorted(((t, v) for t, v in recent.items() if t not in before), key=lambda x: -x[1])[:150]
    out = []
    for t, v in new:
        desc, extract = description(t)
        lane = next((ln for ln in lanes if re.search(LANES[ln], desc.lower())), None)
        if lane:
            out.append({"feed": "wikipedia", "name": t.replace("_", " "), "lane": lane, "description": desc,
                        "views_last_3_days": v, "absent_from_top_list": f"{days} days earlier", "extract": extract})
        time.sleep(0.2)
    return {"window": [str(end - datetime.timedelta(days=2)), str(end)], "compared_with": str(end - datetime.timedelta(days=days)), "items": out}


if __name__ == "__main__":
    out = sys.argv[1]
    days = int(sys.argv[sys.argv.index("--days") + 1]) if "--days" in sys.argv else 28
    lanes = (sys.argv[sys.argv.index("--lanes") + 1] if "--lanes" in sys.argv else "music,entertainment,tech").split(",")
    res = {"generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(), "days": days, "lanes": lanes, "feeds": {}}
    for name, fn in (("github", lambda: github_rising(days)), ("wikipedia", lambda: wikipedia_rising(days, lanes))):
        try:
            res["feeds"][name] = fn()
        except Exception as e:
            res["feeds"][name] = {"error": str(e)[:200], "items": []}
    json.dump(res, open(out, "w"), indent=1)
    for name, f in res["feeds"].items():
        print(f"{name}: {len(f.get('items', []))} candidates {f.get('error', '')}")
        for it in f.get("items", [])[:12]:
            extra = it.get("stars_per_day") or it.get("views_last_3_days")
            print(f"   {it['name'][:48]:<48} {it.get('lane', '')[:12]:<12} {extra}  {(it.get('description') or '')[:60]}")
