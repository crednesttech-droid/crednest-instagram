#!/usr/bin/env python3
"""Independently validate the Nov 16-29 batch, including non-ready media.

Unlike publish.py --check, this command checks review and needs_voice items.
It does not edit the queue, render media, publish, or change publishing state.
Run: python scripts/check_nov_batch.py [--ffprobe /path/to/ffprobe]
"""
from __future__ import annotations

import argparse
from collections import Counter
import copy
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import sys

from PIL import Image, ImageChops, ImageCms, ImageDraw, ImageFont, ImageStat


ROOT = Path(__file__).resolve().parents[1]
IDS = [f"N{i:02d}" for i in range(1, 15)]
RESERVED = {"N07", "N14"}
AUTHORIZED_HOLD_IDS = (
    "CD04-preipo", "CD05-dscr", "D23-new", "CD06-bt-topup",
    "CD07-prepayment", "CD08-small-syndication", "CD09-lap-vs-pl",
    "CD10-red-flags", "CR01-lap-emi", "CD11-emi-bounce",
    "CR02-consolidation", "CR03-rate-half", "N1128-cc-full",
    "N1128-cc-full-story", "N1129-cma",
)
# Exact owner-supplied pronunciation lines. Do not normalize their Unicode.
CANONICAL_SAY = {
    "N01": [
        "CIBIL 780 है। फिर भी loan कम क्यों मिला?",
        "क्योंकि bank, score के बाद आपकी EMI का बोझ देखता है।",
        "Example: कमाई एक लाख महीना, पुरानी EMI पैंतीस हज़ार।",
        "अगर bank पचास percent तक EMI मानता है, तो नई EMI की जगह सिर्फ़ पंद्रह हज़ार।",
        "Score अच्छा है। जगह कम है।",
    ],
    "N04": [
        "ITR में बारह लाख। Bank statement में चालीस लाख।",
        "Bank किस पर भरोसा करेगा?",
        "ज़्यादातर lender, loan ITR की कमाई पर नापते हैं।",
        "Statement सिर्फ़ यह दिखाता है कि पैसा आया। कमाई कितनी थी, यह ITR बताता है।",
        "दोनों की कहानी एक होनी चाहिए।",
    ],
    "N05": [
        "Bank ने CC limit क्यों कम की?",
        "क्योंकि limit काग़ज़ पर होती है। पैसा drawing power से मिलता है।",
        "Example: stock साठ लाख, debtors चालीस लाख, creditors तीस लाख।",
        "बचा सत्तर लाख। पच्चीस percent margin काटो।",
        "Drawing power साढ़े बावन लाख। Limit पचहत्तर लाख होने पर भी।",
    ],
    "N08": [
        "Bank file reject क्यों करता है? पाँच reason.",
        "एक: पुरानी EMI ज़्यादा।",
        "दो: ITR में कमाई कम।",
        "तीन: cheque या EMI bounce.",
        "चार: property के काग़ज़ अधूरे।",
        "पाँच: छुपाया हुआ loan. यह सबसे बड़ा।",
    ],
    "N11": [
        "Profit है। फिर भी bank बोले capacity कम?",
        "Bank एक simple नाप देखता है।",
        "साल में loan चुकाने के लिए कितना cash बचा, और कितना चुकाना है।",
        "Example: cash तीस लाख, चुकाना पच्चीस लाख। नाप आया एक point दो।",
        "कई lender इससे ज़्यादा cushion माँगते हैं।",
    ],
    "N12": [
        "नया project. CMA या DPR?",
        "DPR बताता है project क्या है, कितने का है, पैसा कैसे वापस आएगा।",
        "CMA बताता है business के numbers: पिछले साल और आने वाले साल।",
        "नए project के लिए ज़्यादातर lender दोनों माँगते हैं।",
        "पहले DPR, फिर उसके numbers से CMA.",
    ],
}
FPS_TOLERANCE = 1 / 30 + 0.001
MAX_BYTES = 8_000_000
FPS = 30
APPROVED_SOURCE_HASHES = {
    "batch_nov16_29/batch.json": "007be784abf98ef9f479528e34b08bc3bc47af9986154aa615ba462ff648eb33",
    "batch_nov16_29/BRIEF_SOURCE.txt": "b77cce8c4d9cd35124354d0317f1221165c0cfede329ea9872cd2fb947f111b5",
}
# Explicit user-requested display arrangements. Canonical source remains intact.
DISPLAY_LAYOUTS = {
    ("N02", 4): "Bank 3 cheezein dekhta hai:\n1. Kamai aur ITR (income tax return)\n2. Purani EMIs\n3. Property ke kagaz aur title",
    ("N06", 4): "Par total byaaj:\nPersonal loan ₹13,77,250\nLAP ₹31,37,623\nKam EMI ka matlab sasta loan nahi.",
}
REQUESTED_FONT_STEPS = (84, 80, 76, 72)
REQUESTED_SAFE_BOX = (88, 250, 992, 1120)


def requested_paragraphs(item):
    texts = DISPLAY_LAYOUTS[(item, 4)].splitlines()
    roles = ["heading", "numbered_item", "numbered_item", "numbered_item"] if item == "N02" else ["heading", "total_item", "total_item", "closing"]
    return [{"text": text, "kind": role, "prefix": re.match(r"^\d+\.\s+", text).group() if role == "numbered_item" else ""} for text, role in zip(texts, roles)]


