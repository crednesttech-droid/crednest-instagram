# Content v3 build status (18 Nov 2026)

The 4 reels for 22 Nov – 1 Dec (N07, N14, CD10-red-flags, N1201-debtor-days) are built by Claude with
`scripts/build_motion_reels.py` from `reels_v3/specs.json` (brand colours, Manrope, hook on frame 1, 17–21 s).
They go `needs_voice` → "Re-voice reels (Sarvam)" workflow (speaker shubh) → `ready`.

New motion reels: add a spec to `reels_v3/specs.json` (one scene per `voice_scenes` line; kinds: hook, beat,
timeline, takeaway, end), then run `python scripts/build_motion_reels.py --only <id>`. Preview frames first with
`--frames <id>`.
