#!/usr/bin/env python3
"""Independently validate the Nov 16-29 batch, including non-ready media.

Unlike publish.py --check, this command checks review and needs_voice items.
It does not edit the queue, render media, publish, or change publishing state.
Run: python scripts/check_nov_batch.py [--ffprobe /path/to/ffprobe]
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
import math
from pathlib import Path
import re
import shutil
import subprocess

from PIL import Image, ImageChops, ImageCms, ImageStat


ROOT = Path(__file__).resolve().parents[1]
IDS = [f"N{i:02d}" for i in range(1, 15)]
RESERVED = {"N07", "N14"}
FPS_TOLERANCE = 1 / 30 + 0.001
MAX_BYTES = 8_000_000


class Audit:
    def __init__(self):
        self.checks = []
        self.items = {}

    def check(self, name, passed, detail=None, item=None):
        entry = {"check": name, "passed": bool(passed)}
        if item:
            entry["id"] = item
        if detail is not None:
            entry["detail"] = detail
        self.checks.append(entry)
        return bool(passed)

    def error(self, name, detail, item=None):
        self.check(name, False, detail, item)


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def git(root, *args):
    return subprocess.run(
        ["git", "-C", str(root), *args], check=True,
        capture_output=True, encoding="utf-8", timeout=30,
    ).stdout


def canonical_words(text):
    return [word for word in text.split() if re.search(r"\w|₹", word)]


def wrapped_equal(actual, expected):
    return " ".join(str(actual).split()) == " ".join(str(expected).split())


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def safe_path(root, relative):
    path = (root / str(relative)).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError(f"Media path leaves the repository: {relative}")
    return path


def check_box(audit, box, canvas, label, item, safe_y=None):
    valid = (
        isinstance(box, (list, tuple)) and len(box) == 4
        and all(isinstance(n, (int, float)) and math.isfinite(n) for n in box)
    )
    if not audit.check(f"{label}.bbox_shape", valid, box, item):
        return
    x1, y1, x2, y2 = box
    audit.check(f"{label}.bbox_inside_canvas", 0 <= x1 < x2 <= canvas[0] and 0 <= y1 < y2 <= canvas[1], box, item)
    if safe_y:
        audit.check(f"{label}.bbox_inside_safe_zone", safe_y[0] <= y1 and y2 <= safe_y[1], {"bounds": box, "safe_y": safe_y}, item)


def check_elements(audit, elements, expected, canvas, label, item, safe_y=None):
    if not audit.check(f"{label}.elements_present", isinstance(elements, list) and bool(elements), item=item):
        return
    actual_roles = Counter(element.get("role") for element in elements)
    audit.check(f"{label}.exact_roles", actual_roles == Counter(expected.keys()), {"actual": dict(actual_roles), "expected": list(expected)}, item)
    for index, element in enumerate(elements):
        role = element.get("role")
        key = f"{label}.{role}.{index}"
        if role in expected:
            audit.check(f"{key}.exact_text", element.get("text") == expected[role], {"actual": element.get("text"), "expected": expected[role]}, item)
        check_box(audit, element.get("bounds", element.get("box")), canvas, key, item, safe_y)
        lines = element.get("lines")
        if lines is not None:
            joined = " ".join(line["text"] if isinstance(line, dict) else line for line in lines)
            audit.check(f"{key}.wrapped_lines_preserve_copy", wrapped_equal(joined, element.get("text", "")), {"joined": joined}, item)
            for line_index, line in enumerate(lines):
                if isinstance(line, dict):
                    check_box(audit, line.get("bounds", line.get("box")), canvas, f"{key}.line{line_index}", item, safe_y)


def jpeg_quality90_tables():
    buf = io.BytesIO()
    Image.new("RGB", (8, 8)).save(buf, "JPEG", quality=90)
    with Image.open(io.BytesIO(buf.getvalue())) as image:
        return image.quantization


def check_jpeg(audit, path, relative, size, item):
    if not audit.check(f"{relative}.exists", path.is_file(), item=item):
        return
    audit.check(f"{relative}.under_8mb", path.stat().st_size < MAX_BYTES, path.stat().st_size, item)
    try:
        with Image.open(path) as image:
            image.load()
            audit.check(f"{relative}.jpeg", image.format == "JPEG", image.format, item)
            audit.check(f"{relative}.geometry", image.size == size, list(image.size), item)
            audit.check(f"{relative}.rgb", image.mode == "RGB", image.mode, item)
            profile = image.info.get("icc_profile")
            profile_name = ""
            if profile:
                profile_name = ImageCms.getProfileName(ImageCms.ImageCmsProfile(io.BytesIO(profile))).strip()
            audit.check(f"{relative}.embedded_srgb", "srgb" in profile_name.lower(), profile_name or "No embedded ICC profile", item)
            tables = getattr(image, "quantization", {})
            reference = jpeg_quality90_tables()
            quality_ok = bool(tables) and all(
                key in reference and len(values) == 64
                and all(value <= reference[key][i] for i, value in enumerate(values))
                for key, values in tables.items()
            )
            audit.check(f"{relative}.quality_at_least_90", quality_ok, "Quantization tables compared with Pillow quality=90", item)
            audit.items.setdefault(item, {}).setdefault("files", []).append({"path": relative, "bytes": path.stat().st_size, "sha256": file_hash(path), "size": list(image.size), "icc_profile": profile_name})
    except Exception as exc:
        audit.error(f"{relative}.readable", str(exc), item)


def check_voice_scenes(audit, actual, canonical, item, speech_end=12.5):
    if not audit.check("voice_scenes.list", isinstance(actual, list), item=item):
        return
    expected_lines = canonical["voice_lines"]
    audit.check("voice_scenes.exact_full_lines", [scene.get("text") for scene in actual] == expected_lines, item=item)
    previous_end = 0.0
    for index, scene in enumerate(actual):
        start, end = scene.get("start"), scene.get("end")
        valid = all(isinstance(t, (int, float)) and math.isfinite(t) for t in (start, end))
        if not audit.check(f"voice_scene{index}.numeric_times", valid, scene, item):
            continue
        audit.check(f"voice_scene{index}.positive_duration", 0 <= start < end, {"start": start, "end": end}, item)
        audit.check(f"voice_scene{index}.ordered_nonoverlap", start >= previous_end - 0.001, {"previous_end": previous_end, "start": start}, item)
        audit.check(f"voice_scene{index}.before_end_card", end <= speech_end + 0.001, {"end": end, "speech_end": speech_end}, item)
        previous_end = end
    if actual:
        # The cover hook is already visible at frame zero; narration may begin
        # after that opening beat. It must still fit before the end card.
        audit.check("voice_scenes.start_after_hook", 0 <= actual[0].get("start", -1) < speech_end, item=item)
        audit.check("voice_scenes.finish_at_speech_boundary", abs(previous_end - speech_end) <= FPS_TOLERANCE, {"actual": previous_end, "expected": speech_end}, item)


def check_video(audit, root, path, item, ffprobe):
    if not audit.check("reel.exists", path.is_file(), item=item):
        return None
    if not audit.check("ffprobe.available", bool(ffprobe), item=item):
        return None
    try:
        audit.check("reel.under_8mb", path.stat().st_size < MAX_BYTES, path.stat().st_size, item)
        output = subprocess.run([ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)], capture_output=True, encoding="utf-8", check=True, timeout=90)
        probe = json.loads(output.stdout)
        video = [stream for stream in probe.get("streams", []) if stream.get("codec_type") == "video"]
        audio = [stream for stream in probe.get("streams", []) if stream.get("codec_type") == "audio"]
        audit.check("reel.single_video_stream", len(video) == 1, len(video), item)
        audit.check("reel.no_audio_stream", not audio, len(audio), item)
        if video:
            stream = video[0]
            audit.check("reel.h264", stream.get("codec_name") == "h264", stream.get("codec_name"), item)
            audit.check("reel.geometry", (stream.get("width"), stream.get("height")) == (1080, 1920), [stream.get("width"), stream.get("height")], item)
        duration = float(probe["format"]["duration"])
        audit.check("reel.duration_9_to_14s", 9 <= duration <= 14.001, duration, item)
        audit.items.setdefault(item, {})["video"] = {"path": path.relative_to(root).as_posix(), "bytes": path.stat().st_size, "sha256": file_hash(path), "duration": duration, "streams": [{key: stream.get(key) for key in ("codec_type", "codec_name", "width", "height", "pix_fmt", "r_frame_rate")} for stream in probe.get("streams", [])]}
        return duration
    except Exception as exc:
        audit.error("reel.ffprobe", str(exc), item)
        return None


def check_first_frames(audit, path, cover, item, ffmpeg):
    if not path.is_file() or not cover.is_file():
        return
    if not audit.check("ffmpeg.available_for_first_frame_check", bool(ffmpeg), item=item):
        return
    try:
        result = subprocess.run(
            [ffmpeg, "-v", "error", "-i", str(path), "-frames:v", "2", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"],
            capture_output=True, check=True, timeout=60,
        )
        length = 1080 * 1920 * 3
        if not audit.check("reel.two_first_frames_decoded", len(result.stdout) == length * 2, len(result.stdout), item):
            return
        first = Image.frombytes("RGB", (1080, 1920), result.stdout[:length])
        second = Image.frombytes("RGB", (1080, 1920), result.stdout[length:])
        with Image.open(cover) as encoded_cover:
            difference = ImageChops.difference(first, encoded_cover.convert("RGB"))
            cover_error = sum(ImageStat.Stat(difference).mean) / 3
        motion = ImageChops.difference(first, second)
        motion_error = sum(ImageStat.Stat(motion).mean) / 3
        audit.check("reel.cover_matches_actual_first_frame", cover_error < 3.0, {"mean_absolute_rgb_error": round(cover_error, 6), "threshold": 3.0, "purpose": "JPEG cover is the fully formed frame-zero hook"}, item)
        audit.check("reel.motion_from_first_frame", motion.getbbox() is not None and motion_error > 0.002, {"frame0_to_frame1_mean_absolute_rgb_error": round(motion_error, 6)}, item)
    except Exception as exc:
        audit.error("reel.first_frame_decode", str(exc), item)


def load_manifest(audit, path, name):
    try:
        value = read_json(path)
        audit.check(f"{name}.present_readable", True)
        return value
    except Exception as exc:
        audit.error(f"{name}.present_readable", str(exc))
        return {}


def check_carousel_manifest(audit, root, manifest, canonical):
    actual_slides = manifest.get("slides", [])
    expected_count = sum(len(item.get("slides", [])) for item in canonical["items"])
    audit.check("carousel_manifest.slide_count", len(actual_slides) == expected_count, {"actual": len(actual_slides), "expected": expected_count})
    keys = [(slide.get("id"), slide.get("slide")) for slide in actual_slides]
    audit.check("carousel_manifest.unique_slides", len(keys) == len(set(keys)))
    lookup = {(slide.get("id"), slide.get("slide")): slide for slide in actual_slides}
    for item in canonical["items"]:
        if item["type"] != "carousel":
            continue
        for slide in item["slides"]:
            number, ident = slide["number"], item["id"]
            actual = lookup.get((ident, number))
            label = f"slide{number}"
            if not audit.check(f"{label}.manifest_present", actual is not None, item=ident):
                continue
            final = number == len(item["slides"])
            tag = canonical["example_tag"] if number > 1 and re.search(r"\d", slide["text"]) else None
            footer = canonical["disclaimer"] if final else None
            expected_fields = {"path": f"media/{ident}/{number:02d}.jpg", "body": slide["text"], "cta": slide.get("cta"), "example_tag": tag, "footer": footer}
            for field, value in expected_fields.items():
                audit.check(f"{label}.{field}.exact", actual.get(field) == value, {"actual": actual.get(field), "expected": value}, ident)
            words = len(canonical_words(slide["text"]))
            audit.check(f"{label}.body_at_most_25_words", words <= 25, words, ident)
            if "main_body_words" in actual:
                audit.check(f"{label}.word_count_independent", actual["main_body_words"] == words, {"reported": actual["main_body_words"], "counted": words}, ident)
            expected = {"body": slide["text"]}
            if number == 1:
                expected.update(series=item["series"], website="crednest.io")
            if slide.get("cta"):
                expected["cta"] = slide["cta"]
            if tag:
                expected["example_tag"] = tag
            if footer:
                expected["footer"] = footer
            check_elements(audit, actual.get("elements"), expected, (1080, 1350), label, ident)


def check_reel_boxes(audit, boxes, expected, label, item):
    if not isinstance(boxes, list):
        audit.error(f"{label}.boxes", "Expected a list", item)
        return
    grouped, invalid = {}, []
    for box in boxes:
        grouped.setdefault(box.get("label"), []).append(box.get("text", ""))
        bounds = box.get("box")
        valid = isinstance(bounds, list) and len(bounds) == 4 and all(isinstance(v, (int, float)) and math.isfinite(v) for v in bounds)
        if valid:
            x1, y1, x2, y2 = bounds
            valid = 0 <= x1 < x2 <= 1080 and 250 <= y1 < y2 <= 1500
        if not valid:
            invalid.append(box)
    audit.check(f"{label}.safe_text_bounds", not invalid, invalid or None, item)
    audit.check(f"{label}.exact_text_roles", set(grouped) == set(expected), {"actual": list(grouped), "expected": list(expected)}, item)
    mismatches = []
    for role, value in expected.items():
        actual = " ".join(grouped.get(role, []))
        if not wrapped_equal(actual, value):
            mismatches.append({"role": role, "actual": actual, "expected": value})
    audit.check(f"{label}.exact_rendered_copy", not mismatches, mismatches or None, item)


def check_reel_manifest(audit, root, item, queued, canonical, registry):
    ident = item["id"]
    manifest = load_manifest(audit, root / "reels_nov2026/manifests" / f"{ident}.json", f"{ident}.render_manifest")
    if not manifest:
        return
    for field in ("hook", "series", "cta", "number_card"):
        audit.check(f"reel_manifest.exact_{field}", manifest.get(field) == item.get(field), item=ident)
    audit.check("reel_manifest.exact_disclaimer", manifest.get("disclaimer") == canonical["disclaimer"], item=ident)
    output = manifest.get("output", {})
    for field, expected in (("width", 1080), ("height", 1920), ("fps", 30), ("duration", 14.0), ("audio", False), ("safe_zone", [250, 1500]), ("caption_baseline", 1260), ("end_card_start", 12.5), ("cover_frame_seconds", 0)):
        audit.check(f"reel_manifest.output.{field}", field in output and output[field] == expected, output.get(field), ident)
    cover_expected = {"hook": item["hook"], "series_tag": item["series"], "website": "crednest.io"}
    check_reel_boxes(audit, manifest.get("cover_boxes"), cover_expected, "reel_cover", ident)
    scenes = manifest.get("voice_scenes", [])
    stripped = [{key: scene.get(key) for key in ("start", "end", "text")} for scene in scenes]
    audit.check("reel_manifest.voice_matches_queue", stripped == queued.get("voice_scenes"), item=ident)
    audit.check("reel_manifest.voice_matches_canonical", [scene.get("text") for scene in scenes] == item["voice_lines"], item=ident)
    expected_voice_states = []
    for index, scene in enumerate(scenes):
        words = scene.get("words", [])
        audit.check(f"reel_scene{index}.exact_all_words", [word.get("text") for word in words] == scene.get("text", "").split(), item=ident)
        timing_errors = []
        prior_end = round(scene.get("start", 0) * 30)
        prefix = []
        for word in words:
            start, end = word.get("start_frame"), word.get("end_frame")
            valid = isinstance(start, int) and isinstance(end, int) and start == prior_end and end > start
            if valid:
                valid = abs(word.get("start", -1) - start / 30) < 0.00001 and abs(word.get("end", -1) - end / 30) < 0.00001
            if not valid:
                timing_errors.append(word)
            prior_end = end if isinstance(end, int) else prior_end
            prefix.append(word.get("text", ""))
            expected_voice_states.append((" ".join(prefix), start, end))
        if prior_end != round(scene.get("end", 0) * 30):
            timing_errors.append({"final_word_end": prior_end, "scene_end": scene.get("end")})
        audit.check(f"reel_scene{index}.all_words_timed_contiguously", not timing_errors, timing_errors or None, ident)
    states = manifest.get("states", [])
    actual_voice_states = [(state.get("text"), state.get("start_frame"), state.get("end_frame")) for state in states if state.get("kind") == "voice"]
    audit.check("reel_manifest.word_by_word_states_exact", actual_voice_states == expected_voice_states, {"actual_states": len(actual_voice_states), "expected_states": len(expected_voice_states)}, ident)
    audit.check("reel_manifest.one_hook_one_end_card", Counter(state.get("kind") for state in states) == Counter({"hook": 1, "voice": len(expected_voice_states), "end_card": 1}), item=ident)
    previous_end = 0
    interval_errors = []
    number_card_seen = False
    for index, state in enumerate(states):
        start, end = state.get("start_frame"), state.get("end_frame")
        if not isinstance(start, int) or not isinstance(end, int) or start != previous_end or end <= start:
            interval_errors.append({"index": index, "start": start, "end": end, "previous_end": previous_end})
        if isinstance(end, int):
            previous_end = end
        kind = state.get("kind")
        if kind == "hook":
            expected = cover_expected
            audit.check("reel.hook_on_first_frame", start == 0 and state.get("text") == item["hook"], item=ident)
        elif kind == "end_card":
            expected = {"cta": item["cta"], "website": "crednest.io", "disclaimer": canonical["disclaimer"]}
            audit.check("reel.end_card_last_1_5s", start == 375 and end == 420 and state.get("text") == item["cta"], item=ident)
        elif kind == "voice":
            expected = {"series_tag": item["series"], "voice_caption": state.get("text", "")}
            if any(box.get("label") == "number_card" for box in state.get("boxes", [])):
                expected["number_card"] = item.get("number_card")
                number_card_seen = True
        else:
            expected = {}
        check_reel_boxes(audit, state.get("boxes"), expected, f"reel_state{index}", ident)
    audit.check("reel_manifest.no_frame_gaps_or_overlaps", not interval_errors and previous_end == 420, interval_errors or {"final_frame": previous_end}, ident)
    audit.check("reel_manifest.numeric_card_rendered_when_required", number_card_seen == bool(item.get("number_card")), item=ident)
    assets = {asset.get("name"): asset for asset in registry.get("assets", [])}
    broll_errors = []
    for segment in manifest.get("broll", []):
        asset = assets.get(segment.get("name"))
        if not asset or segment.get("source_id") != asset.get("id") or segment.get("page_url") != asset.get("page_url"):
            broll_errors.append(segment)
    audit.check("reel_manifest.licensed_broll_registry_matches", bool(manifest.get("broll")) and not broll_errors, broll_errors or None, ident)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--base", help="Protected base revision; defaults to batch.json base_revision, then HEAD")
    parser.add_argument("--ffprobe", help="ffprobe executable; auto-detects Jellyfin on Windows")
    parser.add_argument("--ffmpeg", help="ffmpeg executable for actual first-frame/cover comparison and motion check")
    parser.add_argument("--report", type=Path, default=Path("reports/nov16-29/validation.json"))
    args = parser.parse_args()
    root = args.root.resolve()
    candidate = Path("C:/Program Files/Jellyfin/Server/ffprobe.exe")
    ffprobe = args.ffprobe or shutil.which("ffprobe") or (str(candidate) if candidate.is_file() else None)
    ffmpeg_candidate = Path("C:/Program Files/Jellyfin/Server/ffmpeg.exe")
    ffmpeg = args.ffmpeg or shutil.which("ffmpeg") or (str(ffmpeg_candidate) if ffmpeg_candidate.is_file() else None)
    audit = Audit()
    canonical_path = root / "batch_nov16_29/batch.json"
    try:
        canonical = read_json(canonical_path)
        queue = read_json(root / "queue.json")
        base_revision = args.base or canonical.get("base_revision") or "HEAD"
        baseline_commit = git(root, "rev-parse", base_revision).strip()
        baseline = json.loads(git(root, "show", f"{baseline_commit}:queue.json"))
    except Exception as exc:
        raise SystemExit(f"Cannot load canonical batch, queue, or protected baseline: {exc}")
    expected_items = canonical["items"]
    audit.check("canonical.exact_14_ids_in_order", [item.get("id") for item in expected_items] == IDS)
    audit.check("canonical.confirmed_series", canonical.get("series_pending") is False and len(canonical.get("series_tags", {})) == 4)
    audit.check("canonical.cover_annotations_disabled", canonical.get("cover_annotations") is False)
    audit.check("user_clarifications.present", (root / "batch_nov16_29/USER_CLARIFICATIONS.md").is_file())
    counts = Counter(item.get("id") for item in queue)
    audit.check("queue.unique_ids", all(count == 1 for count in counts.values()))
    audit.check("queue.original_objects_unchanged", queue[:len(baseline)] == baseline, {"original_count": len(baseline)})
    audit.check("queue.only_14_batch_items_appended", [item.get("id") for item in queue[len(baseline):]] == IDS)
    try:
        changed = git(root, "diff", "--name-only", baseline_commit, "--", "state/published.json").strip()
        audit.check("state.published_unchanged_from_base", not changed, changed or f"git diff {baseline_commit} -- state/published.json is empty")
    except Exception as exc:
        audit.error("state.published_unchanged_from_base", str(exc))
    by_id = {item.get("id"): item for item in queue}
    for offset, item in enumerate(expected_items):
        ident = item["id"]
        expected_date = datetime(2026, 11, 16, 19, 30, tzinfo=timezone(timedelta(hours=5, minutes=30))) + timedelta(days=offset)
        audit.check("canonical.correct_schedule", item.get("publish_at") == expected_date.isoformat(), item.get("publish_at"), ident)
        actual = by_id.get(ident)
        if not audit.check("queue.item_present", actual is not None, item=ident):
            continue
        audit.items[ident] = {"type": item["type"], "publish_at": actual.get("publish_at"), "status": actual.get("status")}
        audit.check("queue.exact_publish_at", actual.get("publish_at") == item["publish_at"], actual.get("publish_at"), ident)
        if ident in RESERVED:
            audit.check("reserved.needs_content", actual.get("status") == "needs_content", actual.get("status"), ident)
            audit.check("reserved.empty_content", not any(actual.get(field) for field in ("media", "caption", "cover", "voice_scenes")), item=ident)
            directory = root / "media" / ident
            audit.check("reserved.no_media_files", not directory.exists() or not any(directory.iterdir()), item=ident)
            continue
        for field, value in (("type", item["type"]), ("caption", item["caption"]), ("topic", item["hook"])):
            audit.check(f"queue.exact_{field}", actual.get(field) == value, None if actual.get(field) == value else {"actual": actual.get(field), "expected": value}, ident)
        hashtags = re.findall(r"#[\w]+", actual.get("caption", ""))
        audit.check("caption.at_most_5_hashtags", len(hashtags) <= 5, hashtags, ident)
        audit.check("caption.instagram_length", len(actual.get("caption", "")) <= 2200, len(actual.get("caption", "")), ident)
        status = "needs_voice" if item["type"] == "reel" else "review"
        audit.check("queue.correct_review_status", actual.get("status") == status, actual.get("status"), ident)
        if item["type"] == "carousel":
            expected_paths = [f"media/{ident}/{slide['number']:02d}.jpg" for slide in item["slides"]]
            audit.check("queue.exact_slide_paths_order", actual.get("media") == expected_paths, actual.get("media"), ident)
            for relative in expected_paths:
                check_jpeg(audit, safe_path(root, relative), relative, (1080, 1350), ident)
        else:
            relative, cover = f"media/{ident}/reel.mp4", f"media/{ident}/cover.jpg"
            audit.check("queue.exact_reel_path", actual.get("media") == [relative], actual.get("media"), ident)
            audit.check("queue.exact_cover_path", actual.get("cover") == cover, actual.get("cover"), ident)
            duration = check_video(audit, root, safe_path(root, relative), ident, ffprobe)
            check_jpeg(audit, safe_path(root, cover), cover, (1080, 1920), ident)
            check_first_frames(audit, safe_path(root, relative), safe_path(root, cover), ident, ffmpeg)
            check_voice_scenes(audit, actual.get("voice_scenes"), item, ident, (duration - 1.5) if duration else 12.5)
    carousel_manifest = load_manifest(audit, root / "reports/nov16-29/carousel-render-manifest.json", "carousel_manifest")
    check_carousel_manifest(audit, root, carousel_manifest, canonical)
    registry = load_manifest(audit, root / "reels_nov2026/stock_sources.json", "reel_stock_registry")
    audit.check("reel_stock_registry.pexels_license_recorded", registry.get("license_url") == "https://www.pexels.com/license/")
    for item in expected_items:
        if item["type"] == "reel" and item["id"] in by_id:
            check_reel_manifest(audit, root, item, by_id[item["id"]], canonical, registry)
    failed = [check for check in audit.checks if not check["passed"]]
    report = {
        "status": "OK" if not failed else "FAILED",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "canonical_sha256": file_hash(canonical_path),
        "baseline_commit": baseline_commit,
        "scope": "14 batch queue slots: 6 carousels, 6 silent reels, 2 reserved; original queue and publishing state protected",
        "limits": "Text is checked against renderer manifests and bounds, not OCR. Faceless footage and visual quality require the accompanying human/visual review. Word timing describes silent captions; later voice synthesis still needs listening checks.",
        "summary": {"checks": len(audit.checks), "passed": len(audit.checks) - len(failed), "failed": len(failed)},
        "errors": failed,
        "items": audit.items,
        "checks": audit.checks,
    }
    output = args.report if args.report.is_absolute() else root / args.report
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{report['status']}: {len(audit.checks) - len(failed)}/{len(audit.checks)} checks passed; {len(failed)} failed")
    for error in failed[:30]:
        print(f"ERROR {error.get('id', 'batch')}: {error['check']}: {error.get('detail', '')}")
    if len(failed) > 30:
        print(f"... {len(failed) - 30} more failures in {output}")
    print(f"Report: {output}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
