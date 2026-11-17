# Codex brief: 4 reels for 22 Nov – 1 Dec 2026 (content v3)

Follow AGENTS.md and REELS_BRIEF.md (v3). Captions, hooks and `voice_scenes` are final in `queue.json`; build the video to match them.

| Slot (IST) | id | Hook = frame 1 and cover | Built from |
|---|---|---|---|
| Sun 22 Nov 19:30 | N07 | ₹80 lakh ki machine. Loan lo ya lease? | 24 Oct machinery carousel: 86 shares |
| Sun 29 Nov 19:30 | N14 | Profit ₹50 lakh. Bank ne kam kyun maana? | 15 Oct profit-myth carousel: 66 shares, 8 follows |
| Mon 30 Nov 19:30 | CD10-red-flags | Loan se pehle ₹15,000 file charge? Ruk jao. | Rebuild of the held reel: remove every "Capital Desk" mark |
| Tue 1 Dec 19:30 | N1201-debtor-days | Customer 60 din. Supplier 30 din. | Rebuild of the held reel: remove every "Capital Desk" mark |

For each:
1. 1080 × 1920 MP4, 15–20 s, `media/<id>/reel.mp4` + `media/<id>/cover.jpg` (cover = frame 1).
2. One scene per `voice_scenes` line, same start/end. The hook text is on screen from frame 1, no logo or series intro before it.
3. Small corner tag "Illustrative example" from 2 s onwards (amounts are examples).
4. Set status `needs_voice`. The "Re-voice reels" workflow voices it with Sarvam `shubh` (bulbul:v3, hi-IN), as set on each item.
5. `python scripts/publish.py --check`, then PR "Content v3: 4 reels 22 Nov – 1 Dec".

N07 must be in review by Sat 21 Nov 12:00 IST, or the slot posts nothing (the autopilot moves it to the next free slot once it is ready).
