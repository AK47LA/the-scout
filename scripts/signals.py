"""Public signals for a watch: behaviour data with history, one detection rule, a durability check.

Usage:
  python3 signals.py pull BASKET.json OUT_DIR [--refresh]     fetch (cached per source and entity)
  python3 signals.py analyze BASKET.json OUT_DIR              weekly series, flags, control false alarms, durability

BASKET.json:
{"watch_id": "...", "start": "2023-01-02", "end": "2026-10-19",
 "entities": [{"name": "Labubu", "wikipedia": "Labubu", "hackernews": "labubu", "bluesky": "labubu",
               "github": "owner/repo", "huggingface": "org/model", "youtube": "labubu", "spotify_artist": "id"}],
 "controls": [{"name": "Coffee", "wikipedia": "Coffee", "hackernews": "coffee", "bluesky": "coffee"}],
 "rule": {"baseline_weeks": 52, "threshold_mads": 3, "consecutive": 2,
          "min_volume": {"wikipedia": 500, "hackernews": 3, "bluesky": 50, "youtube": 20}}}

Backfilled (history today): wikipedia, hackernews, bluesky, github. Snapshots (history accrues from the first run):
huggingface, apple_music, kworb_us, spotify_artist. Keyed: youtube (scout-youtube), spotify_artist
(scout-spotify-id, scout-spotify-secret), github token optional (scout-github). Keys come from SCOUT_* env vars or
the macOS keychain and are never written anywhere. Every fetch records ok, failed or skipped; nothing is zero-filled.
"""
import base64, collections, datetime, json, math, os, re, statistics, subprocess, sys, time, urllib.error, urllib.parse, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pageviews  # noqa: E402

UA = "TheScout-signals/1.0 (trend research; read-only)"
BACKFILLED = ["wikipedia", "hackernews", "bluesky", "github", "youtube", "chartmetric"]
SNAPSHOT = ["huggingface", "apple_music", "kworb_us", "spotify_artist"]
DEFAULT_MIN = {"wikipedia": 500, "hackernews": 3, "bluesky": 50, "github": 100, "youtube": 20}


def key(name):
    env = os.environ.get("SCOUT_" + name.upper().replace("-", "_"))
    if env:
        return env
    try:
        out = subprocess.run(["security", "find-generic-password", "-s", f"scout-{name}", "-w"],
                             capture_output=True, text=True, timeout=10)
        return out.stdout.strip() or None
    except Exception:
        return None


def get_json(url, headers=None, retries=3):
    wait = 5
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=dict({"User-Agent": UA}, **(headers or {})))
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r), dict(r.headers)
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and attempt < retries:
                time.sleep(float(e.headers.get("Retry-After") or wait))
                wait *= 2
                continue
            raise


def mondays(start, end):
    d = start - datetime.timedelta(days=start.weekday())
    while d <= end:
        yield d
        d += datetime.timedelta(days=7)


def to_weekly(daily):
    w = collections.Counter()
    for d, v in daily.items():
        dt = datetime.date.fromisoformat(d) if "-" in d else datetime.date(int(d[:4]), int(d[4:6]), int(d[6:8]))
        w[(dt - datetime.timedelta(days=dt.weekday())).isoformat()] += v
    return dict(w)


# ---------- backfilled sources: return {"weekly": {...}} ----------

def f_wikipedia(q, start, end):
    s, err = pageviews.fetch(q, start.strftime("%Y%m%d"), end.strftime("%Y%m%d"), pause=1.0)
    if s is None:
        raise RuntimeError(err)
    return {"weekly": to_weekly(s), "first_day": min(s) if s else None}


def hn_query(q):
    """Exact matching: Algolia's typo tolerance turns "openclaw" into OpenCL and OpenLaw."""
    return f'"{q}"' if " " in q and not q.startswith('"') else q


