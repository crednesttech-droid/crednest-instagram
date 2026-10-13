# AGENTS.md — rules for Codex (CredNest Instagram)

You make Instagram content for CredNest (@crednest.io). Claude writes the brief (BRIEF.md), you build files, Claude reviews and marks items `ready`. A GitHub Action publishes `ready` items on schedule.

## Brand
- Colours: Lime #B8FF5A, Ink #07150F, Deep Green #0D2119, Forest #315746, Paper #F8F8F4, Mint #9DF3C5.
- Font: Manrope (`brand/03_Fonts/`). Logo: `brand/04_Logos/` — use as supplied, never redraw or recolour.
- Layout language: see `brand/02_Instagram_Templates/` and existing files in `media/` (small caps kicker, large headline, short subtitle, lime CTA bar, footer disclaimer).
- Voice and banned claims: `brand/01_Guidelines/`.

## Formats
| Type | Size | Files |
|---|---|---|
| Image | 1080 × 1350 JPEG | `media/<id>/01.jpg` |
| Carousel | 2–10 slides, 1080 × 1350 JPEG | `media/<id>/01.jpg`, `02.jpg` … |
| Story | 1080 × 1920 JPEG, keep text out of top/bottom 250 px | `media/<id>/01.jpg` … |
| Reel | 1080 × 1920 MP4 (H.264, AAC), ≤ 90 s, plus `cover.jpg` | `media/<id>/reel.mp4` |

JPEG only (Instagram API rejects PNG). Each file under 8 MB.

## Compliance (non-negotiable)
- CredNest is an advisory firm, not a lender or NBFC. Never imply approval, guaranteed sanction, specific rates, "lowest EMI", bank tie-ups or lender names.
- No client names, results or testimonials. Case stories are labelled "Illustrative scenario, not a client case or testimonial."
- Any market fact needs a source (RBI, CIBIL, SIDBI, CRIF, government circular) recorded in the PR description.
- Feed/reel captions end with the hashtags, then: "CredNest is an advisory firm, not a lender. Loan approval and terms are at the lender's sole discretion." Max 5 hashtags.
- WhatsApp contact: +91 98199 99057.

## Reels and voice
Do not use Windows/system text-to-speech. Put the narration lines in `voice_scenes` (`start`, `end`, `text`) and set status `needs_voice`; the "Re-voice reels" workflow adds the Sarvam voice.

## queue.json
Each item: `id`, `type` (image | carousel | reel | story), `publish_at` (ISO, +05:30), `media`, `cover` (reels), `caption` (empty for stories), `status`.
Statuses: `needs_content` → you build → `review` → Claude → `ready` → published. Never set `ready` yourself. Never edit `state/published.json`.
Always run `python scripts/publish.py --check` before opening a PR.
