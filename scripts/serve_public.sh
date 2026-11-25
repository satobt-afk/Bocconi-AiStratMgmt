#!/bin/zsh
# Run the app for access from the internet through Tailscale Funnel.
#
#   scripts/serve_public.sh                 # real accounts only
#   DEMO_MODE=on scripts/serve_public.sh    # + the /demo door (e.g. on presentation day)
#
# Then, in another terminal:  tailscale funnel --bg 8000
#
# - APP_ENV=production: Secure cookies (HTTPS only) and HSTS
# - 127.0.0.1 only: not reachable on the Wi-Fi; Tailscale is the only way in
# - caffeinate: keeps the Mac awake while this runs (Ctrl+C stops both)
set -e
cd "$(dirname "$0")/.."
source .venv/bin/activate
export APP_ENV=production
exec caffeinate -is python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