def independent_requested_layout(root, item, size, scale):
    """Predict wrapping and occupied ink using the user-authorized fixed policy."""
    face = ImageFont.truetype(str(root / "brand/03_Fonts/Manrope-Extrabold.ttf"), round(size * scale))
    draw = ImageDraw.Draw(Image.new("L", (1, 1)))
    left, top, right, bottom = REQUESTED_SAFE_BOX
    leading, baseline = round(size * 1.18), 0
    groups, measured = [], []
    for paragraph in requested_paragraphs(item):
        continuation_x = left + draw.textlength(paragraph["prefix"], font=face) / scale
        lines, current, x = [], "", left
        for token in paragraph["text"].split():
            proposed = (current + " " + token).strip()
            if current and draw.textlength(proposed, font=face) / scale > right - x:
                lines.append(current)
                current, x = token, continuation_x
            else:
                current = proposed
        if current:
            lines.append(current)
        records = []
        for index, line in enumerate(lines):
            x = left if index == 0 else continuation_x
            box = [value / scale for value in draw.textbbox((round(x * scale), round(baseline * scale)), line, font=face, anchor="ls")]
            measured.append(box)
            records.append({"text": line, "x": x, "baseline": baseline})
            baseline += leading
        groups.append({**paragraph, "lines": records, "continuation_x": continuation_x})
        baseline += 36
    ink_top, ink_bottom = min(box[1] for box in measured), max(box[3] for box in measured)
    fits = ink_bottom - ink_top <= bottom - top and all(left <= box[0] < box[2] <= right for box in measured) and all(len(group["lines"]) <= 2 for group in groups)
    return {"size": size, "groups": groups, "fits": fits, "ink_height": ink_bottom - ink_top, "ink_top": ink_top, "ink_bottom": ink_bottom, "leading": leading}


def numeric_core_color(root, image, word, line, scale):
    """Measure actual JPEG pixels inside independently rendered glyph cores."""
    left, top, right, bottom = word["bounds"]
    crop = (math.floor(left), math.floor(top), math.ceil(right), math.ceil(bottom))
    width, height = crop[2] - crop[0], crop[3] - crop[1]
    face = ImageFont.truetype(str(root / "brand/03_Fonts/Manrope-Extrabold.ttf"), round(line["font_size"] * scale))
    mask = Image.new("L", (round(width * scale), round(height * scale)))
    origin = (word["pixel_origin"][0] - round(crop[0] * scale), word["pixel_origin"][1] - round(crop[1] * scale))
    ImageDraw.Draw(mask).text(origin, word["text"], font=face, fill=255, anchor="ls")
    core = mask.resize((width, height), Image.Resampling.LANCZOS).point(lambda value: 255 if value >= 250 else 0)
    if core.histogram()[255] == 0:
        raise ValueError(f"No solid glyph-core pixels for {word['text']!r}")
    return ImageStat.Stat(image.crop(crop).convert("RGB"), mask=core).mean


def check_requested_wrapped_layout(audit, root, element, item, scale, image_path=None):
    label = "slide4.requested_layout"
    policy = element.get("layout_policy", {})
    expected_policy = {"safe_box": list(REQUESTED_SAFE_BOX), "font_steps": list(REQUESTED_FONT_STEPS), "line_height_factor": 1.18, "group_gap": 36}
    audit.check(f"{label}.fixed_safe_area_and_policy", all(policy.get(key) == value for key, value in expected_policy.items()), policy, item)
    lines = element.get("lines", [])
    sizes = [line.get("font_size") for line in lines]
    uniform = bool(sizes) and len(set(sizes)) == 1 and sizes[0] in REQUESTED_FONT_STEPS and element.get("font_size") == sizes[0]
    audit.check(f"{label}.uniform_84_80_76_72_font", uniform, sizes, item)
    candidates = [independent_requested_layout(root, item, size, scale) for size in REQUESTED_FONT_STEPS]
    fitting = [candidate for candidate in candidates if candidate["fits"]]
    selected = fitting[0] if fitting else None
    audit.check(f"{label}.largest_fitting_font", selected is not None and uniform and sizes[0] == selected["size"], {"selected": sizes[0] if sizes else None, "candidates": [{"font_size": candidate["size"], "fits": candidate["fits"], "ink_height": candidate["ink_height"]} for candidate in candidates]}, item)
    groups = element.get("groups", [])
    paragraphs = requested_paragraphs(item)
    audit.check(f"{label}.separate_exact_semantic_groups", isinstance(groups, list) and [group.get("text") for group in groups] == [paragraph["text"] for paragraph in paragraphs], item=item)
    if selected is None or not isinstance(groups, list) or len(groups) != len(paragraphs):
        return
    group_errors, origin_errors, numeric_errors, color_errors = [], [], [], []
    all_indices, previous_group_last = [], None
    actual_baselines, predicted_baselines = [], []
    image = Image.open(image_path).convert("RGB") if image_path is not None else None
    for index, (group, predicted) in enumerate(zip(groups, selected["groups"])):
        indices = group.get("line_indices", [])
        all_indices.extend(indices)
        group_lines = [lines[line_index] for line_index in indices if isinstance(line_index, int) and 0 <= line_index < len(lines)]
        expected_texts = [line["text"] for line in predicted["lines"]]
        valid = group.get("index") == index and group.get("kind") == predicted["kind"] and group.get("prefix") == predicted["prefix"] and [line.get("text") for line in group_lines] == expected_texts
        valid = valid and indices == list(range(indices[0], indices[0] + len(indices))) if indices else False
        for field, expected_x in (("first_line_x", REQUESTED_SAFE_BOX[0]), ("text_start_x", predicted["continuation_x"]), ("continuation_x", predicted["continuation_x"])):
            if not isinstance(group.get(field), (int, float)) or abs(group[field] - expected_x) > 0.51:
                origin_errors.append({"group": index, "field": field, "actual": group.get(field), "expected": expected_x})
        if not valid:
            group_errors.append({"group": index, "actual_indices": indices, "actual_lines": [line.get("text") for line in group_lines], "expected": expected_texts})
        for row, (line, expected_line) in enumerate(zip(group_lines, predicted["lines"])):
            origin = line.get("draw_origin", [])
            expected_x = expected_line["x"]
            valid_origin = len(origin) == 2 and abs(origin[0] - expected_x) <= 0.51 and line.get("paragraph_index") == index and line.get("group_role") == predicted["kind"] and line.get("is_continuation") is (row > 0)
            if not valid_origin:
                origin_errors.append({"group": index, "row": row, "origin": origin, "expected_x": expected_x})
            actual_baselines.append(line.get("baseline_y", float("nan")))
            predicted_baselines.append(expected_line["baseline"])
            if row == 0 and previous_group_last is not None and line.get("baseline_y", 0) <= previous_group_last:
                group_errors.append({"group": index, "error": "Semantic item did not start on a new physical line"})
            for word in line.get("words", []):
                if re.search(r"\d|₹", word.get("text", "")):
                    if str(word.get("fill", "")).lower() != "#b8ff5a":
                        numeric_errors.append({"text": word.get("text"), "fill": word.get("fill")})
                    if image is not None:
                        measured = numeric_core_color(root, image, word, line, scale)
                        if max(abs(value - expected) for value, expected in zip(measured, (184, 255, 90))) > 12:
                            color_errors.append({"text": word.get("text"), "measured_rgb": measured})
        if group_lines:
            previous_group_last = group_lines[-1].get("baseline_y")
    audit.check(f"{label}.each_item_starts_own_group", not group_errors and all_indices == list(range(len(lines))), group_errors or None, item)
    audit.check(f"{label}.hanging_indent_origins", not origin_errors, origin_errors or None, item)
    baseline_offsets = [actual - expected for actual, expected in zip(actual_baselines, predicted_baselines)]
    audit.check(f"{label}.fixed_leading_and_group_spacing", bool(baseline_offsets) and max(baseline_offsets) - min(baseline_offsets) <= 0.51, baseline_offsets, item)
    bounds = element.get("bounds", [])
    safe = REQUESTED_SAFE_BOX
    audit.check(f"{label}.body_ink_inside_safe_area", len(bounds) == 4 and safe[0] <= bounds[0] < bounds[2] <= safe[2] and safe[1] <= bounds[1] < bounds[3] <= safe[3], bounds, item)
    audit.check(f"{label}.numeric_words_lime", not numeric_errors, numeric_errors or None, item)
    if image is not None:
        audit.check(f"{label}.actual_numeric_glyph_pixels_lime", not color_errors, color_errors or None, item)


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


