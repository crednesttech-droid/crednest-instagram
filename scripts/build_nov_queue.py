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


def refresh_voice_timings(original, additions):
    """Replace only existing batch reel timings, preserving all other objects."""
    expected = {item["id"]: item for item in additions}
    decoder = json.JSONDecoder()
    cursor = original.index("[") + 1
    replacements = []
    while True:
        while cursor < len(original) and original[cursor].isspace():
            cursor += 1
        if original[cursor] == "]":
            break
        start = cursor
        item, cursor = decoder.raw_decode(original, cursor)
        target = expected.get(item.get("id"))
        if target is not None and item != target:
            if target["type"] != "reel" or any(item.get(key) != value for key, value in target.items() if key != "voice_scenes"):
                raise SystemExit(f"Refusing changes beyond voice timing for {item['id']}")
            if [scene["text"] for scene in item["voice_scenes"]] != [scene["text"] for scene in target["voice_scenes"]]:
                raise SystemExit(f"Refusing narration copy changes for {item['id']}")
            updated = dict(item)
            updated["voice_scenes"] = [dict(before, start=after["start"], end=after["end"])
                                       for before, after in zip(item["voice_scenes"], target["voice_scenes"])]
            if updated != item:
                replacements.append((start, cursor, json.dumps(updated, ensure_ascii=False, indent=1)))
        while cursor < len(original) and original[cursor].isspace():
            cursor += 1
        if original[cursor] == ",":
            cursor += 1
        elif original[cursor] != "]":
            raise SystemExit("Invalid queue array separator")
    for start, end, replacement in reversed(replacements):
        original = original[:start] + replacement + original[end:]
    return original, len(replacements)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--check", action="store_true", help="Compare only; do not write")
    modes.add_argument("--retime", action="store_true", help="Refresh only existing batch reel voice_scenes after rebuilding from a timings file")
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
        if len(already) != len(additions):
            raise SystemExit("Only part of the batch exists; refusing to overwrite")
        if any(existing[item["id"]] != item for item in additions):
            if not args.retime:
                raise SystemExit("Batch differs; use --retime to refresh only reel voice timings")
            updated, count = refresh_voice_timings(original, additions)
            expected = {item["id"]: item for item in additions}
            updated_queue = json.loads(updated)
            assert len(updated_queue) == len(queue)
            for before, after in zip(queue, updated_queue):
                if before == after:
                    continue
                assert before["id"] in expected and before["type"] == "reel"
                assert {key for key in set(before) | set(after) if before.get(key) != after.get(key)} == {"voice_scenes"}
                for old_scene, new_scene, target in zip(before["voice_scenes"], after["voice_scenes"], expected[before["id"]]["voice_scenes"]):
                    assert {key: value for key, value in old_scene.items() if key not in {"start", "end"}} == {key: value for key, value in new_scene.items() if key not in {"start", "end"}}
                    assert all(new_scene[key] == target[key] for key in ("start", "end", "text"))
            with queue_path.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(updated)
            print(f"Retimed {count} reels; captions, metadata and unrelated items unchanged")
            return
        print("OK: all 14 batch slots already match; unrelated items unchanged")
        return
    if args.retime:
        raise SystemExit("Cannot retime a batch that has not been added")
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
