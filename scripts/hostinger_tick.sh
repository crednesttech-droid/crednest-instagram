#!/bin/sh
# External 15-minute trigger for the Instagram autopilot (runs on Hostinger cron).
# GitHub's own cron fired only ~4x/day on 1-17 Nov, so posts went out hours late.
#
# Setup (one time, on Hostinger):
#   1. GitHub -> Settings -> Developer settings -> Fine-grained token
#      Repository: crednesttech-droid/crednest-instagram only
#      Permission: Contents = Read and write (needed for repository_dispatch). Expiry: 90 days.
#   2. hPanel -> File Manager: save the token in ~/.crednest_tick_token (outside public_html), chmod 600.
#   3. Upload this file to ~/hostinger_tick.sh, chmod 700.
#   4. hPanel -> Advanced -> Cron Jobs -> every 15 minutes:  sh ~/hostinger_tick.sh
TOKEN=$(cat "$HOME/.crednest_tick_token")
curl -fsS -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Accept: application/vnd.github+json" \
  https://api.github.com/repos/crednesttech-droid/crednest-instagram/dispatches \
  -d '{"event_type":"publish-tick"}' >/dev/null 2>&1 || echo "tick failed $(date)" >> "$HOME/crednest_tick.log"
