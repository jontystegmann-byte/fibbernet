#!/bin/zsh
cd "$(dirname "$0")" || exit 1
python3 monitor.py run
result=$?
open reports/latest.html
if [ "$result" -ne 0 ]; then
  echo "The test or email failed; see the report and logs."
fi
echo "Press Return to close."
read -r
exit "$result"
