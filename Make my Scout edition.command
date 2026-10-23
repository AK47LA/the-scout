#!/bin/bash
# Double-click to refresh your most recent Scout edition with this week's data.
cd "$(dirname "$0")" || exit 1
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
python3 -I scripts/scout.py run
echo
read -n 1 -s -r -p "Press any key to close this window."
