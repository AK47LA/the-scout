#!/bin/bash
# Double-click to install The Scout and make your first edition.
cd "$(dirname "$0")" || exit 1
bash ./install.sh
echo
read -n 1 -s -r -p "Press any key to close this window."