def expected_original_queue(baseline):
    expected = copy.deepcopy(baseline)
    for item in expected:
        if item.get("id") in AUTHORIZED_HOLD_IDS:
            item["status"] = "hold"
    return expected


def check_protected_originals(audit, baseline, queue):
    """Permit only the 15 explicitly authorized status changes, not object edits."""
    expected = expected_original_queue(baseline)
    prefix = queue[:len(baseline)]
    audit.check("queue.original_count_and_order_preserved", len(prefix) == len(baseline) and [item.get("id") for item in prefix] == [item.get("id") for item in baseline], {"original_count": len(baseline), "current_prefix_count": len(prefix)})
    audit.check("queue.original_objects_only_authorized_holds", prefix == expected, {"allowed_status_changes": list(AUTHORIZED_HOLD_IDS)})
    actual_changes = []
    for before, after in zip(baseline, prefix):
        if before != after:
            fields = sorted(key for key in before.keys() | after.keys() if (key in before) != (key in after) or before.get(key) != after.get(key))
            actual_changes.append({"id": before.get("id"), "fields": fields, "status": after.get("status")})
    audit.check("queue.exactly_15_original_hold_changes", len(actual_changes) == len(AUTHORIZED_HOLD_IDS) and {change["id"] for change in actual_changes} == set(AUTHORIZED_HOLD_IDS) and all(change["fields"] == ["status"] and change["status"] == "hold" for change in actual_changes), actual_changes)
    for ident in AUTHORIZED_HOLD_IDS:
        prior = [item for item in baseline if item.get("id") == ident]
        current = [item for item in queue if item.get("id") == ident]
        if not audit.check("hold.original_and_current_exist_exactly_once", len(prior) == len(current) == 1, {"original": len(prior), "current": len(current)}, ident):
            continue
        audit.check("hold.status_is_hold", current[0].get("status") == "hold", current[0].get("status"), ident)
        exact = copy.deepcopy(prior[0])
        exact["status"] = "hold"
        changed_fields = sorted(key for key in exact.keys() | current[0].keys() if (key in exact) != (key in current[0]) or exact.get(key) != current[0].get(key))
        audit.check("hold.all_other_fields_preserved", current[0] == exact, {"unexpected_changed_fields": changed_fields}, ident)


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


