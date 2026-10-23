"""Backfilled Wikipedia attention for one watch, with a control basket and a pre-registered detection rule.

Usage:
  python3 pageviews.py pull BASKET.json OUT_DIR        live pull (read-only), writes pageviews_raw.json + receipt.json
  python3 pageviews.py analyze BASKET.json OUT_DIR      analysis from OUT_DIR/pageviews_raw.json, writes analysis.json

BASKET.json: {"watch_id", "watch": [titles], "control": [titles], "start": "YYYYMMDD", "end": "YYYYMMDD",
              "min_volume": 500, "baseline_weeks": 52, "threshold_mads": 3, "consecutive": 2, "notes": "..."}
"""
import collections, datetime, json, math, os, statistics, sys, time, urllib.error, urllib.parse, urllib.request

UA = {"User-Agent": "TheScout-backfill/1.0 (trend research; read-only; contact via repository owner)"}
API = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/{t}/daily/{s}00/{e}00"


def fetch(title, start, end, retries=4, pause=1.5):
    url = API.format(t=urllib.parse.quote(title.replace(" ", "_"), safe=""), s=start, e=end)
    wait = 5
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                items = json.load(r)["items"]
            time.sleep(pause)
            return {i["timestamp"][:8]: i["views"] for i in items}, None
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < retries:
                time.sleep(float(e.headers.get("Retry-After") or wait))
                wait *= 2
                continue
            return None, f"HTTP {e.code}"
        except Exception as e:  # network errors are recorded, never zero-filled
            return None, str(e)[:200]
    return None, "retries exhausted"


def pull(basket, out_dir):
    raw, results = {}, {}
    end = basket.get("end") or (datetime.date.today() - datetime.timedelta(days=1)).strftime("%Y%m%d")
    for t in basket["watch"] + basket["control"]:
        series, err = fetch(t, basket.get("start", "20150701"), end)
        if series is None:
            results[t] = {"ok": False, "error": err}
        else:
            raw[t] = series
            days = sorted(series)
            results[t] = {"ok": True, "days": len(days), "first": days[0], "last": days[-1], "total": sum(series.values())}
    receipt = {"pulled_at": datetime.datetime.now(datetime.timezone.utc).isoformat(), "watch_id": basket.get("watch_id"),
               "range": [basket.get("start", "20150701"), end], "agent": "user", "access": "all-access",
               "project": "en.wikipedia", "results": results}
    os.makedirs(out_dir, exist_ok=True)
    json.dump(raw, open(os.path.join(out_dir, "pageviews_raw.json"), "w"))
    json.dump(receipt, open(os.path.join(out_dir, "receipt.json"), "w"), indent=1)
    return receipt


def weekly(series):
    w = collections.Counter()
    for d, v in series.items():
        dt = datetime.date(int(d[:4]), int(d[4:6]), int(d[6:8]))
        w[(dt - datetime.timedelta(days=dt.weekday())).isoformat()] += v
    return w


def monthly(series):
    m = collections.Counter()
    for d, v in series.items():
        m[f"{d[:4]}-{d[4:6]}"] += v
    return dict(sorted(m.items()))


def flags(num, den, weeks, minvol, base_n, k, consec):
    r = [(wk, math.log((num.get(wk, 0) + 1) / (den.get(wk, 0) + 1)), num.get(wk, 0)) for wk in weeks]
    out, run = [], 0
    for i in range(base_n, len(r)):
        base = [x[1] for x in r[i - base_n:i]]
        med = statistics.median(base)
        mad = statistics.median([abs(b - med) for b in base]) * 1.4826 or 1e-9
        hit = r[i][1] > med + k * mad and r[i][2] >= minvol
        run = run + 1 if hit else 0
        out.append((r[i][0], run >= consec))
    return out


def analyze(basket, out_dir):
    raw = json.load(open(os.path.join(out_dir, "pageviews_raw.json")))
    W = {t: weekly(s) for t, s in raw.items()}
    weeks = sorted(set().union(*[set(w) for w in W.values()]))[:-1]  # last week is open or partial
    minvol, base_n = basket.get("min_volume", 500), basket.get("baseline_weeks", 52)
    k, consec = basket.get("threshold_mads", 3), basket.get("consecutive", 2)
    ctrl = [t for t in basket["control"] if t in raw]
    watch = [t for t in basket["watch"] if t in raw]
    fa = {}
    for t in ctrl:
        den = collections.Counter()
        for o in ctrl:
            if o != t:
                den.update(W[o])
        f = flags(W[t], den, weeks, minvol, base_n, k, consec)
        n = sum(1 for _, h in f if h)
        fa[t] = {"weeks_tested": len(f), "flagged": n, "rate": round(n / len(f), 4) if f else None}
    tested = sum(v["weeks_tested"] for v in fa.values())
    pooled = round(sum(v["flagged"] for v in fa.values()) / tested, 4) if tested else None
    den, num = collections.Counter(), collections.Counter()
    for o in ctrl:
        den.update(W[o])
    for t in watch:
        num.update(W[t])
    wf = flags(num, den, weeks, minvol, base_n, k, consec)
    starts = {t: min(raw[t]) for t in watch}
    analysis = {
        "watch_id": basket.get("watch_id"),
        "rule": {"ratio": "log((watch+1)/(control+1))", "baseline_weeks": base_n, "threshold_mads": k,
                 "consecutive": consec, "min_volume": minvol, "weeks": "Monday start, open week dropped"},
        "missing_articles": [t for t in basket["watch"] + basket["control"] if t not in raw],
        "control_false_alarm": fa,
        "control_false_alarm_pooled": pooled,
        "watch_flagged_weeks": [w for w, h in wf if h],
        "watch_last8": {wk: num.get(wk, 0) for wk in weeks[-8:]},
        "watch_same_weeks_last_year": {wk: num.get(wk, 0) for wk in weeks[-60:-52]},
        "composition_warning": {t: d for t, d in starts.items() if d > basket.get("start", "20150701")},
        "monthly": {t: monthly(raw[t]) for t in watch},
        "last_closed_week": weeks[-1] if weeks else None,
    }
    json.dump(analysis, open(os.path.join(out_dir, "analysis.json"), "w"), indent=1)
    return analysis


if __name__ == "__main__":
    mode, basket_path, out = sys.argv[1], sys.argv[2], sys.argv[3]
    basket = json.load(open(basket_path))
    if mode == "pull":
        rec = pull(basket, out)
        bad = [t for t, r in rec["results"].items() if not r["ok"]]
        print(f"pulled {len(rec['results']) - len(bad)} of {len(rec['results'])}; failed: {bad or 'none'}")
    elif mode == "analyze":
        a = analyze(basket, out)
        print(f"pooled control false alarm {a['control_false_alarm_pooled']}; flagged weeks {a['watch_flagged_weeks'][-6:]}")
    else:
        sys.exit("mode must be pull or analyze")
