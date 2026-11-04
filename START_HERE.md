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
| Your saves | What you sent to The Scout from your phone this week (once you've set up the Send to Scout shortcut). Everything is also kept in your Idea Museum |
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

### Note a thought with one press

For the things that aren't links (a scene in a film, a line in a book, an idea in the shower), make a second shortcut:

1. In **Shortcuts**, tap **+** and name it **Note an idea**.
2. Add **Dictate Text**. Set **Stop Listening** to **After Pause**.
3. Add a **Text** action: **Current Date** (format **ISO 8601**), a space, then **Dictated Text**.
4. Add **Append to Text File**: the same `Scout/saves.txt`, with **Make New Line** on.
5. Add **Show Notification** with the text "Noted."
6. On an iPhone with an Action Button, open **Settings › Action Button**, choose **Shortcut**, then **Note an idea**. Otherwise use **Settings › Accessibility › Touch › Back Tap**, or just say "Hey Siri, Note an idea."

Start with a word and a colon to tag it: "movie: the dinner scene in Buddy is all one take", "book:", "show:", "song:", "place:". Anything else is filed as an idea.

### Or use Apple Notes for all of it

If your Action Button already opens a new note, keep it. The Scout can read your ideas straight from Apple Notes on your Mac (Notes syncs them from your phone) every time it runs:

1. In Notes, make a folder for ideas, for example **Ideas** (a Quick Note lands in **Quick Notes**).
2. Jot ideas there. To save a post, tap **Share** on it in Instagram, Substack or anywhere else, choose **Notes**, and pick that folder.
3. Add `"notes_folders": ["Ideas"]` to `scout-config.json` in your niche's folder (agents: `local.json`).

Each run reads only those folders. A note becomes an idea in your museum, a link in a note is filed as a link with its preview, and a note you edit later updates its entry instead of adding a second one. The first time, your Mac asks whether The Scout may use Notes. Nothing in Notes is changed or deleted.

## Your Idea Museum

Everything you send or note is kept for good in your **Idea Museum**, on two boards:

- **Validated:** posts whose public numbers show they travelled (10,000 likes or 250,000 views and up).
- **Favorites:** what you love: your own thoughts and notes, and saves without big numbers.

One of each, from your own point of view, is a post. Every edition updates it. It lives next to your inbox in iCloud Drive › Shortcuts › Scout: open `museum.html` on your Mac to search and filter it, or on your phone in the Files app. `museum.md` is the same list as plain text.

**Bring in everything you've already saved on Instagram.** Instagram lets you download your own data, saved posts included:

1. In Instagram, open your profile, the menu, then **Accounts Center › Your information and permissions › Download your information**.
2. Choose **Download or transfer information**, your Instagram account, then **Some of your information**, and tick **Saved**.
3. Choose **Download to device**, **All time** and the **JSON** format, then **Create files**. Instagram emails you when the file is ready.
4. Download the .zip, then run `python3 scripts/museum.py import ~/Downloads/instagram-....zip` (or ask your agent to).

Every saved post is added straight away. Their previews (who posted it, the caption, the likes) are read a few at a time on each run so Instagram doesn't block the reads.

Ask your agent to "process my ideas" and it reads each new thing, says why it works, names the lane, and writes five angles on it. It never writes the post for you.

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
