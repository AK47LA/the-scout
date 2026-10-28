#!/bin/bash
# The Scout installer. Checks what it needs, asks before linking into Codex and Claude or installing ffmpeg,
# tests itself, then starts the guided setup.
# Usage: bash install.sh          (interactive: asks before every change outside this folder)
#        bash install.sh --yes    (for agents: links into Codex and Claude, skips ffmpeg and the guided setup)
set -u
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
DIR="$(cd "$(dirname "$0")" && pwd)"
YES=0
[ "${1:-}" = "--yes" ] && YES=1
say() { printf "%s\n" "$*"; }
yes_no() {  # yes_no "Question" -> 0 for yes. Default is no; --yes answers yes.
  [ $YES -eq 1 ] && return 0
  (exec </dev/tty) 2>/dev/null || return 1  # no keyboard attached (a script or an agent): that's a no
  local ans
  read -r -p "$1 [y/N] " ans </dev/tty || return 1
  case "$ans" in [Yy]*) return 0 ;; *) return 1 ;; esac
}

say ""
say "Installing The Scout"
say "--------------------"

# 1. Python 3.9 or later
if ! command -v python3 >/dev/null 2>&1 || ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null; then
  say "The Scout needs Python 3.9 or later."
  if [ "$(uname)" = "Darwin" ]; then
    say "Opening Apple's free developer tools installer, which includes Python."
    say "When it finishes, run this installer again."
    xcode-select --install 2>/dev/null
  else
    say "Install Python 3 from python.org, then run this installer again."
  fi
  exit 1
fi
say "Python: $(python3 -c 'import platform; print(platform.python_version())')"

# 2. A Chromium browser draws the pages
BROWSER="$(python3 -I -c 'import sys; sys.path.insert(0, sys.argv[1]); import capture; print(capture.find_chrome() or "")' "$DIR/scripts")"
if [ -z "$BROWSER" ]; then
  say "No Chrome, Edge, Brave or Chromium found. The Scout uses one to draw its pages."
  say "Install Google Chrome from google.com/chrome, then run this installer again."
  exit 1
fi
say "Browser: $BROWSER"

# 3. ffmpeg makes the audio and video (optional)
if command -v ffmpeg >/dev/null 2>&1; then
  say "Video: ffmpeg found"
elif command -v brew >/dev/null 2>&1 && [ $YES -eq 0 ] && yes_no "ffmpeg makes the audio and video. Install it now with Homebrew (a few minutes)?"; then
  if brew install ffmpeg; then say "Video: ffmpeg installed"; else say "ffmpeg didn't install, so editions will skip audio and video."; fi
else
  say "Video: ffmpeg isn't installed, so editions make the PDF and images but skip audio and video."
  say "To add it later: install Homebrew from brew.sh, then run: brew install ffmpeg"
fi

# 4. Link into Codex and Claude, when they're installed, so your agent can run it. Asks first; never replaces another skill.
LINKED=0
for d in "$HOME/.codex" "$HOME/.claude"; do
  [ -d "$d" ] || continue
  target="$d/skills/the-scout"
  if [ -L "$target" ] && [ "$(readlink "$target")" = "$DIR" ]; then
    say "Already linked into $target"; LINKED=1; continue
  fi
  if [ -L "$target" ]; then  # a link from an earlier download: agents would keep running that older copy
    old="$(readlink "$target")"
    if [ ! -e "$old" ] || [ -f "$old/scripts/scout.py" ]; then
      if yes_no "$target points to another copy of The Scout ($old). Point it at this one?"; then
        rm "$target" && ln -s "$DIR" "$target" && say "Linked into $target (was $old)" && LINKED=1
      else
        say "Left $target pointing at $old"
      fi
      continue
    fi
  fi
  if [ -e "$target" ] || [ -L "$target" ]; then
    say "Something else is already at $target, so it was left alone."
    continue
  fi
  if yes_no "Add The Scout to $(basename "$d") as a skill (a link at $target)?"; then
    mkdir -p "$d/skills" && ln -s "$DIR" "$target" && say "Linked into $target" && LINKED=1
  fi
done
[ $LINKED -eq 0 ] && say "Not linked into Codex or Claude Code. The Scout runs fine on its own."

# 5. Self-test (offline)
LOG="$(mktemp "${TMPDIR:-/tmp}/scout-selftest.XXXXXX")"
if python3 -I "$DIR/scripts/self_test.py" >"$LOG" 2>&1; then
  say "Self-test: passed"
else
  say "Self-test failed. The details are in $LOG"
  exit 1
fi
chmod +x "$DIR"/*.command 2>/dev/null

say ""
say "The Scout is installed."
if [ $YES -eq 1 ]; then
  exit 0
fi
say ""
python3 -I "$DIR/scripts/scout.py" setup
