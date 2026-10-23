# Start here: your niche's first Scout edition

About 10 minutes, no accounts or keys. You get a 4:5 poster-style edition with a year of real behaviour data for the names you care about, a PDF, a spoken brief and a video.

## 1. Install

You need Python 3.9 or later, Google Chrome (or Chromium), and ffmpeg (`brew install ffmpeg` on a Mac). Then link this folder into your agent:

```bash
ln -s "$PWD" ~/.codex/skills/the-scout
```

```bash
mkdir -p ~/.claude/skills && ln -s "$PWD" ~/.claude/skills/the-scout
```

Check it works offline:

```bash
python3 scripts/self_test.py
```

## 2. Pick your names

Copy `templates/signals-basket-example.json` to `my-basket.json`. List 3 to 12 things in your niche: artists, products, tools, games, shows. For each, add whichever sources fit:

- `wikipedia`: the exact article title
- `bluesky` and `hackernews`: the words people actually use
- `github`: `owner/repo` for open-source tools

Keep the controls: steady, unrelated topics that absorb platform-wide swings. Fix both lists before you look at any results. Then let the tool confirm your titles:

```bash
python3 scripts/signals.py check my-basket.json --fix
```

## 3. Make the edition

Copy `templates/starter-edition.json` to `my-edition.json` and change the headline, series and mark to your niche and name. Then:

```bash
python3 scripts/run.py --out my-scout --signals my-basket.json --pull --slides my-edition.json --media
```

The first pull takes a few minutes, because it fetches up to four years of weekly history. After that it reuses the cache. Your edition is in `my-scout/frames/`: PNGs, `edition.pdf`, `brief.mp3` and `edition.mp4`.

## 4. Get ahead, honestly

- `python3 scripts/discover.py my-scout/discovery.json` lists things gaining attention fast.
- `python3 scripts/calls.py propose my-scout/discovery.json templates/benchmark_outlets.json my-scout/proposals.json` drops anything the big outlets already named. What's left is your chance to call it first: write it down with a date in a calls file.
- Run the same command next week. Calls resolve themselves against the press, and a hit becomes proof in your lead-time ledger.
- Your edition can't claim you were early until the ledger shows it. That's the point.

## Optional keys

Add any of these to the macOS keychain, or as environment variables named `SCOUT_` plus the name in capitals. Each switches a source on. Keys never touch your files.

```bash
security add-generic-password -a "$USER" -s scout-elevenlabs -w
```

The same command works for `scout-youtube`, `scout-github`, `scout-spotify-id`, `scout-spotify-secret` and `scout-higgsfield` (Higgsfield keys look like `KEY_ID:SECRET`; they power the cover drawings and the animated intro): change the name after `-s`, then paste the key when it asks. Set the narrator with `"voice": {"voice_id": "..."}` in your edition file.

## What it never does

Post, send, schedule, sign in, scrape gated platforms, or tell you something is a trend because it got loud.
