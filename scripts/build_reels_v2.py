#!/usr/bin/env python3
"""Rebuild silent, faceless CredNest reels from licensed stock and storyboards.

Requires Python 3, Pillow, FFmpeg/ffprobe, and a Chromium browser for faithful
rendering of the supplied SVG lockup. Stock originals and all intermediate files
stay in the explicit external --work-dir. Only reel.mp4 and cover.jpg are written
to media/. This script does not edit queue.json or generate any audio.

Example:
    python scripts/build_reels_v2.py --only D06-feed --work-dir /tmp/crednest
    # Place the registry's named stock files in /tmp/crednest/stock first.
"""

from __future__ import annotations

import argparse
import html
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import time

from PIL import Image, ImageCms, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
WIDTH, HEIGHT, FPS = 1080, 1920, 30
PAPER = "#F8F8F4"
LIME = "#B8FF5A"
INK = "#07150F"
GREEN = "#0D2119"
FONT_DIR = ROOT / "brand/03_Fonts"
CLIP_PLANS = {
    "D06-feed": ["packing_box", "document_review", "signing", "warehouse", "packing_smallbusiness", "calculator", "spreadsheet", "signing", "document_review", "spreadsheet"],
    "D12-feed": ["keys", "document_review", "spreadsheet", "calculator", "signing", "floorplans", "blueprints", "document_review", "signing", "keys"],
    "D03-feed": ["packing_box", "signing", "calculator", "warehouse", "packing_smallbusiness", "spreadsheet", "document_review", "signing", "calculator", "spreadsheet"],
    "D14-feed": ["machinery", "calculator", "signing", "machinery", "warehouse", "document_review", "spreadsheet", "signing", "document_review", "machinery"],
    "D17-feed": ["document_review", "signing", "spreadsheet", "calculator", "document_review", "floorplans", "blueprints", "signing", "document_review", "keys"],
    "D29-feed": ["signing", "document_review", "calculator", "warehouse", "spreadsheet", "signing", "document_review", "calculator", "signing", "spreadsheet"],
}


def font(size: int, weight: str = "Extrabold"):
    return ImageFont.truetype(str(FONT_DIR / f"Manrope-{weight}.ttf"), size)


def run(command, log_path: Path, **kwargs):
    with log_path.open("ab") as log:
        subprocess.run(command, check=True, stdout=log, stderr=log, **kwargs)


def ffconcat_path(path: Path) -> str:
    # ffconcat escaping is separate from shell quoting; subprocess never uses a shell.
    return "'" + path.resolve().as_posix().replace("'", "'\\''") + "'"


def find_browser(explicit: str | None) -> str:
    if explicit:
        return explicit
    for name in ["chromium", "chromium-browser", "google-chrome", "msedge", "chrome"]:
        if found := shutil.which(name):
            return found
    if os.name == "nt":
        for env, relative in [("ProgramFiles(x86)", "Microsoft/Edge/Application/msedge.exe"), ("ProgramFiles", "Google/Chrome/Application/chrome.exe")]:
            candidate = Path(os.environ.get(env, "")) / relative
            if candidate.is_file():
                return str(candidate)
    raise SystemExit("A Chromium browser is needed to render the supplied SVG; pass --browser.")


def render_supplied_logo(work_dir: Path, browser: str) -> Image.Image:
    """Render the supplied SVG unchanged, with its bundled font available by CSS."""
    output = work_dir / "supplied_logo.png"
    if output.exists():
        return Image.open(output).convert("RGBA")
    svg = (ROOT / "brand/04_Logos/CredNest_Lockup_Dark.svg").read_text(encoding="utf-8")
    font_uri = (FONT_DIR / "Manrope-Extrabold.ttf").resolve().as_uri()
    page = work_dir / "supplied_logo.html"
    page.write_text(
        '<!doctype html><meta charset="utf-8"><style>'
        f'@font-face{{font-family:Manrope;src:url("{html.escape(font_uri)}");font-weight:800}}'
        'html,body{margin:0;padding:0;width:510px;height:140px;overflow:hidden;background:#0D2119}'
        '</style>' + svg,
        encoding="utf-8",
    )
    run(
        [browser, "--headless", "--disable-gpu", "--disable-extensions", "--no-first-run", "--hide-scrollbars", "--allow-file-access-from-files", "--force-device-scale-factor=1", "--window-size=510,400", f"--user-data-dir={work_dir / 'logo-browser-profile'}", f"--screenshot={output}", page.resolve().as_uri()],
        work_dir / "logo-render.log",
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        timeout=60,
    )
    # Some Chromium builds impose a minimum viewport height. The supplied SVG's
    # viewBox is exactly 510 x 140; trim only the unused page below the artwork.
    logo = Image.open(output).convert("RGBA").crop((0, 0, 510, 140))
    logo.save(output)
    return logo


