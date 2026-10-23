"""Backtest: would the Scout's rule have flagged past breakouts before the benchmark press named them?

Usage: python3 backtest.py CASES.json OUTLETS.json OUT_DIR [--skip-pull] [--skip-benchmark]
CASES.json: {"start": "2023-01-02", "end": "2026-10-19", "controls": [{entity}], "rule": {...},
             "cases": [{"id", "name", "lane", "kind": "breakout"|"fade", "entity": {signals entity},
                        "benchmark": {"window_start", "window_end", "slug_patterns": [...]}}]}
Cases and the outlet set are fixed before the run. Results are reported as they come out, misses included.
"""
import datetime, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import benchmark, signals  # noqa: E402


def main():
    cases_path, outlets_path, out = sys.argv[1], sys.argv[2], sys.argv[3]
    spec = json.load(open(cases_path))
    outlets = json.load(open(outlets_path))
    os.makedirs(out, exist_ok=True)
    basket = {"watch_id": "backtest", "start": spec["start"], "end": spec["end"], "rule": spec.get("rule", {}),
              "entities": [c["entity"] for c in spec["cases"]], "controls": spec["controls"]}
    json.dump(basket, open(os.path.join(out, "basket.json"), "w"), indent=1)
    if "--skip-pull" not in sys.argv:
        signals.pull(basket, out)
    analysis = signals.analyze(basket, out)
    bdir = os.path.join(out, "benchmark")
    os.makedirs(bdir, exist_ok=True)
    rows = []
    for c in spec["cases"]:
        bpath = os.path.join(bdir, f"{c['id']}.json")
        if "--skip-benchmark" not in sys.argv or not os.path.exists(bpath):
            q = dict(c["benchmark"], row=c["id"], earliest_only=True)
            json.dump(benchmark.run(outlets, q), open(bpath, "w"), indent=1)
        bres = json.load(open(bpath))
        hits = []
        for o in bres["outlets"]:
            for cand in o["candidates"]:
                if cand.get("published"):
                    hits.append({"outlet": o["name"], "url": cand["url"], "published": cand["published"][:10],
                                 "title": cand.get("title"), "date_source": cand.get("date_source")})
        hits.sort(key=lambda h: h["published"])
        first = hits[0] if hits else None
        cov = {o["name"]: o["coverage"] for o in bres["outlets"]}
        per_source = {}
        for src, s in analysis["sources"].items():
            e = s["entities"].get(c["entity"]["name"])
            if not e:
                continue
            lead = None
            if first and e["flag_known_at"]:
                lead = (datetime.date.fromisoformat(first["published"]) - datetime.date.fromisoformat(e["flag_known_at"])).days
            per_source[src] = {"flag_known_at": e["flag_known_at"], "lead_days_vs_press": lead, "durability": e["durability"],
                               "first_nonzero_week": e["first_nonzero_week"], "peak_week": e["peak_week"],
                               "control_false_alarm": s["control_false_alarm_pooled"]}
        known = [v["flag_known_at"] for v in per_source.values() if v["flag_known_at"]]
        earliest_flag = min(known) if known else None
        combined = ((datetime.date.fromisoformat(first["published"]) - datetime.date.fromisoformat(earliest_flag)).days
                    if first and earliest_flag else None)
        rows.append({"id": c["id"], "name": c["name"], "lane": c["lane"], "kind": c["kind"],
                     "first_benchmark": first, "benchmark_coverage": cov, "benchmark_matches": len(hits),
                     "earliest_flag_known_at": earliest_flag, "lead_days_vs_press": combined, "per_source": per_source})
    report = {"generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(), "rule": analysis["rule"],
              "min_volume": analysis["min_volume"], "outlets": [o["name"] for o in outlets], "cases": rows,
              "note": "Lead is first benchmark headline naming the entity minus the day the first flag was knowable "
                      "(end of the second consecutive flagged week). Positive means the rule was earlier than the press."}
    json.dump(report, open(os.path.join(out, "backtest.json"), "w"), indent=1)
    for r in rows:
        fb = r["first_benchmark"]
        print(f"{r['name']:<24} {r['kind']:<8} press {fb['published'] if fb else 'none':<10} ({fb['outlet'] if fb else '-'})  "
              f"flag {r['earliest_flag_known_at'] or 'none':<10}  lead {r['lead_days_vs_press']}")
        for src, v in r["per_source"].items():
            print(f"      {src:<11} known {v['flag_known_at'] or 'none':<10} lead {v['lead_days_vs_press']}  {v['durability'] or ''}")


if __name__ == "__main__":
    main()
