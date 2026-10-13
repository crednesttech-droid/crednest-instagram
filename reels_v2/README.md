# Faceless reels v2

`storyboards.json` defines the spoken copy, word highlights and 28-second timeline for each reel. `stock_sources.json` records every approved Pexels clip, its source URL, creator, license, download URL and checksum. Originals remain outside this repository.

The six reels were built in this order: D06, D12, D03, D14, D17, D29. Each starts with a question or tension, changes scene within three seconds, reveals the exact voice line word by word, and ends with the WhatsApp action, brand line and full disclaimer. D03 carries the full illustrative-scenario tag throughout.

## Rebuild

Install Pillow and make FFmpeg, ffprobe and a Chromium browser available. Download the registry's approved source files into an external `stock/` directory, using its listed filenames. Do not substitute unlicensed sources.

```sh
python scripts/build_reels_v2.py \
  --only D06-feed --only D12-feed \
  --work-dir /path/outside/repo/crednest-reels
```

Omit `--only` to build all six in the storyboard's order. Use `--ffmpeg`, `--ffprobe` or `--browser` when those executables are not on PATH. `--force` rebuilds cached B-roll segments after a crop or timing change.

The renderer writes `media/<id>/reel.mp4` and `cover.jpg`, and keeps intermediates, render logs and measured text bounds in the external work directory. It exports silent 1080 × 1920 H.264 at 30 fps for exactly 28 seconds; covers are the actual hook frame at 1.8 seconds, saved as quality-95 sRGB JPEGs. All final files are below 8 MB. The footage receives a 60% Deep Green overlay. Burned-in captions use Manrope ExtraBold with lime keywords, and all text stays within y=250–1500; the full disclaimer ends above y=1450.

## Voice handoff and review

The six queue entries contain matching `voice_scenes` and stay `needs_voice`. Old `voice` and `audio` metadata is removed because these exports have no audio. Captions, schedules and published state are preserved.

Use the existing **Re-voice reels (Sarvam)** workflow in **voice** mode after review. Music-only mode requires an existing voice track. This rebuild does not run that workflow or publish anything.

Run `python scripts/publish.py --check` before the PR. That check skips media belonging to `needs_voice` items, so also probe and fully decode every rebuilt MP4, inspect the hook/cuts/end card, check the cover profile and verify queue preservation. Keep stock source URLs and primary educational references in the PR description.