def f_hackernews(q, start, end):
    weekly = {}
    for m in mondays(start, end):
        a = int(datetime.datetime(m.year, m.month, m.day, tzinfo=datetime.timezone.utc).timestamp())
        b = a + 7 * 86400
        url = ("https://hn.algolia.com/api/v1/search_by_date?" +
               urllib.parse.urlencode({"query": hn_query(q), "tags": "story", "hitsPerPage": 0, "typoTolerance": "false",
                                       "numericFilters": f"created_at_i>={a},created_at_i<{b}"}))
        d, _ = get_json(url)
        weekly[m.isoformat()] = d.get("nbHits", 0)
        time.sleep(0.15)
    return {"weekly": weekly}


def f_bluesky(q, start, end):
    weekly = {}
    first = max(start, datetime.date(2023, 2, 20))  # public posting history begins early 2023
    for m in mondays(first, end):
        a, b = m, m + datetime.timedelta(days=7)
        url = ("https://api.bsky.app/xrpc/app.bsky.feed.searchPosts?" +
               urllib.parse.urlencode({"q": q, "since": f"{a}T00:00:00Z", "until": f"{b}T00:00:00Z", "limit": 1}))
        d, _ = get_json(url)
        weekly[m.isoformat()] = d.get("hitsTotal", len(d.get("posts", [])))
        time.sleep(0.12)
    return {"weekly": weekly, "note": "hitsTotal from Bluesky search; history before early 2023 does not exist. "
                                      f"Search counts stop at {BLUESKY_CAP:,} a week, so a week at that number is a floor, not a count."}


BLUESKY_CAP = 10000  # Bluesky search reports at most this many hits per query; weeks at the cap can't be compared


def capped_weeks(src, weekly):
    """Weeks whose count hit a source's reporting ceiling (Bluesky search stops at 10,000)."""
    if src != "bluesky" or not weekly:
        return []
    return sorted(w for w, v in weekly.items() if v >= BLUESKY_CAP)


def f_github(repo, start, end):
    tok = key("github")
    hdr = {"Accept": "application/vnd.github.star+json"}
    if tok:
        hdr["Authorization"] = f"Bearer {tok}"
    daily, page, capped = collections.Counter(), 1, False
    while True:
        try:
            d, h = get_json(f"https://api.github.com/repos/{repo}/stargazers?per_page=100&page={page}", hdr, retries=1)
        except urllib.error.HTTPError as e:
            if e.code == 422:  # GitHub stops listing stargazers after 400 pages
                capped = True
                break
            raise
        if not d:
            break
        for s in d:
            daily[s["starred_at"][:10]] += 1
        if len(d) < 100:
            break
        page += 1
        if int(h.get("X-RateLimit-Remaining", h.get("x-ratelimit-remaining", "1"))) <= 1:
            capped = True
            break
        time.sleep(0.2)
    return {"weekly": to_weekly(daily), "capped": capped, "authenticated": bool(tok),
            "note": "New stars per week. Capped means GitHub's listing or rate limit stopped the pull early."}


def f_youtube(q, start, end):
    k = key("youtube")
    if not k:
        return {"skipped": "no key: add scout-youtube to the keychain or SCOUT_YOUTUBE to the environment"}
    weekly = {}
    first = max(start, end - datetime.timedelta(weeks=26))  # 100 quota units per call; last 26 weeks only
    for m in mondays(first, end):
        url = ("https://www.googleapis.com/youtube/v3/search?" +
               urllib.parse.urlencode({"part": "id", "q": q, "type": "video", "maxResults": 1, "key": k,
                                       "publishedAfter": f"{m}T00:00:00Z",
                                       "publishedBefore": f"{m + datetime.timedelta(days=7)}T00:00:00Z"}))
        d, _ = get_json(url)
        weekly[m.isoformat()] = (d.get("pageInfo") or {}).get("totalResults", 0)
    return {"weekly": weekly, "note": "YouTube totalResults is an estimate; last 26 weeks only to protect quota."}


CM = {"token": None, "at": 0}
CM_METRICS = {"spotify_listeners": ("spotify", "listeners"), "spotify_followers": ("spotify", "followers"),
              "spotify_popularity": ("spotify", "popularity"), "tiktok_followers": ("tiktok", "followers"),
              "youtube_subscribers": ("youtube_channel", "subscribers"), "instagram_followers": ("instagram", "followers")}


