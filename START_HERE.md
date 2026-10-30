# Start here

The Scout reads your niche every time you run it: this week's headlines, the public posts of X accounts you choose, and years of public data (Wikipedia and Bluesky) for the things you track. Then it makes a poster-style edition: what came in, what went out, the move, four posts to make, what the press wrote, and the history charts. You get a PDF, plus a spoken brief and a short video if ffmpeg is installed. About 10 minutes the first time. No accounts or keys needed.

## The easy way: double-click

1. **Get the folder.** On this GitHub page, click the green **Code** button, then **Download ZIP**. Open your Downloads folder and double-click the ZIP to unzip it. Move the folder somewhere you'll keep it, for example Documents.
2. **Double-click Install The Scout.**
   - Your Mac will probably block it the first time, because it's a script from the internet. Click **Done**. Open **System Settings › Privacy & Security**, scroll down to the line about "Install The Scout", click **Open Anyway**, and confirm with your password or Touch ID. Then double-click it again. You do this once for each of the three double-click files.
   - On macOS 14 or older, right-click (or Control-click) the file, choose **Open**, then **Open** again.
   - Prefer to skip that? Open **Terminal**, type `bash ` (with a space), drag `install.sh` from the folder into the window, and press Return.
3. **The installer checks what it needs and asks before changing anything.** It asks before installing ffmpeg (for audio and video) and before adding The Scout to Codex or Claude Code, if you have them. Saying no is fine.
4. **A window asks four things:**
   - your niche (for example K-pop, indie games, skincare, AI tools)
   - 3 to 10 things to watch, separated by commas
   - your name for the footer (optional)
   - optional: up to 20 X accounts that cover your niche. The Scout reads each one's public posts to check it exists and shows you its name before keeping it. No login.
5. It finds each thing on Wikipedia and shows a short description, so you can confirm it picked the right one. Type the number of the right match, or press Return for the first.
6. Wait a few minutes while it pulls the history. Your edition opens by itself when it's ready.

Your editions live in **Documents › The Scout**, one folder per niche.

**Once a week, double-click Make my Scout edition.** It doesn't run by itself. Each run adds the newest weeks of data, today's headlines and the newest X posts, then makes a fresh edition dated today. To watch a different niche, double-click **Start a new niche**.

What the installer needs: Python (your Mac offers to install it if it's missing), Google Chrome or another Chromium browser such as Edge or Brave, and optionally ffmpeg for the audio and video. Without ffmpeg you still get the PDF and images.

## What's in each edition

| Page | What it shows |
|---|---|
| Cover | How many headlines and outlets it read this week, and X posts if you added accounts |
| In or out | What came in, what's at its high, and what went out, each judged against its own past year, with the number behind it |
| The move | One thing to do this week, picked by a fixed rule from those numbers |
| Four posts to make | Starting points, each tied to its receipt. The take is yours |
| The press | The week's headlines about your niche and the names the press wrote about most |
| Your saves | What you sent to The Scout from your phone this week (once you've set up the Send to Scout shortcut) |
| History | A year of weekly Wikipedia views and Bluesky posts for each thing you track |

## The agent way: just ask

If you use Codex or Claude Code, run the installer once, then say:

> Set up The Scout for K-pop, watching NewJeans, ILLIT and KATSEYE.

Your agent runs the same setup for you, reads the results, and can write a fuller weekly edition with judgment and dated calls. Ask it "what's moving this week?" after each refresh.

Your agent can also read X in your signed-in browser (searches, trends, your bookmarks and following list), but only if you switch it on. It's off by default because X's rules don't allow automated access, so it can put your account at risk. To switch it on, tell your agent you accept that, and it adds `"x_owner_consent": true` to `local.json`.

## Ready-made starters

Want to see it work before choosing your own? Start from one of these:

```bash
python3 scripts/scout.py starter music
```

The other starters are `marketing` (social platforms and marketing news), `games` (indie games) and `ai-tools`. Each comes with checked outlet feeds and an X watchlist.

## The terminal way

```bash
bash install.sh
```

```bash
python3 scripts/scout.py setup --niche "K-pop" --names "NewJeans, ILLIT, KATSEYE" --x "@hybe_labels" --mark "Your Name" --yes
```

```bash
python3 scripts/scout.py run
```

Everything underneath is plain Python in `scripts/`. `README.md` lists every command, and `SKILL.md` is the playbook agents follow.

## Send things to The Scout from your phone

Instagram doesn't let any app read your saved posts. So instead of tapping Save, tap Share, then **Send to Scout**. Each week your edition gets a "What you saved this week" page, and one of your four posts becomes a breakdown of something you sent. It works from Instagram, TikTok, X, YouTube and any web page.

Set it up once on your iPhone (about two minutes):

1. Open **Shortcuts**, tap **+**, and name the shortcut **Send to Scout**.
2. Tap the **(i)** button and turn on **Show in Share Sheet**. Let it receive URLs, Text and Safari web pages.
3. Add a **Text** action. Put **Current Date**, a space, then **Shortcut Input** in it. Tap Current Date and set its format to **ISO 8601**.
4. Add **Append to Text File**. Set the file path to `Scout/saves.txt` and turn on **Make New Line**. The file lives in iCloud Drive › Shortcuts, so your Mac sees it too.
5. Add **Show Notification** with the text "Sent to The Scout."

Now in any app: tap Share (on Instagram, the paper plane, then the share-sheet icon), then Send to Scout. The next time you make your edition, The Scout reads each link's public preview: who posted it and the caption or title. It never signs in to Instagram or anywhere else.

The Scout looks for the file at `~/Library/Mobile Documents/iCloud~is~workflow~my~workflows/Documents/Scout/saves.txt`. To keep it somewhere else, add `"saves_inbox": "/path/to/saves.txt"` to `scout-config.json` in your niche's folder (Documents › The Scout › your niche). Agents running `run.py` read the same key from `local.json`.

## Add outlets you trust

Headlines come from Google News search for your niche and each name you track. To add a site's own feed, open your niche's `basket.json` (in Documents › The Scout) and add an `outlets` list:

```json
"outlets": [{"name": "Billboard", "rss": "https://www.billboard.com/feed/"}]
```

## Optional keys

Each key switches on more. Add one by running its command and pasting the key when asked. It's stored in your Mac's keychain, never in a file.

```bash
security add-generic-password -U -a "$USER" -s scout-elevenlabs -w
```

The same command works for `scout-youtube` (YouTube data), `scout-github` (faster GitHub pulls), `scout-spotify-id` and `scout-spotify-secret` (Spotify artist data), `scout-higgsfield` (cover drawings and b-roll; the key looks like `KEY_ID:SECRET`), and `scout-chartmetric` (your Chartmetric API refresh token). Change the name after `-s`. ElevenLabs, Higgsfield and Chartmetric are paid services; everything else here is free. With an ElevenLabs key you can pick a narrator by adding `"voice": {"voice_id": "..."}` to your edition file.

## What it never does

Post, send or schedule anything, sign in to your accounts, scrape sites that need a login, or call something a trend just because it got loud. It can't claim you spotted something early until its own ledger proves it. Headlines come from Google News's public feeds, which are for personal use, so keep the edition for your own research.
