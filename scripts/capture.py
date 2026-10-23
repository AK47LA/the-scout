"""Real evidence imagery with receipts: headless screenshots of public pages, plus captures the Scout already saved.

Usage: python3 capture.py MANIFEST.json OUT_DIR [--timeout 45]
MANIFEST.json: {"items": [{"id": "wired-ai", "url": "https://...", "credit": "WIRED", "width": 1280, "height": 900},
                          {"id": "x-post", "saved": "/path/to/saved.png", "url": "https://x.com/...", "credit": "X / @handle"}]}
Never signs in, accepts cookies or bypasses gates. Social platforms are never captured live; only saved files are used.
Writes OUT_DIR/<id>.png (or the saved file's copy) and OUT_DIR/captures.json.
"""
import datetime, json, os, shutil, signal, subprocess, sys, tempfile, urllib.parse

SOCIAL = ("x.com", "twitter.com", "instagram.com", "tiktok.com", "facebook.com", "threads.net", "linkedin.com")
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36")


def find_chrome():
    cands = [os.environ.get("SCOUT_CHROME"),
             "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
             "/Applications/Chromium.app/Contents/MacOS/Chromium",
             "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
             "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
             os.path.expanduser("~/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
             shutil.which("google-chrome"), shutil.which("chromium"), shutil.which("chromium-browser"),
             shutil.which("microsoft-edge"), shutil.which("brave-browser")]
    return next((c for c in cands if c and os.path.exists(c)), None)


def screenshot(chrome, url, out_png, width=1280, height=900, timeout=45, budget_ms=9000, extra=None):
    """Run headless Chrome in its own process group so a hung page can be killed whole."""
    prof = tempfile.mkdtemp(prefix="scout-chrome-")
    args = [chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=1",
            f"--window-size={width},{height}", f"--virtual-time-budget={budget_ms}", f"--user-agent={UA}",
            f"--user-data-dir={prof}", f"--screenshot={out_png}"] + (extra or []) + [url]
    if os.path.exists(out_png):
        os.remove(out_png)
    proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    try:
        proc.wait(timeout=timeout)
        outcome = "ok" if os.path.exists(out_png) and os.path.getsize(out_png) > 0 else "failed"
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.wait()
        outcome = "ok" if os.path.exists(out_png) and os.path.getsize(out_png) > 0 else "timeout"
    finally:
        shutil.rmtree(prof, ignore_errors=True)
    return outcome


def host(url):
    h = urllib.parse.urlparse(url or "").netloc.lower()
    return h[4:] if h.startswith("www.") else h


def run(manifest, out_dir, timeout=45, base_dir=None):
    """base_dir resolves relative "saved" paths, normally the manifest's own folder."""
    os.makedirs(out_dir, exist_ok=True)
    chrome = find_chrome()
    receipts = []
    for it in manifest.get("items", []):
        rec = {"id": it["id"], "url": it.get("url"), "credit": it.get("credit") or host(it.get("url")),
               "captured_at": datetime.datetime.now(datetime.timezone.utc).isoformat()}
        if it.get("saved"):
            src = os.path.expanduser(it["saved"])
            if base_dir and not os.path.isabs(src):
                src = os.path.join(base_dir, src)
            if os.path.exists(src):
                ext = os.path.splitext(src)[1].lower() or ".png"
                dst = os.path.join(out_dir, f"{it['id']}{ext}")
                shutil.copyfile(src, dst)
                rec.update(method="saved", outcome="ok", file=dst, saved_from=src)
            else:
                rec.update(method="saved", outcome="missing", file=None, saved_from=src)
        elif any(host(it.get("url")).endswith(s) for s in SOCIAL):
            rec.update(method="live", outcome="skipped_social", file=None,
                       note="Social platforms are only used from captures the Scout saved under its own gates.")
        elif not chrome:
            rec.update(method="live", outcome="no_browser", file=None, note="Set SCOUT_CHROME to a Chrome or Chromium binary.")
        else:
            dst = os.path.join(out_dir, f"{it['id']}.png")
            outcome = screenshot(chrome, it["url"], dst, it.get("width", 1280), it.get("height", 900), timeout)
            attempts = 1
            if outcome == "timeout":  # pages with endless timers often settle with a shorter virtual time budget
                outcome = screenshot(chrome, it["url"], dst, it.get("width", 1280), it.get("height", 900), timeout, 4000)
                attempts = 2
            rec.update(method="live", outcome=outcome, attempts=attempts, file=dst if outcome == "ok" else None)
        receipts.append(rec)
    result = {"schema": 1, "browser": chrome, "timeout_s": timeout, "items": receipts}
    json.dump(result, open(os.path.join(out_dir, "captures.json"), "w"), indent=1)
    return result


if __name__ == "__main__":
    t = 45
    if "--timeout" in sys.argv:
        t = int(sys.argv[sys.argv.index("--timeout") + 1])
    res = run(json.load(open(sys.argv[1])), sys.argv[2], t, os.path.dirname(os.path.abspath(sys.argv[1])))
    for r in res["items"]:
        print(f"{r['id']:<24} {r['method']:<6} {r['outcome']}")
