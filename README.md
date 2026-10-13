# CredNest Instagram autopilot

Posts and stories for @crednest.io publish themselves from this repo. No laptop needed.

## How it works
- `queue.json` holds every post with its IST time and status.
- **Instagram autopilot** (GitHub Action) runs every 15 minutes and publishes items with status `ready` whose time has passed. Max 3 per run; anything more than 36 hours late is skipped, so missed days never dump together.
- `state/published.json` records what is live, so nothing posts twice.
- Instagram downloads the images and videos from this repo's GitHub Pages site, which is why the repo is public. Tokens stay in GitHub Secrets.

## Schedule loaded (14 Oct – 12 Nov 2026)
43 items: 31 `ready`, 6 reels `needs_voice` (waiting for the Sarvam voice), 6 feed images `needs_content` (Codex, see BRIEF.md).

## One-time setup
1. **Meta token.** In the CredNest Meta app add the Instagram product (Instagram API with Instagram Login), add @crednest.io, grant `instagram_business_basic` and `instagram_business_content_publish`, and generate a long-lived token. Note the Instagram user ID.
2. **Secrets** (Settings → Secrets and variables → Actions → New repository secret):
   - `IG_USER_ID`
   - `IG_ACCESS_TOKEN`
   - `SARVAM_API_KEY` (from sarvam.ai, for the reel voice)
3. **Pages** (Settings → Pages): Deploy from branch `main`, folder `/ (root)`.
4. **Test:** Actions → *Instagram autopilot* → Run workflow with *Dry run* ticked.

## Weekly use
- Reels: Actions → *Re-voice reels (Sarvam)* → Run. Speaker default `aditya`; try `rahul`, `rohan`, `priya`, `neha`. Listen to the `revoiced-reels` download before they go live.
- New content: Codex follows AGENTS.md + BRIEF.md and opens a PR with status `review`; Claude checks and sets `ready`.
- Publish one item now: Run *Instagram autopilot* with *only* = item id and dry run unticked.

## Limits
- Story stickers (link, poll, questions) cannot be added through the API. Add them from the phone if needed.
- Long-lived tokens expire after about 60 days. Run `python scripts/publish.py --refresh-token` with the current token before then and update the secret. [VERIFY current expiry]
- GitHub scheduled runs can be delayed by a few minutes at busy times.