def cm_get(path, params=None):
    """Chartmetric with a refresh token from the keychain (scout-chartmetric). Access tokens last about an hour."""
    if not CM["token"] or time.time() - CM["at"] > 3000:
        rt = key("chartmetric")
        if not rt:
            return None
        req = urllib.request.Request("https://api.chartmetric.com/api/token", data=json.dumps({"refreshtoken": rt}).encode(),
                                     headers={"Content-Type": "application/json", "User-Agent": UA})
        with urllib.request.urlopen(req, timeout=30) as r:
            CM.update(token=json.load(r)["token"], at=time.time())
    d, _ = get_json(f"https://api.chartmetric.com/api/{path}" + ("?" + urllib.parse.urlencode(params) if params else ""),
                    {"Authorization": f"Bearer {CM['token']}"})
    time.sleep(1.1)  # stay inside the per-second limit
    return d


def f_chartmetric(q, start, end):
    """Streaming and social history for an artist. q = "Artist name" or "Chartmetric id", optionally ":metric"
    (spotify_listeners by default; also spotify_followers, spotify_popularity, tiktok_followers, youtube_subscribers, instagram_followers).
    Levels, not counts: each week holds the mean of that week's daily values."""
    if not key("chartmetric"):
        return {"skipped": "no key: add your Chartmetric API refresh token as scout-chartmetric in the keychain"}
    name, metric = (q.rsplit(":", 1) if ":" in q and q.rsplit(":", 1)[1] in CM_METRICS else (q, "spotify_listeners"))
    if name.isdigit():
        cid = int(name)
    else:
        found = ((cm_get("search", {"q": name, "type": "artists", "limit": 1}) or {}).get("obj") or {}).get("artists") or []
        if not found:
            return {"skipped": f"Chartmetric has no artist match for {name!r}"}
        cid = found[0]["id"]
    source, field = CM_METRICS[metric]
    d = cm_get(f"artist/{cid}/stat/{source}", {"since": start.isoformat(), "until": end.isoformat(), "field": field}) or {}
    series = (d.get("obj") or {}).get(field) or []
    weeks = collections.defaultdict(list)
    for pt in series:
        day = datetime.date.fromisoformat(str(pt.get("timestp"))[:10])
        if pt.get("value") is not None:
            weeks[(day - datetime.timedelta(days=day.weekday())).isoformat()].append(float(pt["value"]))
    weekly = {w: round(sum(v) / len(v)) for w, v in sorted(weeks.items())}
    return {"weekly": weekly, "kind": "level", "chartmetric_id": cid, "metric": metric,
            "note": f"Chartmetric {source} {field}, weekly mean of daily values"}


# ---------- snapshot sources: return {"snapshot": {...}} ----------

def f_huggingface(model, start, end):
    d, _ = get_json(f"https://huggingface.co/api/models/{model}")
    return {"snapshot": {"downloads_30d": d.get("downloads"), "likes": d.get("likes")}}


def f_apple_music(q, start, end):
    d, _ = get_json("https://rss.marketingtools.apple.com/api/v2/us/music/most-played/100/songs.json")
    hits = [{"rank": i + 1, "name": r["name"], "artist": r["artistName"]} for i, r in enumerate(d["feed"]["results"])
            if q.lower() in (r["name"] + " " + r["artistName"]).lower()]
    return {"snapshot": {"chart_updated": d["feed"]["updated"], "matches": hits, "best_rank": min([h["rank"] for h in hits], default=None)}}


