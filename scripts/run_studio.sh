#!/bin/bash
# Launch Hermes RedTeam Studio (UI + backend) on port 8619
cd "$(dirname "$0")/.." || exit 1
exec .venv/bin/python -m uvicorn redteam.ui_server:app \
  --host 127.0.0.1 --port 8610 --reload 2>&1