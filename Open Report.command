#!/bin/zsh
cd "$(dirname "$0")" || exit 1
python3 monitor.py report || exit 1
open reports/latest.html
