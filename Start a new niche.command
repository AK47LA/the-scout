#!/bin/bash
# Double-click to set up The Scout for another niche.
cd "$(dirname "$0")" || exit 1
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
python3 -I scripts/scout.py setup
echo
read -n 1 -s -r -p "Press any key to close this window."
