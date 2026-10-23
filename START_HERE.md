# Start here

The Scout watches the things you care about (artists, products, tools, shows) using public data with years of history, flags real changes with one fixed rule, and turns it into a poster-style edition: a PDF, a spoken brief and a short video. About 10 minutes the first time. No accounts or keys needed.

## The easy way: double-click

1. Unzip the folder anywhere, for example your Documents.
2. Double-click **Install The Scout**.
   - If your Mac says it "can't be opened because it is from an unidentified developer", right-click (or Control-click) the file, choose **Open**, then **Open** again. You only do this once per file.
3. A window opens and asks three things:
   - your niche (for example K-pop, indie games, skincare, AI tools)
   - 3 to 10 things to watch, separated by commas
   - your name for the footer (optional)
4. It finds each one on Wikipedia and shows a short description, so you can confirm it picked the right one. Type the number of the right match, or just press Return for the first.
5. Wait a few minutes while it pulls the history. Your edition opens by itself when it's ready.

Your editions live in **Documents › The Scout**, one folder per niche.

Every week after that, double-click **Make my Scout edition** to refresh it with new data. To watch a different niche, double-click **Start a new niche**.

What the installer needs: Python (your Mac offers to install it if it's missing), Google Chrome or another Chromium browser such as Edge or Brave, and optionally ffmpeg for the audio and video. If ffmpeg is missing and you have Homebrew, the installer adds it; if not, you still get the PDF and images.

## The agent way: just ask

If you use Codex or Claude Code, run the installer once, then say:

> Set up The Scout for K-pop, watching NewJeans, ILLIT and KATSEYE.

Your agent runs the same setup for you, reads the results, and can write a fuller weekly edition with judgment, dated calls and a lead-time ledger. Ask it "what's moving this week?" after each refresh.

## Ready-made starters

Want to see it work before choosing your own? Start from one of these:

```bash
python3 scripts/scout.py starter music
```

The other starters are `games` (indie games) and `ai-tools`.

## The terminal way

```bash
bash install.sh
```

```bash
python3 scripts/scout.py setup --niche "K-pop" --names "NewJeans, ILLIT, KATSEYE" --mark "Your Name" --yes
```

```bash
python3 scripts/scout.py run
```

Everything underneath is plain Python in `scripts/`. `README.md` lists every command, and `SKILL.md` is the playbook agents follow.

## Optional keys

Each key switches on more. Add one by running its command and pasting the key when asked. It's stored in your Mac's keychain, never in a file.

```bash
security add-generic-password -U -a "$USER" -s scout-elevenlabs -w
```

The same command works for `scout-youtube` (YouTube data), `scout-github` (faster GitHub pulls), `scout-spotify-id` and `scout-spotify-secret` (Spotify artist data), and `scout-higgsfield` (cover drawings and an animated intro; the key looks like `KEY_ID:SECRET`). Change the name after `-s`. With an ElevenLabs key you can pick a narrator by adding `"voice": {"voice_id": "..."}` to your edition file.

## What it never does

Post, send, schedule anything without you, sign in to your accounts, scrape sites that need a login, or call something a trend just because it got loud. It can't claim you spotted something early until its own ledger proves it.
