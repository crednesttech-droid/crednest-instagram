#!/usr/bin/env python3
"""Add only the approved Nov 16–29 batch; never change unrelated queue items."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BATCH = ROOT / "batch_nov16_29/batch.json"
TIMINGS = ROOT / "reels_nov2026/queue_voice_scenes.json"


def entries(batch, timings):
    result = []
    for spec in batch["items"]:
        item = {
            "id": spec["id"],
            "type": "image" if spec["type"] == "reserved" else spec["type"],
            "publish_at": spec["publish_at"],
            "media": [],
            "caption": spec.get("caption", ""),
            "status": "needs_content",
            "source": "Nov 16–29 final-copy brief; user-confirmed series tags",
        }
        if spec["type"] == "reserved":
            item["reserved_for"] = "Claude"
            item["editor_note"] = spec["instruction"]
        else:
            item["topic"] = spec["hook"]
            item["series"] = spec["series"]
            if spec["type"] == "carousel":
                item["media"] = [f"media/{spec['id']}/{s['number']:02d}.jpg" for s in spec["slides"]]
                item["status"] = "review"
            else:
                if spec["id"] not in timings:
                    raise SystemExit(f"Missing exact voice timing for {spec['id']}: {TIMINGS}")
                scenes = timings[spec["id"]]
                if [s["text"] for s in scenes] != spec["voice_lines"]:
                    raise SystemExit(f"Voice copy mismatch for {spec['id']}")
                item["media"] = [f"media/{spec['id']}/reel.mp4"]
                item["cover"] = f"media/{spec['id']}/cover.jpg"
                item["voice_scenes"] = scenes
                item["voice_lang"] = "hi-IN"
                item["status"] = "needs_voice"
        result.append(item)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Compare only; do not write")
    args = parser.parse_args()
    batch = json.loads(BATCH.read_text(encoding="utf-8"))
    timings = json.loads(TIMINGS.read_text(encoding="utf-8"))
    additions = entries(batch, timings)
    queue_path = ROOT / "queue.json"
    original = queue_path.read_text(encoding="utf-8")
    queue = json.loads(original)
    existing = {item["id"]: item for item in queue}
    already = [item for item in additions if item["id"] in existing]
    if already:
        if len(already) != len(additions) or any(existing[item["id"]] != item for item in additions):
            raise SystemExit("Batch IDs already exist with different content; refusing to overwrite")
        print("OK: all 14 batch slots already match; unrelated items unchanged")
        return
    if args.check:
        raise SystemExit("Batch has not yet been added")
    # Append without reserializing any pre-existing object, including its spacing.
    prefix = original.rstrip()
    if not prefix.endswith("]"):
        raise SystemExit("queue.json must be a JSON array")
    prefix = prefix[:-1].rstrip()
    chunks = [json.dumps(item, ensure_ascii=False, indent=1) for item in additions]
    updated = prefix + ("," if queue else "") + "\n " + ",\n ".join(chunks) + "\n]\n"
    assert json.loads(updated) == queue + additions
    with queue_path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(updated)
    print("Added 6 review carousels, 6 needs_voice reels and 2 empty reserved slots")


if __name__ == "__main__":
    main()
