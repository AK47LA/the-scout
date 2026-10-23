#!/bin/bash
# The Scout installer. Checks what it needs, links into Codex and Claude, tests itself, then starts the guided setup.
# Usage: bash install.sh          (interactive)
#        bash install.sh --yes    (no questions; skips the guided setup at the end)
set -u
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
DIR="$(cd "$(dirname "$0")" && pwd)"
YES=0
[ "${1:-}" = "--yes" ] && YES=1
say() { printf "%s\n" "$*"; }

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
BROWSER="$(python3 -I -c "import sys; sys.path.insert(0, '$DIR/scripts'); import capture; print(capture.find_chrome() or '')")"
if [ -z "$BROWSER" ]; then
  say "No Chrome, Edge, Brave or Chromium found. The Scout uses one to draw its pages."
  say "Install Google Chrome from google.com/chrome, then run this installer again."
  exit 1
fi
say "Browser: $BROWSER"

# 3. ffmpeg makes the audio and video (optional)
if command -v ffmpeg >/dev/null 2>&1; then
  say "Video: ffmpeg found"
elif command -v brew >/dev/null 2>&1; then
  say "Installing ffmpeg for the audio and video (this can take a few minutes)..."
  if brew install ffmpeg >/dev/null 2>&1; then say "Video: ffmpeg installed"; else say "ffmpeg didn't install, so editions will skip audio and video."; fi
else
  say "ffmpeg isn't installed, so editions will make the PDF and images but skip audio and video."
  say "To add them later: install Homebrew from brew.sh, then run: brew install ffmpeg"
fi

# 4. Link into Codex and Claude, when they're installed
LINKED=0
for d in "$HOME/.codex" "$HOME/.claude"; do
  if [ -d "$d" ]; then
    mkdir -p "$d/skills"
    ln -sfn "$DIR" "$d/skills/the-scout"
    say "Linked into $d/skills/the-scout"
    LINKED=1
  fi
done
[ $LINKED -eq 0 ] && say "Codex and Claude Code aren't installed here, so The Scout runs on its own. That's fine."

# 5. Self-test (offline)
LOG="$(mktemp -t scout-selftest)"
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
