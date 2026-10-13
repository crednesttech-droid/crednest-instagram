#!/usr/bin/env python3
"""Replace the robotic voiceover in reels with a Sarvam AI (Bulbul) Indian English voice.

For every queue item with status "needs_voice": each scene line in voice_scenes is
spoken by Sarvam, placed at the scene start, sped up slightly only if it would
overrun the scene, mixed with nothing else, and muxed into the reel (video untouched).
The item is then marked "ready".

  SARVAM_API_KEY=... python scripts/revoice.py [--speaker aditya] [--only D03-feed] [--keep-status]

Needs ffmpeg on PATH. Sarvam docs: https://docs.sarvam.ai/api-reference-docs/text-to-speech/convert
"""
import argparse, base64, json, os, subprocess, sys, tempfile, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUEUE = os.path.join(ROOT, "queue.json")
API = "https://api.sarvam.ai/text-to-speech"


def tts(text, speaker, model, pace, key, out):
    body = json.dumps({"text": text, "language_code": "en-IN", "model": model,
                       "speaker": speaker, "pace": pace, "speech_sample_rate": 44100}).encode()
    req = urllib.request.Request(API, data=body, method="POST",
                                 headers={"api-subscription-key": key, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        d = json.load(r)
    with open(out, "wb") as f:
        f.write(base64.b64decode(d["audios"][0]))


def duration(p):
    return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                          "-of", "csv=p=0", p]).strip())


def revoice(item, a, key):
    video = os.path.join(ROOT, item["media"][0])
    vlen = duration(video)
    with tempfile.TemporaryDirectory() as tmp:
        parts = []
        for n, sc in enumerate(item["voice_scenes"]):
            raw = os.path.join(tmp, f"s{n}.wav")
            tts(sc["text"], a.speaker, a.model, a.pace, key, raw)
            slot = max(0.5, min(sc["end"], vlen) - sc["start"] - 0.3)
            speed = min(max(duration(raw) / slot, 1.0), 1.35)   # never slower, at most 1.35x
            fit = os.path.join(tmp, f"f{n}.wav")
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", raw, "-af",
                            f"atempo={speed:.3f},adelay={int((sc['start'] + 0.15) * 1000)}:all=1",
                            "-ar", "44100", "-ac", "2", fit], check=True)
            parts.append(fit)
        mix = os.path.join(tmp, "voice.wav")
        inputs = sum([["-i", p] for p in parts], [])
        subprocess.run(["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex",
                        f"amix=inputs={len(parts)}:normalize=0,apad,loudnorm=I=-16:TP=-1.5",
                        "-t", f"{vlen:.3f}", mix], check=True)
        out = os.path.join(tmp, "out.mp4")
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", video, "-i", mix, "-map", "0:v:0", "-map", "1:a:0",
                        "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-shortest",
                        "-movflags", "+faststart", out], check=True)
        os.replace(out, video)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--speaker", default=os.environ.get("SARVAM_SPEAKER", "aditya"))
    ap.add_argument("--model", default=os.environ.get("SARVAM_MODEL", "bulbul:v3"))
    ap.add_argument("--pace", type=float, default=1.0)
    ap.add_argument("--only")
    ap.add_argument("--keep-status", action="store_true", help="re-voice but leave status unchanged")
    a = ap.parse_args()
    key = os.environ.get("SARVAM_API_KEY")
    if not key:
        sys.exit("SARVAM_API_KEY not set")
    q = json.load(open(QUEUE, encoding="utf-8"))
    targets = [i for i in q if i["type"] == "reel" and (i["id"] == a.only if a.only else i["status"] == "needs_voice")]
    for it in targets:
        print("re-voicing", it["id"], "with", a.speaker)
        revoice(it, a, key)
        if not a.keep_status and it["status"] == "needs_voice":
            it["status"] = "ready"
        it["voice"] = f"sarvam {a.model} {a.speaker}"
    json.dump(q, open(QUEUE, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print("done:", [i["id"] for i in targets])


if __name__ == "__main__":
    main()
