#!/usr/bin/env python3
"""Voice + music for reels.

Modes
  default      Sarvam (Bulbul) voice for every reel with status "needs_voice",
               then add the music bed. Marks the reel "ready".
  --music-only Keep each reel's current voice track, add/refresh the music bed
               and loudness. No Sarvam call, no cost. Use with --all or --only.

Audio: voice at -14 LUFS (Instagram-friendly), music bed ducked under the
voice (sidechain), fades in/out. Music comes from brand/audio/bed.wav if it
exists, otherwise scripts/music.py generates an original royalty-free bed.
The video stream is copied untouched.

  SARVAM_API_KEY=... python scripts/revoice.py [--speaker aditya] [--model bulbul:v3] [--only ID]
  python scripts/revoice.py --music-only --all
"""
import argparse, base64, json, os, subprocess, sys, tempfile, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUEUE = os.path.join(ROOT, "queue.json")
API = "https://api.sarvam.ai/text-to-speech"
BED = os.path.join(ROOT, "brand", "audio", "bed.wav")


def run(*cmd):
    subprocess.run(list(cmd), check=True)


def duration(p):
    return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                          "-of", "csv=p=0", p]).strip())


def tts(text, speaker, model, pace, key, out):
    body = json.dumps({"text": text, "language_code": "en-IN", "model": model,
                       "speaker": speaker, "pace": pace, "speech_sample_rate": 44100}).encode()
    req = urllib.request.Request(API, data=body, method="POST",
                                 headers={"api-subscription-key": key, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        d = json.load(r)
    with open(out, "wb") as f:
        f.write(base64.b64decode(d["audios"][0]))


def sarvam_voice(item, a, key, vlen, tmp):
    parts = []
    for n, sc in enumerate(item["voice_scenes"]):
        raw = os.path.join(tmp, f"s{n}.wav")
        tts(sc["text"], a.speaker, a.model, a.pace, key, raw)
        slot = max(0.5, min(sc["end"], vlen) - sc["start"] - 0.3)
        speed = min(max(duration(raw) / slot, 1.0), 1.35)
        fit = os.path.join(tmp, f"f{n}.wav")
        run("ffmpeg", "-y", "-v", "error", "-i", raw, "-af",
            f"atempo={speed:.3f},adelay={int((sc['start'] + 0.15) * 1000)}:all=1",
            "-ar", "44100", "-ac", "2", fit)
        parts.append(fit)
    voice = os.path.join(tmp, "voice.wav")
    inputs = sum([["-i", p] for p in parts], [])
    run("ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex",
        f"amix=inputs={len(parts)}:normalize=0,apad", "-t", f"{vlen:.3f}", voice)
    return voice


def existing_voice(video, vlen, tmp):
    voice = os.path.join(tmp, "voice.wav")
    run("ffmpeg", "-y", "-v", "error", "-i", video, "-vn", "-ac", "2", "-ar", "44100",
        "-af", "apad", "-t", f"{vlen:.3f}", voice)
    return voice


def music_bed(vlen, tmp, seed):
    bed = os.path.join(tmp, "bed.wav")
    if os.path.exists(BED):
        run("ffmpeg", "-y", "-v", "error", "-stream_loop", "-1", "-i", BED, "-t", f"{vlen:.3f}",
            "-ac", "2", "-ar", "44100", bed)
    else:
        run(sys.executable, os.path.join(ROOT, "scripts", "music.py"), bed,
            "--seconds", f"{vlen + 0.5:.2f}", "--seed", str(seed))
    return bed


def finish(video, voice, bed, vlen, tmp):
    mix = os.path.join(tmp, "mix.wav")
    fade_out = max(0.0, vlen - 1.5)
    fc = ("[0:a]loudnorm=I=-14:TP=-1.5:LRA=11,asplit=2[v][sc];"
          f"[1:a]volume=-19dB,afade=t=in:d=1,afade=t=out:st={fade_out:.2f}:d=1.5[m];"
          "[m][sc]sidechaincompress=threshold=0.03:ratio=6:attack=20:release=400[md];"
          "[v][md]amix=inputs=2:normalize=0,alimiter=limit=0.79,loudnorm=I=-14:TP=-2:LRA=11")
    run("ffmpeg", "-y", "-v", "error", "-i", voice, "-i", bed, "-filter_complex", fc,
        "-t", f"{vlen:.3f}", "-ar", "44100", mix)
    out = os.path.join(tmp, "out.mp4")
    run("ffmpeg", "-y", "-v", "error", "-i", video, "-i", mix, "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", out)
    os.replace(out, video)


def process(item, a, key, seed):
    video = os.path.join(ROOT, item["media"][0])
    vlen = duration(video)
    with tempfile.TemporaryDirectory() as tmp:
        voice = existing_voice(video, vlen, tmp) if a.music_only else sarvam_voice(item, a, key, vlen, tmp)
        bed = music_bed(vlen, tmp, seed)
        finish(video, voice, bed, vlen, tmp)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--speaker", default=os.environ.get("SARVAM_SPEAKER", "aditya"))
    ap.add_argument("--model", default=os.environ.get("SARVAM_MODEL", "bulbul:v3"))
    ap.add_argument("--pace", type=float, default=1.0)
    ap.add_argument("--only")
    ap.add_argument("--all", action="store_true", help="every reel, whatever its status")
    ap.add_argument("--music-only", action="store_true")
    ap.add_argument("--keep-status", action="store_true")
    ap.add_argument("--force", action="store_true", help="music-only: remix even if music was already added")
    a = ap.parse_args()
    key = os.environ.get("SARVAM_API_KEY")
    if not a.music_only and not key:
        sys.exit("SARVAM_API_KEY not set")
    q = json.load(open(QUEUE, encoding="utf-8"))
    reels = [i for i in q if i["type"] == "reel"]
    if a.only:
        targets = [i for i in reels if i["id"] == a.only]
    elif a.all:
        targets = reels
    else:
        targets = [i for i in reels if i["status"] == "needs_voice"]
    if a.music_only and not a.force:
        targets = [i for i in targets if "audio" not in i]  # never stack music twice
    for n, it in enumerate(targets):
        print(("music for" if a.music_only else f"voicing ({a.model} {a.speaker})"), it["id"])
        process(it, a, key, seed=n + 1)
        if not a.music_only:
            it["voice"] = f"sarvam {a.model} {a.speaker}"
            if not a.keep_status and it["status"] == "needs_voice":
                it["status"] = "ready"
        it["audio"] = "voice -14 LUFS + ducked music bed"
    json.dump(q, open(QUEUE, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print("done:", [i["id"] for i in targets])


if __name__ == "__main__":
    main()