def check_line_baselines(audit, root, element, label, item, scale):
    """Check actual recorded draw origins against independent Pillow metrics.

    A common ink-top is not a baseline: words containing descenders have
    different top offsets. Recomputing every word bbox with anchor='ls' catches
    that old failure even if a manifest merely claims a shared baseline.
    """
    draw = ImageDraw.Draw(Image.new("L", (1, 1)))
    for index, line in enumerate(element.get("lines", [])):
        key = f"{label}.line{index}"
        if not isinstance(line, dict):
            audit.error(f"{key}.baseline_records", "Line requires recorded word draw origins", item)
            continue
        baseline, words = line.get("baseline_y"), line.get("words")
        valid = isinstance(baseline, (int, float)) and math.isfinite(baseline) and isinstance(words, list) and bool(words)
        if not audit.check(f"{key}.baseline_records", valid, item=item):
            continue
        size, weight = line.get("font_size", element.get("font_size")), line.get("weight", element.get("weight"))
        expected_font = f"brand/03_Fonts/Manrope-{weight}.ttf"
        try:
            face = ImageFont.truetype(str(root / expected_font), round(size * scale))
        except Exception as exc:
            audit.error(f"{key}.independent_font_metrics", str(exc), item)
            continue
        ascent, descent = face.getmetrics()
        metrics = line.get("font_metrics", {})
        audit.check(f"{key}.independent_font_metrics", line.get("font_path") == expected_font and metrics.get("ascent") == ascent / scale and metrics.get("descent") == descent / scale, {"font": expected_font, "ascent": ascent / scale, "descent": descent / scale}, item)
        line_origin, pixel_origin = line.get("draw_origin"), line.get("pixel_origin")
        audit.check(f"{key}.baseline_draw_origin", line.get("anchor") == "ls" and isinstance(line_origin, list) and len(line_origin) == 2 and abs(line_origin[1] - baseline) <= 0.011 and pixel_origin == [round(value * scale) for value in line_origin], item=item)
        audit.check(f"{key}.words_preserve_line", wrapped_equal(" ".join(word.get("text", "") for word in words), line.get("text", "")), item=item)
        baseline_errors, metric_errors = [], []
        measured_boxes = []
        for word in words:
            origin = word.get("draw_origin")
            correct = isinstance(origin, list) and len(origin) == 2 and all(isinstance(v, (int, float)) and math.isfinite(v) for v in origin)
            correct = correct and word.get("anchor") == "ls" and all(isinstance(word.get(field), (int, float)) and abs(word[field] - baseline) <= 0.011 for field in ("baseline_y", "line_baseline_y"))
            correct = correct and abs(origin[1] - baseline) <= 0.011
            correct = correct and word.get("pixel_origin") == [round(value * scale) for value in origin] and word.get("baseline_px") == round(baseline * scale)
            if not correct:
                baseline_errors.append(word)
            if isinstance(origin, list) and len(origin) == 2:
                measured = [value / scale for value in draw.textbbox((round(origin[0] * scale), round(origin[1] * scale)), word.get("text", ""), font=face, anchor="ls")]
                measured_boxes.append(measured)
                bounds = word.get("bounds")
                if not isinstance(bounds, list) or len(bounds) != 4 or any(abs(actual - recorded) > 0.011 for actual, recorded in zip(measured, bounds)):
                    metric_errors.append({"text": word.get("text"), "recorded": bounds, "independently_measured": measured})
        audit.check(f"{key}.all_words_on_line_baseline", not baseline_errors, baseline_errors or None, item)
        audit.check(f"{key}.word_bounds_match_font_metrics", not metric_errors and len(measured_boxes) == len(words), metric_errors or None, item)
        if measured_boxes:
            union = [min(box[0] for box in measured_boxes), min(box[1] for box in measured_boxes), max(box[2] for box in measured_boxes), max(box[3] for box in measured_boxes)]
            actual = line.get("bounds", [])
            audit.check(f"{key}.line_bounds_match_drawn_words", len(actual) == 4 and all(abs(a - b) <= 0.011 for a, b in zip(actual, union)), {"recorded": actual, "measured_union": union}, item)


def check_elements(audit, elements, expected, canvas, label, item, safe_y=None, *, root=None, scale=1, body_display=None):
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
            display = body_display if role == "body" and body_display is not None else element.get("text", "")
            audit.check(f"{key}.display_text_authorized", wrapped_equal(element.get("display_text", element.get("text", "")), display), item=item)
            audit.check(f"{key}.wrapped_lines_preserve_copy", wrapped_equal(joined, display), {"joined": joined}, item)
            if role == "body" and body_display is not None:
                if root is not None:
                    check_requested_wrapped_layout(audit, root, element, item, scale, root / "media" / item / "04.jpg")
            for line_index, line in enumerate(lines):
                if isinstance(line, dict):
                    check_box(audit, line.get("bounds", line.get("box")), canvas, f"{key}.line{line_index}", item, safe_y)
            if root is not None:
                check_line_baselines(audit, root, element, key, item, scale)


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


