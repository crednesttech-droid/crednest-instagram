# Retiming the six silent reels

`timings.json` is the timing source for N01, N04, N05, N08, N11 and N12. Its `reels.<id>.scene_durations` array contains seconds for each exact `voice_lines` entry in `batch_nov16_29/batch.json`, in the same order. Replace those durations after recording the narration; do not change the copy. `hook_duration` defaults to 0.8 seconds globally and may be overridden for one reel. The end card stays exactly 1.5 seconds.

Each duration is rounded independently to a 30fps frame count. The total is the hook plus all scenes plus the end card. There is no 14-second cap; the initial totals are 16.5–20.2 seconds, and the repository maximum is 90 seconds. Invalid IDs, missing scenes, non-numeric/non-finite/non-positive durations and scenes too short to show their words are rejected.

From the repository root, rebuild using an external working directory and the licensed stock cache:

```powershell
python scripts/build_nov_reels.py --timings reels_nov2026/timings.json --work-dir C:/path/outside-checkout/reels-work --stock-dir C:/path/to/licensed-stock
python scripts/build_nov_reels.py --timings reels_nov2026/timings.json --review --work-dir C:/path/outside-checkout/reels-work --stock-dir C:/path/to/licensed-stock
python scripts/build_nov_queue.py --retime
python scripts/check_nov_batch.py
python scripts/publish.py --check
```

`--only N01` (repeatable) restricts rebuilding to selected reels. `--prepare` validates timings and refreshes `storyboards.json` and `queue_voice_scenes.json` without rendering. `--timings` accepts another JSON file with the same schema. FFmpeg/ffprobe may be supplied through `--ffmpeg` and `--ffprobe`.

Retimed scenes automatically get new B-roll cache keys based on source hash, window, frame count, filters and encoding settings; `--force` is unnecessary. Long scenes loop the licensed source under a finite output duration. Actual rendering remains silent, with exact word captions sharing a baseline. The later Sarvam workflow adds audio; keep queue status `needs_voice` until that separate review is complete.

`--review` refreshes the frame contact sheet and first-frame motion checks. Render manifests include per-scene/per-word times, text bounds, timing configuration hashes, codec and duration evidence. `build_nov_queue.py --retime` copies only updated `voice_scenes` into the six existing reel entries and preserves captions, statuses and unrelated items.
