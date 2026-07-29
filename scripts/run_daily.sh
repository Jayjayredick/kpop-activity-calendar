#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHONPATH=src python -m kpop_notice_collector.cli \
  --hours 24 \
  --out "output/latest_activity_tracker.xlsx"
