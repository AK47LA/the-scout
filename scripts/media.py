"""Spoken brief and 4:5 video for a rendered edition.

Usage: python3 media.py SLIDES.json AUDIT.json FRAMES_DIR [--data name=path ...]
Each slide's "voiceover" (else its headline and body) is resolved through the same placeholders and copy check.
Voice: ElevenLabs when a key is set (SCOUT_ELEVENLABS or keychain scout-elevenlabs); otherwise the macOS system
voice, labelled as a preview. Video: ffmpeg, each frame held for its line plus a beat. Writes brief.mp3, edition.mp4
and media.json into FRAMES_DIR. Never uploads or posts anything.
"""
import argparse, json, os, shutil, subprocess, sys, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import copycheck, signals  # noqa: E402

DEFAULT_VOICE = {"voice_id": "21m00Tcm4TlvDq8ikWAM", "model_id": "eleven_multilingual_v2"}


def line_for(s, data):
    raw = s.get("voiceover") or " ".join(x for x in (s.get("headline"), s.get("body") or s.get("sub")) if x)
    text, _ = copycheck.resolve(raw.replace("\n", " "), data)
    return text


def tts_eleven(text, key, voice, out):
    req = urllib.request.Request(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice['voice_id']}?output_format=mp3_44100_128",
        data=json.dumps({"text": text, "model_id": voice["model_id"]}).encode(),
        headers={"xi-api-key": key, "Content-Type": "application/json", "Accept": "audio/mpeg"})
    with urllib.request.urlopen(req, timeout=120) as r:
        open(out, "wb").write(r.read())


def tts_system(text, out):
    aiff = out.replace(".mp3", ".aiff")
    subprocess.run(["say", "-v", "Samantha", "-o", aiff, text], check=True, timeout=120)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", aiff, "-ar", "44100", "-ac", "2", "-b:a", "128k", out], check=True)
    os.remove(aiff)


def duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                         capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("slides")
    ap.add_argument("audit")
    ap.add_argument("frames")
    ap.add_argument("--data", action="append", default=[])
    a = ap.parse_args()
    a.frames = os.path.abspath(a.frames)  # ffmpeg resolves concat entries relative to the list file
    deck = json.load(open(a.slides))
    audit, data = copycheck.load_data(a.audit, a.data)
    problems, _ = copycheck.check(deck, data, audit.get("radar_gate", {}).get("open", False))
    if problems:
        for p in problems:
            print("FAIL", p)
        sys.exit("copy check failed; no audio or video made")
    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg not found; install it to make audio and video")
    key = signals.key("elevenlabs")
    engine = "elevenlabs" if key else ("system-preview" if shutil.which("say") else None)
    if not engine:
        sys.exit("no voice: add an ElevenLabs key, or run on macOS for the system preview voice")
    voice = dict(DEFAULT_VOICE, **deck.get("voice", {}))
    work = os.path.join(a.frames, "media")
    os.makedirs(work, exist_ok=True)
    rows, segs = [], []
    pngs = sorted(f for f in os.listdir(a.frames) if f.endswith(".png"))
    for i, (s, png) in enumerate(zip(deck["slides"], pngs), 1):
        text = line_for(s, data)
        mp3 = os.path.join(work, f"{i:02d}.mp3")
        stamp = os.path.join(work, f"{i:02d}.txt")
        sig = json.dumps({"engine": engine, "voice": voice if engine == "elevenlabs" else "system", "text": text})
        if not (os.path.exists(mp3) and os.path.exists(stamp) and open(stamp).read() == sig):  # only pay for changed lines
            if engine == "elevenlabs":
                tts_eleven(text, key, voice, mp3)
            else:
                tts_system(text, mp3)
            open(stamp, "w").write(sig)
        dur = duration(mp3)
        hold = round(dur + 0.6, 2)
        seg = os.path.join(work, f"{i:02d}.mp4")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", os.path.join(a.frames, png), "-i", mp3,
                        "-af", "apad", "-t", str(hold), "-c:v", "libx264", "-tune", "stillimage", "-pix_fmt", "yuv420p",
                        "-r", "30", "-vf", "scale=1080:1350", "-c:a", "aac", "-b:a", "160k", "-ar", "44100", seg], check=True)
        segs.append(seg)
        rows.append({"slide": i, "frame": png, "text": text, "seconds": hold})
        print(f"{i:02d} {hold:>5}s  {text[:80]}")
    intro = deck.get("intro_video")
    if intro:
        intro = intro if os.path.isabs(intro) else os.path.join(os.path.dirname(os.path.abspath(a.slides)), intro)
    if intro and os.path.exists(intro):  # an animated illustration opens the video; silent, cropped to 4:5
        seg = os.path.join(work, "00-intro.mp4")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", intro, "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                        "-shortest", "-vf", "scale=1080:-2,crop=1080:1350,fps=30", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                        "-c:a", "aac", "-b:a", "160k", "-ar", "44100", seg], check=True)
        segs.insert(0, seg)
        rows.insert(0, {"slide": 0, "frame": os.path.basename(intro), "text": "(animated illustration, no voice)", "seconds": round(duration(seg), 2)})
    lst = os.path.join(work, "list.txt")
    open(lst, "w").write("".join(f"file '{p}'\n" for p in segs))
    video = os.path.join(a.frames, "edition.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", video], check=True)
    brief = os.path.join(a.frames, "brief.mp3")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", video, "-vn", "-c:a", "libmp3lame", "-b:a", "128k", brief], check=True)
    total = round(sum(r["seconds"] for r in rows), 1)
    receipt = {"engine": engine, "voice": voice if engine == "elevenlabs" else "macOS Samantha (preview only)",
               "seconds": total, "video": video, "audio": brief, "slides": rows}
    json.dump(receipt, open(os.path.join(a.frames, "media.json"), "w"), indent=1)
    print(f"engine {engine}; {total}s; {video}; {brief}")


if __name__ == "__main__":
    main()