def f_kworb_us(q, start, end):
    req = urllib.request.Request("https://kworb.net/spotify/country/us_daily.html", headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        body = r.read().decode("utf-8", "replace")
    rows = []
    for tr in re.findall(r"<tr>(.*?)</tr>", body, re.S)[1:]:
        cells = [re.sub(r"<[^>]+>", "", c).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
        if len(cells) > 6 and q.lower() in cells[2].lower():
            rows.append({"rank": int(cells[0]), "track": cells[2], "days": cells[3], "streams": cells[6]})
    return {"snapshot": {"chart": "Spotify US daily via kworb.net", "matches": rows,
                         "best_rank": min([x["rank"] for x in rows], default=None)}}


def f_spotify_artist(artist_id, start, end):
    cid, sec = key("spotify-id"), key("spotify-secret")
    if not (cid and sec):
        return {"skipped": "no key: add scout-spotify-id and scout-spotify-secret to the keychain"}
    tok_req = urllib.request.Request("https://accounts.spotify.com/api/token", data=b"grant_type=client_credentials",
                                     headers={"Authorization": "Basic " + base64.b64encode(f"{cid}:{sec}".encode()).decode(),
                                              "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(tok_req, timeout=30) as r:
        tok = json.load(r)["access_token"]
    d, _ = get_json(f"https://api.spotify.com/v1/artists/{artist_id}", {"Authorization": f"Bearer {tok}"})
    return {"snapshot": {"followers": (d.get("followers") or {}).get("total"), "popularity": d.get("popularity"), "name": d.get("name")}}


FETCH = {"wikipedia": f_wikipedia, "hackernews": f_hackernews, "bluesky": f_bluesky, "github": f_github,
         "youtube": f_youtube, "huggingface": f_huggingface, "apple_music": f_apple_music, "kworb_us": f_kworb_us,
         "spotify_artist": f_spotify_artist, "chartmetric": f_chartmetric}


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60]


LIMITS = {"hackernews": 4, "bluesky": 3, "wikipedia": 2, "github": 1, "youtube": 1, "chartmetric": 1}


def pull(basket, out_dir, refresh=False, workers=8):
    """Fetch every (entity, source) pair in parallel, with a per-source limit so no API is hammered."""
    import threading
    from concurrent.futures import ThreadPoolExecutor
    start = datetime.date.fromisoformat(basket.get("start", "2023-01-02"))
    end = datetime.date.fromisoformat(basket.get("end") or (datetime.date.today() - datetime.timedelta(days=1)).isoformat())
    today = datetime.date.today().isoformat()
    gates = {src: threading.Semaphore(LIMITS.get(src, 2)) for src in FETCH}
    tasks = []
    for group in ("entities", "controls"):
        for ent in basket.get(group, []):
            for src, fn in FETCH.items():
                q = ent.get(src)
                if not q:
                    continue
                name = f"{slug(ent['name'])}-{today}.json" if src in SNAPSHOT else f"{slug(ent['name'])}.json"
                tasks.append((group, ent, src, fn, q, os.path.join(out_dir, "raw", src, name)))

    def one(t):
        group, ent, src, fn, q, path = t
        rec = {"group": group, "entity": ent["name"], "source": src, "query": q, "file": path}
        old, since = None, start
        if os.path.exists(path) and not refresh:
            try:
                old = json.load(open(path))
            except Exception:
                old = None
            fetched = (old or {}).get("fetched_at", "")[:10]
            fresh = fetched and (datetime.date.today() - datetime.date.fromisoformat(fetched)).days < 6
            if fresh or src not in BACKFILLED or not (old or {}).get("weekly"):
                rec["outcome"] = "cached"
                return rec
            # a week or more old: fetch only the recent weeks (the last three again, in case they were partial) and merge
            since = max(start, datetime.date.fromisoformat(max(old["weekly"])) - datetime.timedelta(days=21))
        with gates[src]:
            try:
                qs = q if isinstance(q, list) else [q]  # aliases are summed, e.g. a product renamed twice
                parts = [fn(x, since, end) for x in qs]
                data = parts[0]
                if len(parts) > 1 and all("weekly" in p for p in parts):
                    merged = {}
                    for p in parts:
                        for w, v in p["weekly"].items():
                            merged[w] = merged.get(w, 0) + v
                    data = dict(parts[0], weekly=merged, aliases=qs)
                if old and "weekly" in data:  # weekly refresh: keep the saved history, replace the recent weeks
                    data = dict(data, weekly=dict(old["weekly"], **data["weekly"]))
                    rec["refreshed_from"] = since.isoformat()
                rec["outcome"] = "skipped" if "skipped" in data else ("updated" if old else "ok")
                if "skipped" in data:
                    rec["reason"] = data["skipped"]
                else:
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                    json.dump(dict(data, fetched_at=datetime.datetime.now(datetime.timezone.utc).isoformat(), query=q), open(path, "w"))
            except Exception as e:  # recorded per entity, never zero-filled
                rec["outcome"] = "failed"
                rec["error"] = str(e)[:200]
        print(f"{group[:3]} {ent['name'][:28]:<28} {src:<14} {rec['outcome']}", flush=True)
        return rec

    with ThreadPoolExecutor(max_workers=workers) as ex:
        receipts = list(ex.map(one, tasks))
    json.dump({"pulled_at": datetime.datetime.now(datetime.timezone.utc).isoformat(), "window": [str(start), str(end)],
               "items": receipts}, open(os.path.join(out_dir, "signals-receipt.json"), "w"), indent=1)
    return receipts


def load_weekly(out_dir, src, ent):
    path = os.path.join(out_dir, "raw", src, f"{slug(ent['name'])}.json")
    if not os.path.exists(path):
        return None
    return json.load(open(path)).get("weekly")


def durability(r, i, base_n, k):
    """Median ratio 8 to 12 weeks after week i against the baseline before it."""
    if i + 12 >= len(r):
        return "too_recent"
    base = [x[1] for x in r[max(0, i - base_n):i]]
    med = statistics.median(base)
    mad = statistics.median([abs(b - med) for b in base]) * 1.4826 or 1e-9
    later = statistics.median([x[1] for x in r[i + 8:i + 13]])
    return "sustained" if later > med + mad else "faded"


def analyze(basket, out_dir, as_of=None):
    rule = dict({"baseline_weeks": 52, "threshold_mads": 3, "consecutive": 2}, **basket.get("rule", {}))
    mins = dict(DEFAULT_MIN, **(rule.get("min_volume") or {}))
    end = datetime.date.fromisoformat(as_of or basket.get("end") or datetime.date.today().isoformat())
    result = {"watch_id": basket.get("watch_id"), "rule": rule, "min_volume": mins, "sources": {}}
    for src in BACKFILLED:
        watch = {e["name"]: load_weekly(out_dir, src, e) for e in basket.get("entities", []) if e.get(src)}
        ctrl = {e["name"]: load_weekly(out_dir, src, e) for e in basket.get("controls", []) if e.get(src)}
        watch = {k: v for k, v in watch.items() if v}
        ctrl = {k: v for k, v in ctrl.items() if v}
        if not watch:
            continue
        all_weeks = sorted(set().union(*[set(v) for v in list(watch.values()) + list(ctrl.values())]))
        weeks = [w for w in all_weeks if datetime.date.fromisoformat(w) + datetime.timedelta(days=7) <= end]
        per_entity = {}
        for name, series in watch.items():
            den = collections.Counter()
            for v in ctrl.values():
                den.update(v)
            if not ctrl:  # no controls: compare against the entity's own history
                den = collections.Counter({w: 0 for w in weeks})
            num = collections.Counter(series)
            f = pageviews.flags(num, den, weeks, mins.get(src, 0), rule["baseline_weeks"], rule["threshold_mads"], rule["consecutive"])
            r = [(wk, math.log((num.get(wk, 0) + 1) / (den.get(wk, 0) + 1)), num.get(wk, 0)) for wk in weeks]
            flagged = [w for w, h in f if h]
            first = flagged[0] if flagged else None
            known = (datetime.date.fromisoformat(first) + datetime.timedelta(days=7)).isoformat() if first else None
            dur = durability(r, weeks.index(first), rule["baseline_weeks"], rule["threshold_mads"]) if first else None
            per_entity[name] = {"first_flag_week": first, "flag_known_at": known, "durability": dur,
                                "flagged_weeks": flagged[-12:], "weeks": len(weeks),
                                "first_nonzero_week": next((w for w in weeks if num.get(w, 0) > 0), None),
                                "peak_week": max(weeks, key=lambda w: num.get(w, 0)) if weeks else None,
                                "peak_value": max([num.get(w, 0) for w in weeks] or [0]),
                                "last8": {w: num.get(w, 0) for w in weeks[-8:]},
                                "tail52": [num.get(w, 0) for w in weeks[-52:]], "tail52_start": weeks[-52] if len(weeks) >= 52 else (weeks[0] if weeks else None),
                                "flagged_recent": bool(flagged and flagged[-1] >= (weeks[-8] if len(weeks) >= 8 else weeks[0]))}
        fa = {}
        for t, series in ctrl.items():
            den = collections.Counter()
            for o, v in ctrl.items():
                if o != t:
                    den.update(v)
            f = pageviews.flags(collections.Counter(series), den, weeks, mins.get(src, 0), rule["baseline_weeks"],
                                rule["threshold_mads"], rule["consecutive"])
            n = sum(1 for _, h in f if h)
            fa[t] = {"weeks_tested": len(f), "flagged": n}
        tested = sum(v["weeks_tested"] for v in fa.values())
        result["sources"][src] = {"entities": per_entity, "control_false_alarm": fa,
                                  "control_false_alarm_pooled": round(sum(v["flagged"] for v in fa.values()) / tested, 4) if tested else None,
                                  "controls_used": sorted(ctrl), "last_closed_week": weeks[-1] if weeks else None}
    snaps = {}
    for src in SNAPSHOT:
        d = os.path.join(out_dir, "raw", src)
        if os.path.isdir(d):
            snaps[src] = sorted(os.listdir(d))
    result["snapshots"] = snaps
    json.dump(result, open(os.path.join(out_dir, "signals-analysis.json"), "w"), indent=1)
    return result


def check(basket, fix=False):
    """Confirm every Wikipedia title exists; suggest the closest real article when it doesn't."""
    report = []
    for group in ("entities", "controls"):
        for ent in basket.get(group, []):
            t = ent.get("wikipedia")
            if not t:
                continue
            try:
                d, _ = get_json("https://en.wikipedia.org/api/rest_v1/page/summary/" + urllib.parse.quote(t.replace(" ", "_"), safe=""))
                report.append({"name": ent["name"], "title": t, "ok": d.get("type") == "standard", "description": d.get("description")})
                continue
            except urllib.error.HTTPError:
                pass
            d, _ = get_json("https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode(
                {"action": "opensearch", "search": ent["name"], "limit": 5, "namespace": 0, "format": "json"}))
            sugg = d[1] if len(d) > 1 else []
            report.append({"name": ent["name"], "title": t, "ok": False, "suggestions": sugg})
            if fix and sugg:
                ent["wikipedia"] = sugg[0]
    return report


if __name__ == "__main__":
    mode, bpath = sys.argv[1], sys.argv[2]
    b = json.load(open(bpath))
    if mode == "check":
        rep = check(b, fix="--fix" in sys.argv)
        for r in rep:
            print(("ok   " if r["ok"] else "MISS ") + f"{r['name']:<28} {r['title']:<36} " + (r.get("description") or ", ".join(r.get("suggestions", []))))
        if "--fix" in sys.argv:
            json.dump(b, open(bpath, "w"), indent=1)
            print("wrote the first suggestion into the basket for each miss; check them")
        sys.exit(0)
    out = sys.argv[3]
    os.makedirs(out, exist_ok=True)
    if mode == "pull":
        pull(b, out, "--refresh" in sys.argv)
    elif mode == "analyze":
        res = analyze(b, out)
        for src, s in res["sources"].items():
            print(f"{src}: control false alarm {s['control_false_alarm_pooled']}")
            for n, e in s["entities"].items():
                print(f"   {n:<28} first flag {e['first_flag_week']}  known {e['flag_known_at']}  {e['durability']}")
    else:
        sys.exit("mode must be pull or analyze")
