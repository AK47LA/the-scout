"""Higgsfield generation for edition illustration and motion. Output is illustration, never evidence.

Usage:
  python3 illustrate.py image "PROMPT" OUT_DIR [--model higgsfield-ai/soul/v2/standard] [--param key=value ...]
  python3 illustrate.py video IMAGE_URL "PROMPT" OUT_DIR [--model kling-video/v2.5-turbo/pro/image-to-video]
Key: SCOUT_HIGGSFIELD or keychain scout-higgsfield, as "KEY_ID:SECRET". Never written to files or logs.
Each run writes the media file plus a receipt (model, prompt, request id, status, source URL) and an entry in
OUT_DIR/manifest.json marked kind "illustration", so editions credit it as generated and never as a capture.
"""
import datetime, json, os, sys, time, urllib.error, urllib.request, uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import signals  # noqa: E402

API = "https://api.higgsfield.ai"


def _req(method, url, key, body=None):
    hdr = {"Authorization": f"Key {key}", "Content-Type": "application/json", "User-Agent": "TheScout/1.0"}
    if body is not None:
        hdr["Idempotency-Key"] = str(uuid.uuid4())
    data = json.dumps(body).encode() if body is not None else None
    with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=hdr, method=method), timeout=120) as r:
        return json.load(r)


def run(model, params, out_dir, kind, timeout=900):
    key = signals.key("higgsfield")
    if not key:
        sys.exit("no key: add scout-higgsfield to the keychain (KEY_ID:SECRET)")
    os.makedirs(out_dir, exist_ok=True)
    try:
        sub = _req("POST", f"{API}/{model}", key, params)
    except urllib.error.HTTPError as e:
        sys.exit(f"submit refused: HTTP {e.code} {e.read()[:300].decode('utf-8', 'replace')}")
    rid, status_url = sub["request_id"], sub["status_url"]
    started, wait, st = time.time(), 3, sub
    while st.get("status") not in ("completed", "failed", "nsfw", "canceled"):
        if time.time() - started > timeout:
            break
        time.sleep(wait)
        wait = min(wait * 1.5, 20)
        st = _req("GET", status_url, key)
    media = [m["url"] for m in (st.get("images") or [])] + [m["url"] for m in ([st["video"]] if isinstance(st.get("video"), dict) else (st.get("videos") or []))]
    files = []
    for i, u in enumerate(media):
        ext = os.path.splitext(u.split("?")[0])[1] or (".mp4" if kind == "video" else ".png")
        path = os.path.join(out_dir, f"{rid[:8]}-{i}{ext}")
        with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "TheScout/1.0"}), timeout=300) as r:
            open(path, "wb").write(r.read())
        files.append(path)
    receipt = {"model": model, "params": params, "request_id": rid, "status": st.get("status"), "kind": kind,
               "source_urls": media, "files": files, "seconds": round(time.time() - started, 1),
               "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat()}
    json.dump(receipt, open(os.path.join(out_dir, f"{rid[:8]}-receipt.json"), "w"), indent=1)
    mpath = os.path.join(out_dir, "manifest.json")
    man = json.load(open(mpath)) if os.path.exists(mpath) else {"schema": 1, "items": []}
    for i, f in enumerate(files):
        man["items"].append({"id": f"illustration-{rid[:8]}-{i}", "saved": os.path.basename(f), "kind": "illustration",
                             "credit": f"Illustration · Higgsfield {model.split('/')[1]}", "model": model, "request_id": rid})
    json.dump(man, open(mpath, "w"), indent=1)
    print(f"{st.get('status')}  {receipt['seconds']}s  {files or 'no media returned'}")
    return receipt


def params_from(argv):
    out = {}
    for a in argv:
        if "=" in a:
            k, v = a.split("=", 1)
            try:
                out[k] = json.loads(v)
            except ValueError:
                out[k] = v  # plain strings such as 4:5 or 2K
    return out


if __name__ == "__main__":
    mode = sys.argv[1]
    model = sys.argv[sys.argv.index("--model") + 1] if "--model" in sys.argv else None
    extra = params_from([sys.argv[i + 1] for i, a in enumerate(sys.argv) if a == "--param"])
    if mode == "image":
        run(model or "higgsfield-ai/soul/v2/standard", dict({"prompt": sys.argv[2]}, **extra), sys.argv[3], "image")
    elif mode == "video":
        run(model or "kling-video/v2.5-turbo/pro/image-to-video", dict({"image_url": sys.argv[2], "prompt": sys.argv[3]}, **extra),
            sys.argv[4], "video")
    else:
        sys.exit("mode must be image or video")
