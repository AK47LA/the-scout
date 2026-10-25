"""Formats worth stealing: is the reader early or late, can they post it first on Reels, and what to keep versus make theirs.

  python3 formats.py FORMATS.json OUT.json

FORMATS.json is a list of formats the edition wants to recommend (pattern: templates/formats-example.json):
  name         what the format is, in plain words ("one move per video, gamified in levels")
  example      the post that shows it best: {"url", "creator", "date"}
  creators     distinct creators who posted the format, per platform per week (Monday dates), counted from saved
               captures only: {"tiktok": {"2026-10-12": 67, "2026-10-19": 263}, "instagram": {...}}
  captures     the evidence files the counts come from (evidence/YYYY-MM-DD/captures/...), one or more
  reels_checked  true only when an Instagram Reels search for the format was read and saved this week
  keep         what stays the same: the mechanics that made it work (structure, length, recurring character, cover, sound)
  make_yours   what the reader changes: the subject, the skill, the voice, the brand

Each platform's weekly series goes through the same rule as everything else (trendstate.classify, minimum 3 creators),
then becomes a plain verdict:
  EARLY  NEW, JUST TRENDING or RISING: worth filming this week
  NOW    PEAKING: post your version this week, before it turns
  LATE   FADING or GONE: only if it fits you very well
  HOLD   STEADY: it's settled; use it if it fits, it won't carry you
  UNKNOWN  no counts, or never above the minimum: say the stage is unknown, never guess
"Post first on Reels" is flagged only when TikTok is EARLY and a Reels search was actually checked this week and came back
under the minimum. An unchecked platform is missing coverage, not a gap to exploit.
A format without both a keep list and a make-yours list fails: copying the whole thing isn't a recommendation.
Never say a format will go viral.
"""
import json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from trendstate import classify  # noqa: E402

MIN_CREATORS = 3
VERDICT = {"NEW": "EARLY", "JUST TRENDING": "EARLY", "RISING": "EARLY", "PEAKING": "NOW",
           "FADING": "LATE", "GONE": "LATE", "STEADY": "HOLD"}
LINE = {"EARLY": "Early: worth filming this week.",
        "NOW": "Peaking: post your version this week, before it turns.",
        "LATE": "Late: only worth it if it fits you very well.",
        "HOLD": "Settled: use it if it fits, it won't carry you.",
        "UNKNOWN": "Stage unknown: no creator counts yet."}


def judge(fmt):
    """One format in, one row out. Raises ValueError on a format that can't be recommended."""
    name = (fmt.get("name") or "").strip()
    if not name:
        raise ValueError("format without a name")
    keep = [k for k in fmt.get("keep") or [] if str(k).strip()]
    mine = [k for k in fmt.get("make_yours") or [] if str(k).strip()]
    if not keep or not mine:
        raise ValueError(f"{name}: needs both a keep list and a make_yours list")
    counts = fmt.get("creators") or {}
    if counts and not fmt.get("captures"):
        raise ValueError(f"{name}: creator counts need the captures they were counted from")
    platforms = {}
    for platform, weekly in counts.items():
        weeks = sorted((w, float(v)) for w, v in (weekly or {}).items())
        row = classify(weeks, minimum=MIN_CREATORS) if weeks else None
        verdict = VERDICT[row["state"]] if row else "UNKNOWN"
        platforms[platform] = dict(row or {}, verdict=verdict,
                                   this_week=weeks[-1][1] if weeks else None,
                                   last_week=weeks[-2][1] if len(weeks) > 1 else None)
    order = ["EARLY", "NOW", "HOLD", "LATE", "UNKNOWN"]
    best = min((p["verdict"] for p in platforms.values()), key=order.index, default="UNKNOWN")
    tiktok = platforms.get("tiktok", {})
    reels = platforms.get("instagram", {})
    reels_quiet = bool(fmt.get("reels_checked")) and (reels.get("this_week") or 0) < MIN_CREATORS
    first_on_reels = tiktok.get("verdict") == "EARLY" and reels_quiet
    return {"name": name, "example": fmt.get("example"), "verdict": best, "line": LINE[best],
            "first_on_reels": first_on_reels,
            "reels_note": ("Rising on TikTok and not on Reels yet: post it first on Reels." if first_on_reels
                           else "Reels not checked this week." if not fmt.get("reels_checked") else ""),
            "platforms": platforms, "keep": keep, "make_yours": mine, "captures": fmt.get("captures") or []}


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    formats = json.load(open(sys.argv[1]))
    rows, errors = [], []
    for f in formats:
        try:
            rows.append(judge(f))
        except ValueError as e:
            errors.append(str(e))
    json.dump({"formats": rows, "errors": errors}, open(sys.argv[2], "w"), indent=1)
    for r in rows:
        print(f"{r['verdict']:8} {r['name']}{'  [first on Reels]' if r['first_on_reels'] else ''}")
    for e in errors:
        print("FAIL     " + e)
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
