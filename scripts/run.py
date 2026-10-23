"""One command for the whole check: audit, backfill, capture, copy check, render.

Usage:
  python3 run.py --run-dir RUN_DIR --out OUT_DIR [--ledger LEDGER.jsonl] [--basket BASKET.json [--pull]]
                 [--manifest MANIFEST.json] [--slides SLIDES.json] [--mean 3]

Every step writes its own receipt under OUT_DIR. Audits are kept in OUT_DIR/history/ and compared with the last one.
Reads the journal only. Never posts, schedules, signs in or pushes.
"""
import argparse, datetime, glob, json, os, shutil, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import audit as audit_mod, capture, pageviews, signals as signals_mod  # noqa: E402


def defaults_from(config_path):
    """local.json holds machine paths (relative ones resolve against the folder that holds the brain or kit)."""
    if not config_path or not os.path.exists(config_path):
        return {}
    cfg = json.load(open(config_path))
    root = os.path.expanduser(cfg.get("root", os.path.dirname(os.path.abspath(config_path))))
    out = {}
    for k in ("run_dir", "out", "ledger", "basket", "signals", "manifest", "slides", "weekly_out", "weekly_slides", "calls", "outlets",
              "registry", "backtest"):
        if cfg.get(k):
            v = os.path.expanduser(cfg[k].replace("{date}", datetime.date.today().isoformat()))
            out[k] = v if os.path.isabs(v) else os.path.join(root, v)
    return out