def wrap_words(text: str, face, max_width: int):
    words = text.split()
    lines, current = [], []
    for index, word in enumerate(words):
        candidate = current + [(index, word)]
        if current and face.getlength(" ".join(w for _, w in candidate)) > max_width:
            lines.append(current)
            current = [(index, word)]
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def tracked_bounds(draw, xy, text, face, fill, bounds, label, anchor="lt", shadow=False):
    box = draw.textbbox(xy, text, font=face, anchor=anchor)
    if box[1] < 250 or box[3] > 1500:
        raise ValueError(f"Unsafe {label} text bounds: {box}")
    if shadow:
        draw.text((xy[0] + 2, xy[1] + 3), text, font=face, fill=(7, 21, 15, 180), anchor=anchor, stroke_width=2, stroke_fill=(7, 21, 15, 120))
    draw.text(xy, text, font=face, fill=fill, anchor=anchor)
    bounds.append({"label": label, "text": text, "box": list(box)})


def caption_image(scene: dict, reel: dict, visible_words: int, logo: Image.Image):
    image = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    bounds = []
    end_card = scene["start"] >= 25
    hook = scene["start"] == 0

    if reel.get("persistent_case_tag"):
        case_font = font(29, "Semibold")
        case_lines = wrap_words(reel["persistent_case_tag"], case_font, 870)
        for i, line in enumerate(case_lines):
            tracked_bounds(draw, (88, 275 + i * 40), " ".join(w for _, w in line), case_font, PAPER, bounds, "case_tag")

    if scene.get("kicker"):
        kicker_font = font(30, "Bold")
        tracked_bounds(draw, (100, 429), scene["kicker"], kicker_font, LIME, bounds, "chapter")
        draw.line((100, 489, 978, 489), fill=(157, 243, 197, 115), width=2)

    if end_card:
        image.alpha_composite(logo, ((WIDTH - logo.width) // 2, 335))
        size, center_y = 84, 740
    elif hook:
        size, center_y = 92, 795
    else:
        size, center_y = 88, 830

    face = font(size)
    lines = wrap_words(scene["text"], face, 880)
    line_height = math.ceil(size * 1.24)
    top = int(center_y - len(lines) * line_height / 2)
    key = scene.get("key_word", "").casefold().strip(".,?!'\"")
    for row, line in enumerate(lines):
        full_line = " ".join(word for _, word in line)
        x = (WIDTH - face.getlength(full_line)) / 2
        y = top + row * line_height
        for index, word in line:
            if index < visible_words:
                color = LIME if word.casefold().strip(".,?!'\"") == key else PAPER
                tracked_bounds(draw, (round(x), y), word, face, color, bounds, "voice_caption", shadow=True)
            x += face.getlength(word + " ")

    if end_card:
        draw.rounded_rectangle((84, 1000, 996, 1168), radius=26, fill=LIME)
        tracked_bounds(draw, (540, 1036), "WhatsApp +91 98199 99057", font(48), INK, bounds, "single_cta", anchor="mt")
        tracked_bounds(draw, (540, 1104), 'MESSAGE “HI”', font(32, "Bold"), INK, bounds, "cta_instruction", anchor="mt")
        tracked_bounds(draw, (540, 1230), "Independent advice. Lender-led decisions.", font(34, "Bold"), PAPER, bounds, "brand_anchor", anchor="mt")
        disclaimer_lines = [
            "CredNest is an advisory firm, not a lender.",
            "Loan approval and terms are at the lender's",
            "sole discretion.",
        ]
        for i, line in enumerate(disclaimer_lines):
            tracked_bounds(draw, (540, 1320 + i * 43), line, font(32, "Medium"), PAPER, bounds, "full_disclaimer", anchor="mt")
        if max(b["box"][3] for b in bounds if b["label"] == "full_disclaimer") > 1450:
            raise ValueError("Disclaimer extends below y=1450")
    return image, bounds


def make_captions(reel: dict, target: Path, logo: Image.Image):
    images_dir = target / "captions"
    images_dir.mkdir(exist_ok=True)
    concat_lines = ["ffconcat version 1.0"]
    manifests = []
    last_file = None
    for scene_index, scene in enumerate(reel["voice_scenes"]):
        start_frame = round(scene["start"] * FPS)
        end_frame = round(scene["end"] * FPS)
        scene_frames = end_frame - start_frame
        count = len(scene["text"].split())
        # The first word is visible immediately, and all words appear by 72% of
        # the scene. Its full layout stays fixed throughout the word reveal.
        reveals = [round(i * scene_frames * 0.72 / max(count - 1, 1)) for i in range(count)]
        states = []
        for i in range(count):
            path = images_dir / f"{scene_index:02}_{i+1:02}.png"
            caption, bounds = caption_image(scene, reel, i + 1, logo)
            caption.save(path, compress_level=3)
            next_frame = reveals[i + 1] if i + 1 < count else scene_frames
            frames = next_frame - reveals[i]
            concat_lines.extend(["file " + ffconcat_path(path), "option framerate 30", f"duration {frames / FPS:.9f}"])
            states.append({"reveal_frame": start_frame + reveals[i], "visible_words": i + 1, "duration_frames": frames, "text_bounds": bounds})
            last_file = path
        manifests.append({"index": scene_index, "start": scene["start"], "end": scene["end"], "text": scene["text"], "keyword": scene.get("key_word"), "states": states})
    # Repeat the final file so concat honors its predecessor's duration.
    concat_lines.extend(["file " + ffconcat_path(last_file), "option framerate 30"])
    concat_path = target / "captions.ffconcat"
    concat_path.write_text("\n".join(concat_lines) + "\n", encoding="utf-8")
    return concat_path, manifests


def build_reel(reel_id: str, storyboard: dict, registry: dict, args, logo):
    started = time.monotonic()
    reel = storyboard["reels"][reel_id]
    external = args.work_dir / "renders" / reel_id
    external.mkdir(parents=True, exist_ok=True)
    destination = ROOT / "media" / reel_id
    destination.mkdir(parents=True, exist_ok=True)
    captions, scene_manifest = make_captions(reel, external, logo)
    asset_by_name = {asset["name"]: asset for asset in registry["assets"]}
    segment_paths = []
    log = external / "ffmpeg.log"
    for index, (scene, clip_name) in enumerate(zip(reel["voice_scenes"], CLIP_PLANS[reel_id])):
        segment_started = time.monotonic()
        clip = asset_by_name[clip_name]
        source = args.work_dir / "stock" / clip["filename"]
        if not source.is_file():
            raise FileNotFoundError(f"Missing licensed source: {source}")
        duration = scene["end"] - scene["start"]
        available = max(0, clip["duration_seconds"] - duration - 0.1)
        offset = min(available, (index * 0.83 + 0.15) % max(available, 0.1))
        segment = external / f"broll_{index:02}.mp4"
        # Crop in source coordinates before scaling, avoiding wasteful 4K-wide
        # intermediate frames. Source action supplies continuous real movement.
        filters = "crop=trunc(ih*9/16/2)*2:ih:(iw-ow)/2:0,scale=1080:1920:flags=lanczos,fps=30,setsar=1,gblur=sigma=0.7,drawbox=x=0:y=0:w=iw:h=ih:color=0x0D2119@0.60:t=fill,format=yuv420p"
        if not segment.exists() or args.force:
            run([args.ffmpeg, "-hide_banner", "-loglevel", "warning", "-y", "-threads", str(args.threads), "-ss", f"{offset:.3f}", "-i", str(source), "-t", str(duration), "-vf", filters, "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-maxrate", "4000k", "-bufsize", "8000k", "-threads", str(args.threads), "-pix_fmt", "yuv420p", "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", str(segment)], log)
        segment_paths.append(segment)
        scene_manifest[index]["stock"] = {"name": clip_name, "id": clip["id"], "url": clip["page_url"], "filename": clip["filename"], "source_offset": round(offset, 3), "source_crop": "center crop to 9:16 before 1080x1920 scale", "deep_green_opacity": 0.60, "source_crop_notes": clip["faceless_crop_notes"]}
        scene_manifest[index]["segment_render_seconds"] = round(time.monotonic() - segment_started, 2)
        print(f"{reel_id}: scene {index + 1}/10 ({clip_name}) prepared", flush=True)

    base_concat = external / "broll.ffconcat"
    base_concat.write_text("ffconcat version 1.0\n" + "\n".join("file " + ffconcat_path(path) for path in segment_paths) + "\n", encoding="utf-8")
    base = external / "broll.mp4"
    run([args.ffmpeg, "-hide_banner", "-loglevel", "warning", "-y", "-f", "concat", "-safe", "0", "-i", str(base_concat), "-an", "-c:v", "copy", str(base)], log)
    output = destination / "reel.mp4"
    # The concat image demuxer may round its final timestamp one frame short.
    # Pad that boundary, then explicitly cap the output at 840 frames / 28 s.
    run([args.ffmpeg, "-hide_banner", "-loglevel", "warning", "-y", "-threads", str(args.threads), "-i", str(base), "-f", "concat", "-safe", "0", "-i", str(captions), "-filter_complex", "[0:v][1:v]overlay=shortest=1:format=auto,tpad=stop_mode=clone:stop_duration=0.1,format=yuv420p[v]", "-map", "[v]", "-an", "-t", "28", "-frames:v", "840", "-r", "30", "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-maxrate", "2000k", "-bufsize", "4000k", "-threads", str(args.threads), "-pix_fmt", "yuv420p", "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", "-movflags", "+faststart", str(output)], log)
    if output.stat().st_size >= 8_000_000:
        raise ValueError(f"Reel exceeds 8 MB: {output.stat().st_size}")
    frame = external / "hook_frame.png"
    run([args.ffmpeg, "-hide_banner", "-loglevel", "warning", "-y", "-ss", "1.8", "-i", str(output), "-frames:v", "1", "-update", "1", str(frame)], log)
    cover = Image.open(frame).convert("RGB")
    srgb = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    cover.save(destination / "cover.jpg", "JPEG", quality=95, subsampling=0, icc_profile=srgb)
    if (destination / "cover.jpg").stat().st_size >= 8_000_000:
        raise ValueError("Cover exceeds 8 MB")
    probe = subprocess.run([args.ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(output)], capture_output=True, text=True, check=True)
    probe_data = json.loads(probe.stdout)
    streams = probe_data["streams"]
    if len(streams) != 1 or streams[0].get("codec_type") != "video":
        raise ValueError("Expected a single video stream and no audio")
    video = streams[0]
    if (video["codec_name"], video["width"], video["height"], video["r_frame_rate"], int(video["nb_frames"])) != ("h264", WIDTH, HEIGHT, "30/1", 840):
        raise ValueError("Unexpected H.264 video geometry, frame rate or frame count")
    if abs(float(probe_data["format"]["duration"]) - 28.0) > 0.001:
        raise ValueError("Video does not match the 28-second voice timeline")
    manifest = {"id": reel_id, "output": {"width": WIDTH, "height": HEIGHT, "fps": FPS, "duration": 28, "audio": False, "file_size_bytes": output.stat().st_size, "safe_zone": [250, 1500], "disclaimer_max_y": 1450, "cover_frame_seconds": 1.8, "cover_quality": 95, "cover_color_profile": "sRGB"}, "render_seconds": round(time.monotonic() - started, 2), "scenes": scene_manifest, "ffprobe": probe_data}
    (external / "render-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"{reel_id}: DONE in {manifest['render_seconds']}s; {output.stat().st_size:,} bytes; silent H.264", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", action="append", choices=list(CLIP_PLANS), help="Build one or more selected IDs; default is storyboard build_order.")
    parser.add_argument("--work-dir", type=Path, required=True, help="External production directory containing stock/; intermediate data is kept here.")
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--ffprobe", default="ffprobe")
    parser.add_argument("--browser", help="Chromium executable used only for supplied SVG rasterization.")
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--force", action="store_true", help="Rebuild cached B-roll segments.")
    args = parser.parse_args()
    args.work_dir = args.work_dir.resolve()
    if args.work_dir == ROOT or ROOT in args.work_dir.parents:
        parser.error("--work-dir must be outside the repository")
    args.work_dir.mkdir(parents=True, exist_ok=True)
    storyboard = json.loads((ROOT / "reels_v2/storyboards.json").read_text(encoding="utf-8"))
    registry = json.loads((ROOT / "reels_v2/stock_sources.json").read_text(encoding="utf-8"))
    logo = render_supplied_logo(args.work_dir, find_browser(args.browser))
    for reel_id in args.only or storyboard["build_order"]:
        build_reel(reel_id, storyboard, registry, args, logo)


if __name__ == "__main__":
    main()
