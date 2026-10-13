# Codex brief: faceless reels, target 8.5/10

Follow AGENTS.md. No person's face on screen (hands, desks, documents, shop floors are fine).
Rebuild the 6 reels in `queue.json` (D03-feed, D06-feed, D12-feed, D14-feed, D17-feed, D29-feed) and use this standard for every new reel.

## The 6 rules
1. **Hook in the first 2 seconds.** Open on a question or a tension, never on a label, logo or intro.
   Bad: "Illustrative scenario: a trading business pays suppliers…"
   Good: "Sales are up. So why is cash down?"
   Put "Illustrative scenario" as a small tag in a corner, not the opening line.
2. **Something changes every 2–3 seconds:** cut to a new B-roll clip, zoom, text animating in word by word, or a number counting up. No static card longer than 3 s.
3. **Real-world B-roll** behind the text: Indian shops, warehouses, factories, offices, invoices, calculators, laptops with spreadsheets, hands signing papers. Use only free-for-commercial-use stock (Pexels or Pixabay). No faces as the main subject, no bank logos, no currency close-ups that look like ads. Darken B-roll with the Deep Green #0D2119 overlay at 55–65% so brand text stays readable. List every clip URL in the PR description.
4. **Kinetic captions:** the line being spoken appears word by word, Manrope ExtraBold, lime #B8FF5A highlight on the key word. Captions burned in (most people watch muted).
5. **Safe zone:** keep all text between 250 px from the top and 420 px from the bottom (Instagram covers the bottom with caption and buttons). The disclaimer goes in the end card, placed at or above y = 1450.
6. **End card (last 3 s):** one clear action: "Comment CASH for the checklist" or "WhatsApp +91 98199 99057", then "Independent advice. Lender-led decisions." and the full disclaimer.

## Shape of a 25–30 s reel
| Time | What |
|---|---|
| 0–2 s | Hook question, big text, fast B-roll |
| 2–20 s | Three points, one per ~6 s, each with its own clip |
| 20–25 s | One concrete takeaway (a checklist line, a ratio to check) |
| 25–30 s | End card with CTA and disclaimer |

## Delivery
- 1080 × 1920 MP4, H.264, 30 fps, 25–30 s, **no audio track needed** (Claude adds the Sarvam voice and music).
- Put the voiceover lines in `voice_scenes` (`start`, `end`, `text`), matching on-screen timing; each line short enough to speak inside its slot.
- `cover.jpg` = the hook frame (1080 × 1920 JPEG).
- Set status `needs_voice`. Do not change captions in queue.json unless the hook change makes the caption's first line wrong; if you change it, say so in the PR.
- Run `python scripts/publish.py --check` before the PR. PR title: "Reels v2: faceless 8.5 standard".

## Compliance (unchanged)
No rates, approval promises, lender or bank names, client names or results. Case-style reels keep the "Illustrative scenario, not a client case" tag on screen.