def main():
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--config", default=os.path.join(os.path.dirname(HERE), "local.json"))
    known, _ = pre.parse_known_args()
    d = defaults_from(known.config)
    ap = argparse.ArgumentParser(parents=[pre])
    ap.add_argument("--run-dir", default=d.get("run_dir"), help="Scout journal folder; optional for a brand-new niche")
    ap.add_argument("--out", default=d.get("out"), required="out" not in d)
    ap.add_argument("--ledger", default=d.get("ledger"))
    ap.add_argument("--basket", default=d.get("basket"))
    ap.add_argument("--pull", action="store_true", help="pull fresh pageviews; otherwise analyse OUT/backfill/pageviews_raw.json")
    ap.add_argument("--manifest", default=d.get("manifest"))
    ap.add_argument("--slides", default=d.get("slides"))
    ap.add_argument("--mean", type=float)
    ap.add_argument("--signals", default=d.get("signals"), help="multi-source signals basket (signals.py format)")
    ap.add_argument("--calls", default=d.get("calls"))
    ap.add_argument("--outlets", default=d.get("outlets"))
    ap.add_argument("--discover", action="store_true")
    ap.add_argument("--media", action="store_true")
    ap.add_argument("--weekly", action="store_true", help="Monday run: weekly_out, weekly_slides, pull, calls, discover, media")
    a = ap.parse_args()
    if a.weekly:
        a.out = d.get("weekly_out", a.out)
        a.slides = d.get("weekly_slides", a.slides)
        a.pull = a.discover = a.media = True
    os.makedirs(a.out, exist_ok=True)
    summary = {"started_at": datetime.datetime.now(datetime.timezone.utc).isoformat(), "steps": {}}

    # 1. Audit, history and changes since the last audit
    result = audit_mod.audit(a.run_dir, a.ledger, a.mean)
    ap_path = os.path.join(a.out, "audit.json")
    json.dump(result, open(ap_path, "w"), indent=1)
    hist = os.path.join(a.out, "history")
    os.makedirs(hist, exist_ok=True)
    previous = sorted(glob.glob(os.path.join(hist, "*-audit.json")))
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    shutil.copyfile(ap_path, os.path.join(hist, f"{stamp}-audit.json"))
    changes = audit_mod.compare(json.load(open(previous[-1])), result) if previous else None
    F = result["figures"]
    summary["steps"]["audit"] = {"file": ap_path, "verdict": result["verdict"], "gate": result["radar_gate"]["reason"],
                                 "changes_since_last": changes, "previous": previous[-1] if previous else None}
    print(f"audit: {F['records']['value']} records, {F['accepted']['value']} accepted, {F['held']['value']} held, "
          f"{F['completed_windows']['value']} completed windows. Verdict: {result['verdict']}.")
    print(f"gate: {result['radar_gate']['reason']}")
    if changes is None:
        print("changes: first audit in this folder")
    elif not changes:
        print("changes: none since the last audit")
    else:
        for c in changes:
            print(f"changes: {c['figure']} {c['before']} -> {c['after']}")

    # 2. Backfilled metric
    extra = []
    if a.basket:
        basket = json.load(open(a.basket))
        bdir = os.path.join(a.out, "backfill", basket.get("watch_id", "watch"))
        if a.pull:
            rec = pageviews.pull(basket, bdir)
            failed = [t for t, r in rec["results"].items() if not r["ok"]]
            print(f"backfill pull: {len(rec['results']) - len(failed)} of {len(rec['results'])} articles; failed {failed or 'none'}")
        if os.path.exists(os.path.join(bdir, "pageviews_raw.json")):
            an = pageviews.analyze(basket, bdir)
            extra.append(f"backfill={os.path.join(bdir, 'analysis.json')}")
            summary["steps"]["backfill"] = {"dir": bdir, "pooled_control_false_alarm": an["control_false_alarm_pooled"],
                                            "flagged_weeks": an["watch_flagged_weeks"][-6:], "missing": an["missing_articles"]}
            print(f"backfill: control false alarm {an['control_false_alarm_pooled']}; recent flagged weeks {an['watch_flagged_weeks'][-3:] or 'none'}")
        else:
            summary["steps"]["backfill"] = {"dir": bdir, "outcome": "no raw pull yet; run with --pull"}
            print("backfill: no raw pull yet; run with --pull")

    # 2b. Multi-source signals for any niche (keyless by default)
    if a.signals:
        sb = json.load(open(a.signals))
        sdir = os.path.join(a.out, "signals")
        if a.pull:
            signals_mod.pull(sb, sdir)
        if os.path.isdir(os.path.join(sdir, "raw")):
            res = signals_mod.analyze(sb, sdir)
            extra.append(f"signals={os.path.join(sdir, 'signals-analysis.json')}")
            flagged = {src: [n for n, e in s["entities"].items() if e.get("flagged_recent")] for src, s in res["sources"].items()}
            summary["steps"]["signals"] = {"dir": sdir, "flagged_recent": flagged}
            print(f"signals: flagged in the last 8 weeks {flagged}")

    # 2c. Calls: resolve against the benchmark press, feed hits into the ledger
    if a.calls and a.outlets and os.path.exists(a.calls):
        import calls as calls_mod
        rows = calls_mod.load(a.calls)
        changed = calls_mod.resolve(rows, json.load(open(a.outlets)), a.ledger) if a.ledger else []
        calls_mod.save(a.calls, rows)
        sc = calls_mod.score(rows)
        json.dump(sc, open(os.path.join(a.out, "calls-score.json"), "w"), indent=1)
        extra.append(f"calls={os.path.join(a.out, 'calls-score.json')}")
        extra.append(f"calls_list={os.path.abspath(a.calls)}")
        summary["steps"]["calls"] = {"changed": changed, "score": sc}
        print(f"calls: {sc['open']} open, {sc['hits']} hit, {sc['misses']} missed, next due {sc['next_due']}")
        if changed and a.ledger:  # a hit becomes a ledger row: refresh the audit so the gate sees it
            result = audit_mod.audit(a.run_dir, a.ledger, a.mean)
            json.dump(result, open(ap_path, "w"), indent=1)

    # 2c+. Registry and backtest, when configured, for the track-record slides
    for name in ("registry", "backtest"):
        path = d.get(name)
        if path and os.path.exists(path):
            extra.append(f"{name}={path}")

    # 2d. Discovery leads for the analyst
    if a.discover:
        rc = subprocess.call([sys.executable, "-I", os.path.join(HERE, "discover.py"), os.path.join(a.out, "discovery.json")])
        summary["steps"]["discovery"] = {"exit": rc, "file": os.path.join(a.out, "discovery.json")}

    # 3. Evidence capture
    caps_path = None
    if a.manifest:
        res = capture.run(json.load(open(a.manifest)), os.path.join(a.out, "captures"), 45,
                          os.path.dirname(os.path.abspath(a.manifest)))
        caps_path = os.path.join(a.out, "captures", "captures.json")
        tally = {}
        for it in res["items"]:
            tally[it["outcome"]] = tally.get(it["outcome"], 0) + 1
        summary["steps"]["capture"] = {"file": caps_path, "outcomes": tally}
        print(f"capture: {tally}")

    # 4. Copy check and render
    if a.slides:
        cmd = [sys.executable, "-I", os.path.join(HERE, "render.py"), a.slides, ap_path, os.path.join(a.out, "frames")]
        if caps_path:
            cmd += ["--captures", caps_path]
        for e in extra:
            cmd += ["--data", e]
        rc = subprocess.call(cmd)
        summary["steps"]["render"] = {"dir": os.path.join(a.out, "frames"), "exit": rc}
        print("render: ok" if rc == 0 else f"render: stopped (exit {rc}); see messages above")

    # 5. Spoken brief and video
    if a.media and a.slides and summary["steps"].get("render", {}).get("exit") == 0:
        cmd = [sys.executable, "-I", os.path.join(HERE, "media.py"), a.slides, ap_path, os.path.join(a.out, "frames")]
        for e in extra:
            cmd += ["--data", e]
        rc = subprocess.call(cmd)
        summary["steps"]["media"] = {"exit": rc, "receipt": os.path.join(a.out, "frames", "media.json")}
        print("media: ok" if rc == 0 else f"media: stopped (exit {rc})")

    summary["finished_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    json.dump(summary, open(os.path.join(a.out, "RUN.json"), "w"), indent=1)
    print(f"receipt: {os.path.join(a.out, 'RUN.json')}")


if __name__ == "__main__":
    main()
