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

## Facebook Page cross-post
Every feed item (image, carousel, reel) that goes live on Instagram is also posted to the CredNest Facebook Page by the same autopilot run. Stories stay Instagram-only. The "Comment CHECKLIST" CTA is swapped for the WhatsApp CTA on Facebook, because comment-to-DM works on Instagram only.

One-time setup:
1. developers.facebook.com → Tools → Graph API Explorer → choose the CredNest Meta app → add permissions `pages_show_list`, `pages_read_engagement`, `pages_manage_posts` → Generate Access Token (log in, tick the CredNest.io Page).
2. In "User or Page", pick **CredNest.io** to get the Page token. Extend it with the Access Token Debugger → "Extend Access Token" so it does not expire in an hour.
3. Add it as repository secret `FB_PAGE_TOKEN`. `FB_PAGE_ID` is optional (read from the token).
4. Backfill what is already on Instagram: Actions → *Facebook backfill* → Run with *Dry run* ticked, check the list, then run again unticked. Posts are back-dated to their Instagram time [VERIFY: Page back-dating via API].

## Limits
- Story stickers (link, poll, questions) cannot be added through the API. Add them from the phone if needed.
- Long-lived tokens expire after about 60 days. Run `python scripts/publish.py --refresh-token` with the current token before then and update the secret. [VERIFY current expiry]
- GitHub scheduled runs can be delayed by a few minutes at busy times.
