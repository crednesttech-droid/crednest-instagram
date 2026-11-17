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
- CredNest is a debt-capital facilitator, not a lender or NBFC. Never imply approval, guaranteed sanction, specific rates, "lowest EMI", bank tie-ups or lender names.
- No client names, results or testimonials. Case stories are labelled "Illustrative scenario, not a client case or testimonial."
- Any market fact needs a source (RBI, CIBIL, SIDBI, CRIF, government circular) recorded in the PR description.
- Feed/reel captions end with the hashtags, then exactly: "CredNest is a debt-capital facilitator, not a lender or NBFC. Loan approval and terms are at the lender's sole discretion." 3–5 hashtags. Use no other disclaimer wording.
- WhatsApp contact: +91 98199 99057.
- One CTA per caption, rotated across the week: either "💬 Comment CHECKLIST — free credit-pack checklist DM mein bhejenge." or 'WhatsApp "Hi" to +91 98199 99057.' Roughly 60% CHECKLIST, 40% WhatsApp. "Independent advice. Lender-led decisions." on at most one post in four.

## Hooks (applies to every new item)
- Caption line 1 and the image headline are the hook: a specific pain, question or number the owner recognises ("CC renewal in 60 days? Start here."). Under 70 characters.
- Banned as headlines: abstract brand lines such as "X is part of the capital conversation", "Numbers tell a business story", "needs a relevant fit". Brand lines go in the body, not the hook.
- The "Illustrative scenario" tag goes in the caption's second paragraph and small on the image, never as the opening line or first reel frame.
- Captions are Hinglish in Roman script by default (v3, 18 Nov 2026); finance terms and the disclaimer stay in English. Caption line 1 = the cover hook, word for word.
- Hashtags: 3–5 niche tags tied to the topic (#CashCredit, #DSCR, #LoanAgainstProperty, #CIBILScore …). No #CredNest, #CapitalDesk or #CreditClarity: brand tags bring no discovery.
- Format mix: at least 60% of feed slots are reels; the rest mostly carousels; single images only for lead/CTA posts.
- Carousels are built to be saved: slide 1 hook, one idea per slide (6–8 slides), last slide a checklist summary with "Save karo".
- CTA rotation: CHECKLIST (the comment → DM keyword handled by scripts/engage.py) and WhatsApp "Hi". "Follow @crednest.io" is not a CTA.
- Any market fact must be checked against its source the week it posts; record the source in the PR.
- `scripts/render_hooks.py` renders hook covers and single-image cards in the house layout; add a spec and run it.

## Reels and voice
Do not use Windows/system text-to-speech. Put the narration lines in `voice_scenes` (`start`, `end`, `text`) and set status `needs_voice`; the "Re-voice reels" workflow adds the Sarvam voice.

## queue.json
Each item: `id`, `type` (image | carousel | reel | story), `publish_at` (ISO, +05:30), `media`, `cover` (reels), `caption` (empty for stories), `status`.
Statuses: `needs_content` → you build → `review` → Claude → `ready` → published. Never set `ready` yourself. Never edit `state/published.json`.
Always run `python scripts/publish.py --check` before opening a PR.
