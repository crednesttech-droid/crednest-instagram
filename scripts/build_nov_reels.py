#!/usr/bin/env python3
"""Render the approved Nov 16–29 silent reels using the reels-v2 production standard.

Only the six new Nxx media directories and reels_nov2026 manifests are written.
Original licensed stock, temporary caption PNGs and FFmpeg logs stay outside
the checkout. Narration is deliberately not generated; exact timed lines are
exported separately for queue.json and the later Sarvam pass.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import time

from PIL import Image, ImageChops, ImageCms, ImageDraw, ImageStat

from build_reels_v2 import FPS, GREEN, HEIGHT, INK, LIME, PAPER, WIDTH, ffconcat_path, font, run, wrap_words

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reels_nov2026"
DEFAULT_HOOK_DURATION = 0.8
END_CARD_DURATION = 1.5
MAX_REEL_DURATION = 90.0
MIN_WORD_DURATION = 0.18
CAPTION_BASELINE = 1260
SAFE = (250, 1500)
PLANS = {
    "N01": ["calculator", "signing", "calculator", "calculator", "signing"],
    "N04": ["document_review", "document_review", "signing", "document_review", "signing"],
    "N05": ["warehouse", "warehouse", "packing_box", "warehouse", "warehouse"],
    "N08": ["document_review", "calculator", "document_review", "signing", "document_review", "signing"],
    "N11": ["calculator", "spreadsheet", "calculator", "spreadsheet", "calculator"],
    "N12": ["machinery", "document_review", "spreadsheet", "document_review", "signing"],
}
CARD_FROM_SCENE = {"N01": 2, "N05": 2, "N11": 3}
SRGB = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
SOURCE_HASHES = {}


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def tracked(draw, xy, text, face, fill, boxes, label, anchor="lt"):
    box = draw.textbbox(xy, text, font=face, anchor=anchor)
    if box[0] < 72 or box[2] > 1008 or box[1] < SAFE[0] or box[3] > SAFE[1]:
        raise ValueError(f"{label}: unsafe bounds {box} for {text!r}")
    draw.text(xy, text, font=face, fill=fill, anchor=anchor)
    boxes.append({"label": label, "text": text, "box": list(box), "anchor": anchor, "origin": list(xy)})


def lines_for(text, size, width=904, weight="Extrabold"):
    face = font(size, weight)
    lines = wrap_words(text, face, width)
    return face, lines


def fitted(text, max_size, width, max_height, min_size=36, weight="Extrabold"):
    for size in range(max_size, min_size - 1, -1):
        face, lines = lines_for(text, size, width, weight)
        if max(face.getlength(" ".join(word for _, word in row)) for row in lines) <= width and len(lines) * math.ceil(size * 1.22) <= max_height:
            return face, lines, math.ceil(size * 1.22)
    raise ValueError(f"Text cannot fit without excessive shrinking: {text}")


def multiline(draw, text, x, y, face, lines, line_height, color, boxes, label, centered=False):
    for index, row in enumerate(lines):
        line = " ".join(word for _, word in row)
        tx = (WIDTH - face.getlength(line)) / 2 if centered else x
        tracked(draw, (round(tx), y + index * line_height), line, face, color, boxes, label)


def overlay_base(item):
    image = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    boxes = []
    return image, draw, boxes


def hook_overlay(item):
    image, draw, boxes = overlay_base(item)
    tracked(draw, (88, 284), item["series"], font(32, "Bold"), LIME, boxes, "series_tag")
    draw.line((88, 345, 992, 345), fill=(157, 243, 197, 105), width=2)
    face, lines, lh = fitted(item["hook"], 140, 904, 800, 65)
    y = round(820 - len(lines) * lh / 2)
    multiline(draw, item["hook"], 88, y, face, lines, lh, PAPER, boxes, "hook")
    tracked(draw, (88, 1435), "crednest.io", font(38, "Bold"), PAPER, boxes, "website")
    return image, boxes


def voice_overlay(item, scene_index, visible_count):
    image, draw, boxes = overlay_base(item)
    tracked(draw, (88, 284), item["series"], font(32, "Bold"), LIME, boxes, "series_tag")
    card_on = item.get("number_card") and scene_index >= CARD_FROM_SCENE[item["id"]]
    if card_on:
        draw.rounded_rectangle((72, 415, 1008, 912), radius=24, fill=(13, 33, 25, 238), outline=(157, 243, 197, 90), width=2)
        face, rows, lh = fitted(item["number_card"], 48, 848, 410, 36, "Bold")
        multiline(draw, item["number_card"], 116, round(660 - len(rows) * lh / 2), face, rows, lh, PAPER, boxes, "number_card")
    text = item["voice_lines"][scene_index]
    size = 62 if card_on else 78
    face, rows = lines_for(text, size, 904)
    lh = math.ceil(size * 1.22)
    first_baseline = CAPTION_BASELINE - (len(rows) - 1) * lh
    first_line = " ".join(word for _, word in rows[0])
    first_top = first_baseline + face.getbbox(first_line, anchor="ls")[1]
    if card_on and first_top < 940:
        raise ValueError("Caption overlaps the number card")
    for line_index, row in enumerate(rows):
        x = 88
        for word_index, word in row:
            if word_index < visible_count:
                tracked(draw, (round(x), first_baseline + line_index * lh), word, face, LIME if word_index == visible_count - 1 else PAPER, boxes, "voice_caption", anchor="ls")
            x += face.getlength(word + " ")
    return image, boxes


def end_overlay(item, disclaimer):
    image, draw, boxes = overlay_base(item)
    draw.rectangle((0, 0, WIDTH, HEIGHT), fill=(13, 33, 25, 235))
    face, rows, lh = fitted(item["cta"], 100, 904, 420, 54)
    multiline(draw, item["cta"], 88, round(795 - len(rows) * lh / 2), face, rows, lh, LIME, boxes, "cta")
    tracked(draw, (88, 1125), "crednest.io", font(52, "Bold"), PAPER, boxes, "website")
    face, rows, lh = fitted(disclaimer, 30, 904, 180, 26, "Medium")
    multiline(draw, disclaimer, 88, 1320, face, rows, lh, PAPER, boxes, "disclaimer")
    return image, boxes


def seconds_frames(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a finite positive number of seconds")
    try:
        seconds = float(value)
    except OverflowError as error:
        raise ValueError(f"{label} is outside the allowed duration range") from error
    if not math.isfinite(seconds) or seconds <= 0 or seconds > MAX_REEL_DURATION:
        raise ValueError(f"{label} must be finite, positive and at most 90 seconds")
    frames = round(seconds * FPS)
    if frames < 1:
        raise ValueError(f"{label} is shorter than one {FPS}fps frame")
    return frames


def verified_source_sha256(path, asset):
    stat = path.stat()
    key = (str(path), stat.st_size, stat.st_mtime_ns)
    if key not in SOURCE_HASHES:
        with path.open("rb") as source:
            SOURCE_HASHES[key] = hashlib.file_digest(source, "sha256").hexdigest()
    if SOURCE_HASHES[key] != asset["sha256"]:
        raise ValueError(f"Stock source differs from its licensed registry hash: {path}")
    return SOURCE_HASHES[key]


def load_timings(path, reels):
    """Validate user-editable scene durations and resolve frame-accurate timelines."""
    config = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(config, dict) or set(config) - {"version", "hook_duration", "end_card_duration", "reels", "notes"}:
        raise ValueError("Timings must be an object with version/hook_duration/end_card_duration/reels")
    if type(config.get("version")) is not int or config["version"] != 1:
        raise ValueError("Timings version must be the integer 1")
    values = config.get("reels")
    expected = {item["id"] for item in reels}
    if not isinstance(values, dict) or set(values) != expected:
        actual = set(values) if isinstance(values, dict) else set()
        raise ValueError(f"Timings reel IDs must match exactly; missing={sorted(expected-actual)}, unexpected={sorted(actual-expected)}")
    default_hook = config.get("hook_duration", DEFAULT_HOOK_DURATION)
    seconds_frames(default_hook, "hook_duration")
    end_duration = config.get("end_card_duration", END_CARD_DURATION)
    end_frames = seconds_frames(end_duration, "end_card_duration")
    if end_duration != END_CARD_DURATION or end_frames != round(END_CARD_DURATION * FPS):
        raise ValueError("The end card must remain exactly 1.5 seconds")
    resolved = {}
    for item in reels:
        reel_id = item["id"]
        timing = values[reel_id]
        if not isinstance(timing, dict) or set(timing) - {"scene_durations", "hook_duration", "notes"}:
            raise ValueError(f"{reel_id}: use only scene_durations and optional hook_duration/notes")
        durations = timing.get("scene_durations")
        if not isinstance(durations, list) or len(durations) != len(item["voice_lines"]):
            raise ValueError(f"{reel_id}: scene_durations must have exactly {len(item['voice_lines'])} entries, one per exact voice line")
        hook_frames = seconds_frames(timing.get("hook_duration", default_hook), f"{reel_id}.hook_duration")
        frames = []
        for index, (duration, line) in enumerate(zip(durations, item["voice_lines"])):
            scene_frames = seconds_frames(duration, f"{reel_id}.scene_durations[{index}]")
            words = len(line.split())
            minimum = math.ceil((words * MIN_WORD_DURATION + 0.1) * FPS)
            if scene_frames < minimum:
                raise ValueError(f"{reel_id} scene {index+1}: {words} words need at least {minimum/FPS:.3f}s for distinct readable word states")
            frames.append(scene_frames)
        total_frames = hook_frames + sum(frames) + end_frames
        if total_frames > round(MAX_REEL_DURATION * FPS):
            raise ValueError(f"{reel_id}: total exceeds the repository's 90-second reel limit")
        digest_input = {"hook_frames": hook_frames, "scene_frames": frames, "end_card_frames": end_frames, "voice_lines": item["voice_lines"]}
        digest = hashlib.sha256(json.dumps(digest_input, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()
        resolved[reel_id] = {"hook_frames": hook_frames, "scene_frames": frames, "end_card_frames": end_frames, "total_frames": total_frames, "hook_duration": hook_frames/FPS, "end_card_start": (total_frames-end_frames)/FPS, "end_card_duration": end_frames/FPS, "duration": total_frames/FPS, "timing_config_sha256": digest}
    return resolved


def timeline(item, timing):
    start_frame = timing["hook_frames"]
    scenes = []
    for index, (text, scene_frames) in enumerate(zip(item["voice_lines"], timing["scene_frames"])):
        end_frame = start_frame + scene_frames
        words = text.split()
        count = len(words)
        reveals = [start_frame + round(i * max(1, scene_frames - 4) / max(count, 1)) for i in range(count)]
        word_times = []
        for word_index, word in enumerate(words):
            word_end = reveals[word_index + 1] if word_index + 1 < count else end_frame
            word_times.append({"text": word, "start": round(reveals[word_index] / FPS, 6), "end": round(word_end / FPS, 6), "start_frame": reveals[word_index], "end_frame": word_end})
        scenes.append({"start": round(start_frame / FPS, 6), "end": round(end_frame / FPS, 6), "text": text, "words": word_times, "stock": PLANS[item["id"]][index]})
        start_frame = end_frame
    assert start_frame == timing["total_frames"] - timing["end_card_frames"]
    return scenes


def prepare(batch, source_registry, timings_path):
    OUT.mkdir(exist_ok=True)
    reels = [item for item in batch["items"] if item["type"] == "reel"]
    timings = load_timings(timings_path, reels)
    try:
        timings_label = timings_path.relative_to(ROOT).as_posix()
    except ValueError:
        timings_label = str(timings_path)
    storyboards = {"standard": "scripts/build_reels_v2.py safe zones, Manrope, exact-copy word reveal and silent FFmpeg composition", "timings_file": timings_label, "fps": FPS, "end_card_duration": END_CARD_DURATION, "caption_baseline": CAPTION_BASELINE, "caption_anchor": "ls", "safe_zone": list(SAFE), "timing_basis": "Editable per-scene recorded-voice durations, quantized individually to 30fps; actual voice alignment belongs to the later Sarvam pass.", "reels": {}}
    voice_export = {}
    for item in reels:
        timing = timings[item["id"]]
        scenes = timeline(item, timing)
        storyboards["reels"][item["id"]] = {"hook": item["hook"], "series": item["series"], "number_card": item.get("number_card"), "cta": item["cta"], "disclaimer": batch["disclaimer"], **timing, "voice_scenes": scenes}
        voice_export[item["id"]] = [{k: scene[k] for k in ("start", "end", "text")} for scene in scenes]
    names = {name for plan in PLANS.values() for name in plan}
    registry = {"license_url": "https://www.pexels.com/license/", "verified_on": "2026-11-12", "notes": "Original cached Pexels sources match the earlier registry SHA-256 values. Official Pexels license and used pages rechecked; faceless source/crop contact sheet reviewed. Original footage remains outside the repo. No location or endorsement claim.", "assets": [a for a in source_registry["assets"] if a["name"] in names]}
    write_json(OUT / "storyboards.json", storyboards)
    write_json(OUT / "queue_voice_scenes.json", voice_export)
    write_json(OUT / "stock_sources.json", registry)
    return reels, storyboards, registry


def build_one(item, batch, storyboard, registry, args):
    started = time.monotonic()
    reel_id = item["id"]
    timing = storyboard["reels"][reel_id]
    work = args.work_dir / reel_id
    work.mkdir(parents=True, exist_ok=True)
    captions_dir = work / "captions"
    captions_dir.mkdir(exist_ok=True)
    destination = ROOT / "media" / reel_id
    destination.mkdir(parents=True, exist_ok=True)
    log = work / "ffmpeg.log"
    entries = []
    text_elements = []
    def save_state(name, image, boxes, start_frame, end_frame, kind, text):
        path = captions_dir / f"{name}.png"
        image.save(path, compress_level=3)
        entries.append((path, end_frame - start_frame))
        text_elements.append({"kind": kind, "text": text, "start_frame": start_frame, "end_frame": end_frame, "boxes": boxes})
    hook_image, hook_boxes = hook_overlay(item)
    save_state("hook", hook_image, hook_boxes, 0, timing["hook_frames"], "hook", item["hook"])
    scenes = timing["voice_scenes"]
    for index, scene in enumerate(scenes):
        for word_index, word in enumerate(scene["words"]):
            image, boxes = voice_overlay(item, index, word_index + 1)
            save_state(f"{index:02}_{word_index:02}", image, boxes, word["start_frame"], word["end_frame"], "voice", " ".join(scene["text"].split()[:word_index + 1]))
    end_image, end_boxes = end_overlay(item, batch["disclaimer"])
    save_state("end", end_image, end_boxes, timing["total_frames"]-timing["end_card_frames"], timing["total_frames"], "end_card", item["cta"])
    concat = ["ffconcat version 1.0"]
    for path, frames in entries:
        concat += ["file " + ffconcat_path(path), "option framerate 30", f"duration {frames / FPS:.9f}"]
    concat += ["file " + ffconcat_path(entries[-1][0]), "option framerate 30"]
    caption_concat = work / "captions.ffconcat"
    caption_concat.write_text("\n".join(concat) + "\n", encoding="utf-8")

    asset_by_name = {a["name"]: a for a in registry["assets"]}
    segments = [(0.0, timing["hook_duration"], PLANS[reel_id][0])] + [(s["start"], s["end"], s["stock"]) for s in scenes] + [(timing["end_card_start"], timing["duration"], PLANS[reel_id][-1])]
    segment_paths, broll_manifest = [], []
    for index, (start, end, name) in enumerate(segments):
        asset = asset_by_name[name]
        source = args.stock_dir / asset["filename"]
        if not source.is_file():
            raise FileNotFoundError(source)
        duration = end - start
        offset = min(max(0.0, asset["duration_seconds"] - duration - 0.1), 0.45 + (index % 3) * 0.8)
        filters = "crop=trunc(ih*9/16/2)*2:ih:(iw-ow)/2:0,scale=1080:1920:flags=lanczos,fps=30,setsar=1,gblur=sigma=0.7,drawbox=x=0:y=0:w=iw:h=ih:color=0x0D2119@0.60:t=fill,format=yuv420p"
        segment_config = {"source_sha256": verified_source_sha256(source, asset), "source_size": source.stat().st_size, "input_loop": -1, "frames": round(duration*FPS), "offset": round(offset, 6), "filters": filters, "codec": "libx264", "preset": "veryfast", "crf": 20, "fps": FPS, "pixel_format": "yuv420p", "color_primaries": "bt709", "color_trc": "bt709", "colorspace": "bt709"}
        cache_key = hashlib.sha256(json.dumps(segment_config, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        segment = work / f"broll_{index:02}_{cache_key[:16]}.mp4"
        if not segment.exists() or args.force:
            run([args.ffmpeg, "-hide_banner", "-loglevel", "warning", "-y", "-threads", str(args.threads), "-stream_loop", "-1", "-ss", f"{offset:.6f}", "-i", str(source), "-t", f"{duration:.6f}", "-frames:v", str(segment_config["frames"]), "-vf", filters, "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-threads", str(args.threads), "-pix_fmt", "yuv420p", "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", str(segment)], log)
        segment_paths.append(segment)
        broll_manifest.append({"start": start, "end": end, "source_offset": offset, "name": name, "source_id": asset["id"], "page_url": asset["page_url"], "crop_notes": asset["faceless_crop_notes"], "cache_key": cache_key, "cache_config": segment_config})
    base_concat = work / "broll.ffconcat"
    base_concat.write_text("ffconcat version 1.0\n" + "\n".join("file " + ffconcat_path(path) for path in segment_paths) + "\n", encoding="utf-8")
    base = work / "broll.mp4"
    run([args.ffmpeg, "-hide_banner", "-loglevel", "warning", "-y", "-f", "concat", "-safe", "0", "-i", str(base_concat), "-an", "-c:v", "copy", str(base)], log)
    output = destination / "reel.mp4"
    run([args.ffmpeg, "-hide_banner", "-loglevel", "warning", "-y", "-threads", str(args.threads), "-i", str(base), "-f", "concat", "-safe", "0", "-i", str(caption_concat), "-filter_complex", "[0:v][1:v]overlay=shortest=1:format=auto,tpad=stop_mode=clone:stop_duration=0.1,format=yuv420p[v]", "-map", "[v]", "-an", "-t", str(timing["duration"]), "-frames:v", str(timing["total_frames"]), "-r", str(FPS), "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-maxrate", "3500k", "-bufsize", "7000k", "-threads", str(args.threads), "-pix_fmt", "yuv420p", "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", "-movflags", "+faststart", str(output)], log)
    frame = work / "first_frame.png"
    run([args.ffmpeg, "-hide_banner", "-loglevel", "warning", "-y", "-i", str(output), "-frames:v", "1", "-update", "1", str(frame)], log)
    Image.open(frame).convert("RGB").save(destination / "cover.jpg", "JPEG", quality=95, subsampling=0, icc_profile=SRGB)
    probe = subprocess.run([args.ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(output)], capture_output=True, text=True, check=True)
    probe_data = json.loads(probe.stdout)
    streams = probe_data["streams"]
    assert len(streams) == 1 and streams[0]["codec_type"] == "video", "Audio stream found"
    assert (streams[0]["width"], streams[0]["height"], streams[0]["codec_name"]) == (WIDTH, HEIGHT, "h264")
    assert int(streams[0]["nb_frames"]) == timing["total_frames"]
    assert abs(float(probe_data["format"]["duration"]) - timing["duration"]) < 0.01
    assert output.stat().st_size < 8_000_000
    # The cover is the fully formed first frame, with exactly hook/series/site.
    manifest = {"id": reel_id, "output": {"width": WIDTH, "height": HEIGHT, "fps": FPS, "duration": timing["duration"], "total_frames": timing["total_frames"], "hook_duration": timing["hook_duration"], "end_card_duration": timing["end_card_duration"], "timing_config_sha256": timing["timing_config_sha256"], "audio": False, "file_size_bytes": output.stat().st_size, "safe_zone": list(SAFE), "caption_baseline": CAPTION_BASELINE, "caption_anchor": "ls", "end_card_start": timing["end_card_start"], "cover_frame_seconds": 0, "cover_quality": 95, "cover_color_profile": "sRGB"}, "hook": item["hook"], "series": item["series"], "number_card": item.get("number_card"), "cta": item["cta"], "disclaimer": batch["disclaimer"], "cover_boxes": hook_boxes, "voice_scenes": scenes, "states": text_elements, "broll": broll_manifest, "ffprobe": probe_data, "render_seconds": round(time.monotonic() - started, 2)}
    write_json(OUT / "manifests" / f"{reel_id}.json", manifest)
    print(f"{reel_id}: complete, {timing['duration']:.3f}s silent H.264, {output.stat().st_size:,} bytes", flush=True)


def review_frames(items, args):
    """Extract factual review frames and verify motion between frames zero/one."""
    review = args.work_dir / "review"
    review.mkdir(exist_ok=True)
    sheet = Image.new("RGB", (1080, len(items) * 414), PAPER)
    draw = ImageDraw.Draw(sheet)
    checks = {}
    for row, item in enumerate(items):
        reel_id = item["id"]
        manifest_path = OUT / "manifests" / f"{reel_id}.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        scenes = manifest["voice_scenes"]
        example_index = CARD_FROM_SCENE.get(reel_id, min(2, len(scenes) - 1))
        end_start = manifest["output"]["end_card_start"]
        times = [0.0, scenes[0]["end"] - 1 / FPS, scenes[example_index]["end"] - 1 / FPS, end_start - 0.1, end_start + 0.5]
        source = ROOT / "media" / reel_id / "reel.mp4"
        frames = []
        for column, timestamp in enumerate(times):
            frame = review / f"{reel_id}_{column}.png"
            run([args.ffmpeg, "-hide_banner", "-loglevel", "warning", "-y", "-ss", f"{timestamp:.6f}", "-i", str(source), "-frames:v", "1", "-update", "1", str(frame)], review / "ffmpeg.log")
            image = Image.open(frame).convert("RGB")
            frames.append(image)
            image.thumbnail((216, 384), Image.Resampling.LANCZOS)
            sheet.paste(image, (column * 216, row * 414 + 28))
            draw.text((column * 216 + 8, row * 414 + 5), f"{reel_id} / {timestamp:.2f}s", font=font(17, "Bold"), fill=INK)
        frame_one = review / f"{reel_id}_frame_one.png"
        run([args.ffmpeg, "-hide_banner", "-loglevel", "warning", "-y", "-ss", "0.033333", "-i", str(source), "-frames:v", "1", "-update", "1", str(frame_one)], review / "ffmpeg.log")
        first = Image.open(review / f"{reel_id}_0.png").convert("RGB")
        second = Image.open(frame_one).convert("RGB")
        difference = ImageChops.difference(first, second)
        mean_change = sum(ImageStat.Stat(difference).mean) / 3
        if mean_change <= 0.01:
            raise ValueError(f"{reel_id}: no detectable movement from frame zero")
        manifest["first_frame_motion"] = {"frames_compared": [0, 1], "mean_absolute_rgb_change": round(mean_change, 6), "hook_text_unchanged": True, "passed": True}
        write_json(manifest_path, manifest)
        checks[reel_id] = manifest["first_frame_motion"]
    sheet.save(OUT / "frame_contact_sheet.jpg", "JPEG", quality=95, subsampling=0, icc_profile=SRGB)
    write_json(OUT / "motion_checks.json", checks)
    print("Review contact sheet and first-frame motion checks complete.", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", required=True, type=Path)
    parser.add_argument("--stock-dir", required=True, type=Path)
    parser.add_argument("--ffmpeg", default=shutil.which("ffmpeg") or "C:/Program Files/Jellyfin/Server/ffmpeg.exe")
    parser.add_argument("--ffprobe", default=shutil.which("ffprobe") or "C:/Program Files/Jellyfin/Server/ffprobe.exe")
    parser.add_argument("--source-registry", type=Path, default=ROOT / "reels_v2/stock_sources.json")
    parser.add_argument("--timings", type=Path, default=OUT / "timings.json", help="Per-reel hook/scene durations, in seconds; end card stays 1.5s.")
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--only", action="append", choices=list(PLANS))
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--review", action="store_true", help="Review existing renders without rebuilding.")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    args.work_dir = args.work_dir.resolve()
    args.stock_dir = args.stock_dir.resolve()
    if args.work_dir == ROOT or ROOT in args.work_dir.parents:
        parser.error("--work-dir must be outside the checkout")
    args.work_dir.mkdir(parents=True, exist_ok=True)
    batch = json.loads((ROOT / "batch_nov16_29/batch.json").read_text(encoding="utf-8"))
    source_registry = json.loads(args.source_registry.read_text(encoding="utf-8"))
    args.timings = args.timings.resolve()
    try:
        items, storyboards, registry = prepare(batch, source_registry, args.timings)
    except (OSError, ValueError, TypeError) as error:
        parser.error(f"Invalid timings: {error}")
    if args.prepare:
        return
    selected = [item for item in items if not args.only or item["id"] in args.only]
    if args.review:
        review_frames(selected, args)
        return
    for item in selected:
        build_one(item, batch, storyboards, registry, args)


if __name__ == "__main__":
    main()