def timing_plan(config, item):
    """Derive expected timing solely from the editable duration configuration."""
    specification = config["reels"][item["id"]]
    durations = specification["scene_durations"]
    if len(durations) != len(item["voice_lines"]):
        raise ValueError("scene_durations must have one duration per exact voice line")
    hook_duration = specification.get("hook_duration", config.get("hook_duration", 0.8))
    end_duration = config.get("end_card_duration", 1.5)
    values = [hook_duration, end_duration, *durations]
    if not all(type(value) in (int, float) and math.isfinite(value) and value > 0 for value in values):
        raise ValueError("All configured durations must be finite positive seconds")
    if end_duration != 1.5:
        raise ValueError("The end card must remain exactly 1.5 seconds")
    hook_frames, end_frames = round(hook_duration * FPS), round(end_duration * FPS)
    scene_frames = [round(duration * FPS) for duration in durations]
    if min(hook_frames, end_frames, *scene_frames) < 1:
        raise ValueError("Every hook, scene and end card must last at least one frame")
    cursor = hook_frames
    scenes = []
    for frames, text in zip(scene_frames, item["voice_lines"]):
        scenes.append({"start": round(cursor / FPS, 6), "end": round((cursor + frames) / FPS, 6), "text": text})
        cursor += frames
    total_frames = cursor + end_frames
    if total_frames > 90 * FPS:
        raise ValueError("Configured reel exceeds the repository's 90-second maximum")
    signed_config = {"hook_frames": hook_frames, "scene_frames": scene_frames, "end_card_frames": end_frames, "voice_lines": item["voice_lines"]}
    signature = hashlib.sha256(json.dumps(signed_config, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()
    return {"hook_frames": hook_frames, "scene_frames": scene_frames, "end_card_frames": end_frames, "total_frames": total_frames, "duration": total_frames / FPS, "end_card_start": cursor / FPS, "voice_scenes": scenes, "config_sha256": signature}


def scene_text_timeline(scenes):
    if not isinstance(scenes, list) or not all(isinstance(scene, dict) for scene in scenes):
        return None
    return [{key: scene.get(key) for key in ("start", "end", "text")} for scene in scenes]


def check_pronunciation(audit, queued, item):
    expected = CANONICAL_SAY[item]
    scenes = queued.get("voice_scenes", [])
    actual = [scene.get("say") for scene in scenes] if isinstance(scenes, list) and all(isinstance(scene, dict) for scene in scenes) else None
    # Python string equality deliberately preserves punctuation, spacing and
    # composed/decomposed nukta code points exactly as supplied by the owner.
    audit.check("voice_scenes.exact_owner_say_lines", actual == expected, {"actual_count": len(actual) if actual is not None else None, "expected_count": len(expected), "mismatched_indices": [index for index, (have, need) in enumerate(zip(actual or [], expected)) if have != need]}, item)
    audit.check("voice.exact_language", queued.get("voice_lang") == "hi-IN", queued.get("voice_lang"), item)
    audit.check("voice.exact_model", queued.get("voice_model") == "bulbul:v3", queued.get("voice_model"), item)


def check_configured_timing(audit, actual_scenes, actual_duration, plan, item):
    audit.check("voice_scenes.exact_configured_timing", scene_text_timeline(actual_scenes) == plan["voice_scenes"], item=item)
    if actual_duration is not None:
        audit.check("reel.actual_duration_matches_configuration", abs(actual_duration - plan["duration"]) <= 0.01, {"actual": actual_duration, "configured": plan["duration"]}, item)


def check_voice_scenes(audit, actual, canonical, item, speech_end):
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


def check_video(audit, root, path, item, ffprobe, plan):
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
            if plan:
                audit.check("reel.actual_frame_count_matches_configuration", str(stream.get("nb_frames")) == str(plan["total_frames"]), {"actual": stream.get("nb_frames"), "configured": plan["total_frames"]}, item)
        duration = float(probe["format"]["duration"])
        audit.check("reel.duration_within_repository_limit", 0 < duration <= 90.001, duration, item)
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
    scale = manifest.get("supersampling")
    if not audit.check("carousel_manifest.valid_render_scale", isinstance(scale, (int, float)) and scale > 0, scale):
        scale = 1
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
            display = DISPLAY_LAYOUTS.get((ident, number))
            if display is not None:
                audit.check(f"{label}.requested_display_text", actual.get("display_body") == display, item=ident)
            elif "display_text" in actual:
                audit.check(f"{label}.no_unapproved_display_rewrite", wrapped_equal(actual["display_text"], slide["text"]), item=ident)
            override = actual.get("display_override")
            if (ident, number) == ("N06", 4):
                audit.check(f"{label}.explicit_user_display_override", isinstance(override, dict) and override.get("requested_by_user") is True and override.get("canonical_text") == slide["text"] and override.get("display_text") == display, override, ident)
            elif override:
                audit.check(f"{label}.only_authorized_display_override", (ident, number) == ("N02", 4) and isinstance(override, dict) and override.get("canonical_text") == slide["text"] and override.get("display_text") == display, override, ident)
            check_elements(audit, actual.get("elements"), expected, (1080, 1350), label, ident, root=root, scale=scale, body_display=display)


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


def check_reel_manifest(audit, root, item, queued, canonical, registry, plan):
    ident = item["id"]
    manifest = load_manifest(audit, root / "reels_nov2026/manifests" / f"{ident}.json", f"{ident}.render_manifest")
    if not manifest:
        return
    for field in ("hook", "series", "cta", "number_card"):
        audit.check(f"reel_manifest.exact_{field}", manifest.get(field) == item.get(field), item=ident)
    audit.check("reel_manifest.exact_disclaimer", manifest.get("disclaimer") == canonical["disclaimer"], item=ident)
    output = manifest.get("output", {})
    expected_output = {"width": 1080, "height": 1920, "fps": FPS, "audio": False, "safe_zone": [250, 1500], "caption_baseline": 1260, "cover_frame_seconds": 0}
    if plan:
        expected_output.update(duration=plan["duration"], hook_duration=plan["hook_frames"] / FPS, end_card_duration=plan["end_card_frames"] / FPS, end_card_start=plan["end_card_start"], total_frames=plan["total_frames"], timing_config_sha256=plan["config_sha256"])
    for field, expected in expected_output.items():
        audit.check(f"reel_manifest.output.{field}", field in output and output[field] == expected, output.get(field), ident)
    cover_expected = {"hook": item["hook"], "series_tag": item["series"], "website": "crednest.io"}
    check_reel_boxes(audit, manifest.get("cover_boxes"), cover_expected, "reel_cover", ident)
    scenes = manifest.get("voice_scenes", [])
    stripped = [{key: scene.get(key) for key in ("start", "end", "text")} for scene in scenes]
    audit.check("reel_manifest.voice_matches_queue", stripped == scene_text_timeline(queued.get("voice_scenes")), item=ident)
    audit.check("reel_manifest.voice_matches_canonical", [scene.get("text") for scene in scenes] == item["voice_lines"], item=ident)
    if plan:
        audit.check("reel_manifest.voice_matches_configuration", stripped == plan["voice_scenes"], item=ident)
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
            audit.check("reel.hook_on_first_frame", start == 0 and state.get("text") == item["hook"] and (not plan or end == plan["hook_frames"]), item=ident)
        elif kind == "end_card":
            expected = {"cta": item["cta"], "website": "crednest.io", "disclaimer": canonical["disclaimer"]}
            audit.check("reel.end_card_last_1_5s", plan is not None and start == plan["total_frames"] - plan["end_card_frames"] and end == plan["total_frames"] and state.get("text") == item["cta"], item=ident)
        elif kind == "voice":
            expected = {"series_tag": item["series"], "voice_caption": state.get("text", "")}
            if any(box.get("label") == "number_card" for box in state.get("boxes", [])):
                expected["number_card"] = item.get("number_card")
                number_card_seen = True
        else:
            expected = {}
        check_reel_boxes(audit, state.get("boxes"), expected, f"reel_state{index}", ident)
    audit.check("reel_manifest.no_frame_gaps_or_overlaps", plan is not None and not interval_errors and previous_end == plan["total_frames"], interval_errors or {"final_frame": previous_end}, ident)
    audit.check("reel_manifest.numeric_card_rendered_when_required", number_card_seen == bool(item.get("number_card")), item=ident)
    assets = {asset.get("name"): asset for asset in registry.get("assets", [])}
    broll_errors = []
    for segment in manifest.get("broll", []):
        asset = assets.get(segment.get("name"))
        if not asset or segment.get("source_id") != asset.get("id") or segment.get("page_url") != asset.get("page_url"):
            broll_errors.append(segment)
    audit.check("reel_manifest.licensed_broll_registry_matches", bool(manifest.get("broll")) and not broll_errors, broll_errors or None, ident)


def regression_controls(root, carousel_manifest, config, canonical, baseline):
    """Exercise typography and retiming failure cases without changing files."""
    controls = []
    sample = next(element for slide in carousel_manifest["slides"] for element in slide["elements"] if element.get("role") == "body" and element.get("lines") and len(element["lines"][0].get("words", [])) > 1)
    scale = carousel_manifest["supersampling"]
    positive = Audit()
    check_line_baselines(positive, root, sample, "baseline_control", "test", scale)
    controls.append({"scenario": "actual_baseline_metadata_passes_independent_font_metrics", "passed": all(check["passed"] for check in positive.checks)})
    floated = copy.deepcopy(sample)
    word = floated["lines"][0]["words"][-1]
    word["draw_origin"][1] -= 4
    word["pixel_origin"][1] -= round(4 * scale)
    negative = Audit()
    check_line_baselines(negative, root, floated, "floated_word", "test", scale)
    controls.append({"scenario": "word_draw_origin_offset_is_rejected", "passed": any(not check["passed"] and check["check"].endswith("all_words_on_line_baseline") for check in negative.checks)})
    legacy = copy.deepcopy(sample)
    line = legacy["lines"][0]
    word = line["words"][0]
    weight, size = line.get("weight", legacy["weight"]), line.get("font_size", legacy["font_size"])
    face = ImageFont.truetype(str(root / "brand/03_Fonts" / f"Manrope-{weight}.ttf"), round(size * scale))
    draw = ImageDraw.Draw(Image.new("L", (1, 1)))
    # The prior renderer aligned each token by its ink top. These independently
    # generated lt bounds cannot masquerade as baseline-aligned ls glyph bounds.
    word["bounds"] = [value / scale for value in draw.textbbox(tuple(word["pixel_origin"]), word["text"], font=face, anchor="lt")]
    negative = Audit()
    check_line_baselines(negative, root, legacy, "legacy_ink_top", "test", scale)
    controls.append({"scenario": "old_ink_top_anchor_bounds_are_rejected", "passed": any(not check["passed"] and check["check"].endswith("word_bounds_match_font_metrics") for check in negative.checks)})
    item = next(item for item in canonical["items"] if item["type"] == "reel")
    plan = timing_plan(config, item)
    negative = Audit()
    check_configured_timing(negative, plan["voice_scenes"], plan["duration"] - 1 / FPS, plan, "test")
    controls.append({"scenario": "encoded_duration_one_frame_short_is_rejected", "passed": any(not check["passed"] and check["check"] == "reel.actual_duration_matches_configuration" for check in negative.checks)})
    retimed = copy.deepcopy(config)
    retimed["reels"][item["id"]]["scene_durations"][0] += 0.8
    new_plan = timing_plan(retimed, item)
    negative = Audit()
    check_configured_timing(negative, plan["voice_scenes"], plan["duration"], new_plan, "test")
    controls.append({"scenario": "edited_config_rejects_stale_queue_and_render_duration", "passed": all(not check["passed"] for check in negative.checks) and new_plan["config_sha256"] != plan["config_sha256"]})
    positive = Audit()
    check_configured_timing(positive, new_plan["voice_scenes"], new_plan["duration"], new_plan, "test")
    controls.append({"scenario": "freshly_retimed_scenes_and_duration_pass_without_code_changes", "passed": all(check["passed"] for check in positive.checks)})
    special = next(slide for slide in carousel_manifest["slides"] if (slide["id"], slide["slide"]) == ("N02", 4))
    body = next(element for element in special["elements"] if element["role"] == "body")
    mutations = []
    for size, scenario, target in ((68, "below_72px_requested_body_is_rejected", "uniform_84_80_76_72_font"), (72, "unnecessary_downsizing_when_84px_fits_is_rejected", "largest_fitting_font")):
        bad = copy.deepcopy(body)
        bad["font_size"] = size
        for line in bad["lines"]:
            line["font_size"] = size
        mutations.append((bad, scenario, target))
    bad = copy.deepcopy(body)
    bad["lines"][0]["font_size"] = 80
    mutations.append((bad, "inconsistent_heading_and_item_font_is_rejected", "uniform_84_80_76_72_font"))
    bad = copy.deepcopy(body)
    continuation = next(line for line in bad["lines"] if line["is_continuation"] and line["group_role"] == "numbered_item")
    continuation["draw_origin"][0] = REQUESTED_SAFE_BOX[0]
    mutations.append((bad, "continuation_aligned_under_number_is_rejected", "hanging_indent_origins"))
    bad = copy.deepcopy(body)
    bad["groups"][1]["text"] += " " + bad["groups"][2]["text"]
    del bad["groups"][2]
    mutations.append((bad, "combined_numbered_items_are_rejected", "separate_exact_semantic_groups"))
    bad = copy.deepcopy(body)
    numeric = next(word for line in bad["lines"] for word in line["words"] if re.search(r"\d|₹", word["text"]))
    numeric["fill"] = "#F8F8F4"
    mutations.append((bad, "non_lime_numeric_fill_is_rejected", "numeric_words_lime"))
    for bad, scenario, target in mutations:
        negative = Audit()
        check_requested_wrapped_layout(negative, root, bad, "N02", scale)
        controls.append({"scenario": scenario, "passed": any(not check["passed"] and check["check"].endswith(target) for check in negative.checks)})
    permitted = expected_original_queue(baseline)
    positive = Audit()
    check_protected_originals(positive, baseline, permitted)
    controls.append({"scenario": "exactly_authorized_15_hold_status_changes_pass", "passed": all(check["passed"] for check in positive.checks)})
    first_held = AUTHORIZED_HOLD_IDS[0]
    mutations = []
    bad = copy.deepcopy(permitted)
    next(item for item in bad if item["id"] == first_held)["status"] = "ready"
    mutations.append((bad, "reverted_ready_status_on_held_item_is_rejected", "hold.status_is_hold"))
    bad = copy.deepcopy(permitted)
    next(item for item in bad if item["id"] not in AUTHORIZED_HOLD_IDS)["status"] = "hold"
    mutations.append((bad, "unauthorized_sixteenth_hold_is_rejected", "queue.exactly_15_original_hold_changes"))
    bad = copy.deepcopy(permitted)
    held = next(item for item in bad if item["id"] == first_held)
    held["caption"] = held.get("caption", "") + " Unauthorized edit."
    mutations.append((bad, "held_item_caption_edit_is_rejected", "hold.all_other_fields_preserved"))
    bad = [copy.deepcopy(item) for item in permitted if item["id"] != first_held]
    mutations.append((bad, "held_item_deletion_is_rejected", "hold.original_and_current_exist_exactly_once"))
    for bad, scenario, target in mutations:
        negative = Audit()
        check_protected_originals(negative, baseline, bad)
        controls.append({"scenario": scenario, "passed": any(not check["passed"] and check["check"] == target for check in negative.checks)})
    ident = "N01"
    pronunciation = {"voice_lang": "hi-IN", "voice_model": "bulbul:v3", "voice_scenes": [{"say": line} for line in CANONICAL_SAY[ident]]}
    positive = Audit()
    check_pronunciation(positive, pronunciation, ident)
    controls.append({"scenario": "exact_owner_unicode_say_and_voice_settings_pass", "passed": all(check["passed"] for check in positive.checks)})
    mutations = []
    bad = copy.deepcopy(pronunciation)
    bad["voice_scenes"][0]["say"] += "."
    mutations.append((bad, "altered_say_punctuation_is_rejected", "voice_scenes.exact_owner_say_lines"))
    bad = copy.deepcopy(pronunciation)
    del bad["voice_scenes"][0]["say"]
    mutations.append((bad, "missing_scene_say_is_rejected", "voice_scenes.exact_owner_say_lines"))
    bad = copy.deepcopy(pronunciation)
    bad["voice_scenes"][0]["say"], bad["voice_scenes"][1]["say"] = bad["voice_scenes"][1]["say"], bad["voice_scenes"][0]["say"]
    mutations.append((bad, "swapped_say_scene_order_is_rejected", "voice_scenes.exact_owner_say_lines"))
    bad = copy.deepcopy(pronunciation)
    bad["voice_model"] = "bulbul:v2"
    mutations.append((bad, "wrong_voice_model_is_rejected", "voice.exact_model"))
    bad = copy.deepcopy(pronunciation)
    bad["voice_lang"] = "en-IN"
    mutations.append((bad, "wrong_voice_language_is_rejected", "voice.exact_language"))
    bad = copy.deepcopy(pronunciation)
    for scene in bad["voice_scenes"]:
        if "\u091c\u093c" in scene["say"]:
            scene["say"] = scene["say"].replace("\u091c\u093c", "\u095b", 1)
            break
    else:
        raise AssertionError("The pronunciation fixture must contain the owner's exact decomposed nukta sequence")
    mutations.append((bad, "visually_equivalent_nukta_codepoint_change_is_rejected", "voice_scenes.exact_owner_say_lines"))
    for bad, scenario, target in mutations:
        negative = Audit()
        check_pronunciation(negative, bad, ident)
        controls.append({"scenario": scenario, "passed": any(not check["passed"] and check["check"] == target for check in negative.checks)})
    return controls


def main():
    # Validation failures can contain the exact supplied rupee figures.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--base", help="Protected base revision; defaults to batch.json base_revision, then HEAD")
    parser.add_argument("--ffprobe", help="ffprobe executable; auto-detects Jellyfin on Windows")
    parser.add_argument("--ffmpeg", help="ffmpeg executable for actual first-frame/cover comparison and motion check")
    parser.add_argument("--timings", type=Path, default=Path("reels_nov2026/timings.json"), help="Editable per-scene duration configuration")
    parser.add_argument("--self-test", action="store_true", help="Run in-memory baseline/duration/retiming regression controls only")
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
    timings_path = args.timings if args.timings.is_absolute() else root / args.timings
    config = load_manifest(audit, timings_path, "timing_configuration")
    expected_reel_ids = {item["id"] for item in expected_items if item["type"] == "reel"}
    audit.check("pronunciation.canonical_exact_reel_ids", set(CANONICAL_SAY) == expected_reel_ids)
    audit.check("timing_configuration.exact_reels", set(config.get("reels", {})) == expected_reel_ids)
    audit.check("timing_configuration.version", config.get("version") == 1)
    plans = {}
    for item in expected_items:
        if item["type"] != "reel":
            continue
        try:
            plans[item["id"]] = timing_plan(config, item)
            audit.check("timing_configuration.valid_scene_durations", True, {"duration": plans[item["id"]]["duration"], "scene_frames": plans[item["id"]]["scene_frames"]}, item["id"])
        except Exception as exc:
            audit.error("timing_configuration.valid_scene_durations", str(exc), item["id"])
    if args.self_test:
        controls = regression_controls(root, read_json(root / "reports/nov16-29/carousel-render-manifest.json"), config, canonical, baseline)
        for control in controls:
            print(("PASS " if control["passed"] else "FAIL ") + control["scenario"])
        return 0 if all(control["passed"] for control in controls) else 1
    for relative, approved_hash in APPROVED_SOURCE_HASHES.items():
        audit.check("approved_source.unchanged", file_hash(root / relative) == approved_hash, relative)
    audit.check("canonical.exact_14_ids_in_order", [item.get("id") for item in expected_items] == IDS)
    audit.check("canonical.confirmed_series", canonical.get("series_pending") is False and len(canonical.get("series_tags", {})) == 4)
    audit.check("canonical.cover_annotations_disabled", canonical.get("cover_annotations") is False)
    audit.check("user_clarifications.present", (root / "batch_nov16_29/USER_CLARIFICATIONS.md").is_file())
    counts = Counter(item.get("id") for item in queue)
    audit.check("queue.unique_ids", all(count == 1 for count in counts.values()))
    check_protected_originals(audit, baseline, queue)
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
            check_pronunciation(audit, actual, ident)
            audit.check("queue.exact_reel_path", actual.get("media") == [relative], actual.get("media"), ident)
            audit.check("queue.exact_cover_path", actual.get("cover") == cover, actual.get("cover"), ident)
            plan = plans.get(ident)
            duration = check_video(audit, root, safe_path(root, relative), ident, ffprobe, plan)
            check_jpeg(audit, safe_path(root, cover), cover, (1080, 1920), ident)
            check_first_frames(audit, safe_path(root, relative), safe_path(root, cover), ident, ffmpeg)
            if plan:
                check_voice_scenes(audit, actual.get("voice_scenes"), item, ident, plan["end_card_start"])
                check_configured_timing(audit, actual.get("voice_scenes"), duration, plan, ident)
    carousel_manifest = load_manifest(audit, root / "reports/nov16-29/carousel-render-manifest.json", "carousel_manifest")
    check_carousel_manifest(audit, root, carousel_manifest, canonical)
    registry = load_manifest(audit, root / "reels_nov2026/stock_sources.json", "reel_stock_registry")
    audit.check("reel_stock_registry.pexels_license_recorded", registry.get("license_url") == "https://www.pexels.com/license/")
    for item in expected_items:
        if item["type"] == "reel" and item["id"] in by_id:
            check_reel_manifest(audit, root, item, by_id[item["id"]], canonical, registry, plans.get(item["id"]))
    try:
        controls = regression_controls(root, carousel_manifest, config, canonical, baseline)
        for control in controls:
            audit.check("regression_control." + control["scenario"], control["passed"])
    except Exception as exc:
        controls = []
        audit.error("regression_controls.completed", str(exc))
    failed = [check for check in audit.checks if not check["passed"]]
    report = {
        "status": "OK" if not failed else "FAILED",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "canonical_sha256": file_hash(canonical_path),
        "timing_configuration_sha256": file_hash(timings_path) if timings_path.is_file() else None,
        "baseline_commit": baseline_commit,
        "authorized_original_hold_ids": list(AUTHORIZED_HOLD_IDS),
        "scope": "14 batch queue slots: 6 carousels, 6 silent reels, 2 reserved; exactly 15 authorized original status-only holds; all other original fields, order and publishing state protected",
        "limits": "Text is checked against renderer manifests and bounds, not OCR. Faceless footage and visual quality require the accompanying human/visual review. Word timing describes silent captions; later voice synthesis still needs listening checks.",
        "summary": {"checks": len(audit.checks), "passed": len(audit.checks) - len(failed), "failed": len(failed)},
        "errors": failed,
        "items": audit.items,
        "regression_controls": controls,
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
