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
              "registry", "backtest", "x_manifest", "x_dir", "x_watchlist", "x_public_dir", "x_history", "x_keywords", "saves_inbox"):
        if cfg.get(k):
            v = os.path.expanduser(cfg[k].replace("{date}", datetime.date.today().isoformat()))
            out[k] = v if os.path.isabs(v) else os.path.join(root, v)
    for k in ("terms_bluesky", "tool_lanes"):  # plain settings, not paths
        if cfg.get(k):
            out[k] = cfg[k]
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
    ap.add_argument("--headlines", action="store_true", help="read this week's headlines for the niche (Google News plus basket outlets)")
    ap.add_argument("--media", action="store_true")
    ap.add_argument("--weekly", action="store_true", help="Monday run: weekly_out, weekly_slides, pull, calls, discover, media")
    a = ap.parse_args()
    if a.weekly:
        a.out = d.get("weekly_out", a.out)
        a.slides = d.get("weekly_slides", a.slides)
        a.pull = a.discover = a.media = a.headlines = True
    os.makedirs(a.out, exist_ok=True)
    import time
    t0 = time.time() - 2  # files written from here on belong to this run
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
            # In or out: every tracked item's state (new, just trending, rising, peaking, fading, gone) on one rule, every run
            rc = subprocess.call([sys.executable, "-I", os.path.join(HERE, "trendstate.py"), "signals", a.signals, sdir,
                                  os.path.join(a.out, "states-signals.json")])
            summary["steps"]["states_signals"] = {"exit": rc, "file": os.path.join(a.out, "states-signals.json")}

    # 2b+. This week's headlines for the niche and each tracked name (Google News search plus any outlet feeds; no key)
    if a.headlines and a.signals:
        rc = subprocess.call([sys.executable, "-I", os.path.join(HERE, "headlines.py"), a.signals, os.path.join(a.out, "headlines.json")])
        summary["steps"]["headlines"] = {"exit": rc, "file": os.path.join(a.out, "headlines.json")}

    # 2b++. What you sent to The Scout from your phone with the Send to Scout share-sheet Shortcut (Instagram, TikTok, X, links)
    import inbox as inbox_mod
    inbox_path = os.path.expanduser(d.get("saves_inbox") or inbox_mod.DEFAULT_INBOX)
    if os.path.exists(inbox_path):
        rc = subprocess.call([sys.executable, "-I", os.path.join(HERE, "inbox.py"), inbox_path, os.path.join(a.out, "saves.json"),
                              "--seen", os.path.join(a.out, "saves-seen.json")])
        summary["steps"]["saves"] = {"exit": rc, "file": os.path.join(a.out, "saves.json")}

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

    # 2d. X, every run, no login: the watchlist's public posts, ranked and compared with earlier weeks
    if d.get("x_watchlist"):
        xo = d.get("x_public_dir") or os.path.join(a.out, "x")
        rc = subprocess.call([sys.executable, "-I", os.path.join(HERE, "xpublic.py"), "pull", d["x_watchlist"], xo])
        rc2 = subprocess.call([sys.executable, "-I", os.path.join(HERE, "xpublic.py"), "report", xo, "--hours", "168"]
                              + (["--history", d["x_history"]] if d.get("x_history") else []))
        summary["steps"]["x_public"] = {"exit": max(rc, rc2), "file": os.path.join(xo, "report.json")}
        # every weekly pull, so each week is counted from its own pull, not from today's two pages per account
        hist = d.get("x_history") or os.path.dirname(xo)
        pulls = sorted(set(glob.glob(os.path.join(hist, "*", "posts.jsonl")) + [os.path.join(xo, "posts.jsonl")]))
        tracked = [e["name"] for e in json.load(open(a.signals)).get("entities", [])] if a.signals and os.path.exists(a.signals) else []
        rc = subprocess.call([sys.executable, "-I", os.path.join(HERE, "trendstate.py"), "x", *[p for p in pulls if os.path.exists(p)],
                              os.path.join(a.out, "states-x.json")] + (["--names", ",".join(tracked)] if tracked else []))
        summary["steps"]["states_x"] = {"exit": rc, "file": os.path.join(a.out, "states-x.json")}

    # 2d+. Discovery leads for the analyst (an agent's fuller edition; slow, so only with --discover)
    if a.discover:
        rc = subprocess.call([sys.executable, "-I", os.path.join(HERE, "discover.py"), os.path.join(a.out, "discovery.json")])
        summary["steps"]["discovery"] = {"exit": rc, "file": os.path.join(a.out, "discovery.json")}
        # New words people started using, and new AI tools people picked up: found, not supplied
        cmd = [sys.executable, "-I", os.path.join(HERE, "terms.py"), os.path.join(a.out, "terms.json")]
        if d.get("terms_bluesky"):
            cmd += ["--bluesky", d["terms_bluesky"]]
        if d.get("x_dir"):
            cmd += ["--x-dir", d["x_dir"]]
        elif d.get("x_manifest"):
            cmd += ["--x-manifest", d["x_manifest"]]
        rc = subprocess.call(cmd)
        summary["steps"]["terms"] = {"exit": rc, "file": os.path.join(a.out, "terms.json")}
        cmd = [sys.executable, "-I", os.path.join(HERE, "tools.py"), os.path.join(a.out, "tools.json")]
        if d.get("tool_lanes"):
            cmd += ["--priority", d["tool_lanes"]]
        rc = subprocess.call(cmd)
        summary["steps"]["tools"] = {"exit": rc, "file": os.path.join(a.out, "tools.json")}
        if d.get("x_watchlist") and d.get("x_keywords"):  # next week's searches follow what is trending now
            xo = d.get("x_public_dir") or os.path.join(a.out, "x")
            rc = subprocess.call([sys.executable, "-I", os.path.join(HERE, "xkeywords.py"), "update", d["x_keywords"],
                                  "--states", os.path.join(a.out, "states-x.json"), "--terms", os.path.join(a.out, "terms.json"),
                                  "--posts", os.path.join(xo, "posts.jsonl")])
            summary["steps"]["x_keywords"] = {"exit": rc, "file": d["x_keywords"]}

    # 2e. The week in one place: in and out, the move, four posts, the press (from this run's measured files only)
    if a.signals or a.headlines or os.path.exists(inbox_path):
        xo = d.get("x_public_dir") or os.path.join(a.out, "x")
        cmd = [sys.executable, "-I", os.path.join(HERE, "brief.py"), os.path.join(a.out, "brief.json")]
        def this_run(p):  # a file left by an earlier run would put last week's numbers on this week's pages
            return os.path.exists(p) and os.path.getmtime(p) >= t0
        for name, flag in (("states-signals.json", "--states"), ("states-x.json", "--states"), ("headlines.json", "--headlines"),
                           ("saves.json", "--saves")):
            if this_run(os.path.join(a.out, name)):
                cmd += [flag, os.path.join(a.out, name)]
        if d.get("x_watchlist") and this_run(os.path.join(xo, "report.json")):
            cmd += ["--x-report", os.path.join(xo, "report.json"), "--watchlist", d["x_watchlist"]]
            hist = d.get("x_history") or os.path.dirname(xo)
            pulls = {datetime.date.fromisoformat(n).isocalendar()[:2] for n in (os.listdir(hist) if os.path.isdir(hist) else [])
                     if len(n) == 10 and n[4] == "-" and os.path.exists(os.path.join(hist, n, "posts.jsonl"))}
            cmd += ["--x-weeks", str(len(pulls))]
        if a.signals:
            cmd += ["--basket", a.signals]
        rc = subprocess.call(cmd)
        summary["steps"]["brief"] = {"exit": rc, "file": os.path.join(a.out, "brief.json")}
        if rc == 0:
            extra.append(f"brief={os.path.join(a.out, 'brief.json')}")

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
