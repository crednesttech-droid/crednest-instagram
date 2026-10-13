#!/usr/bin/env python3
"""CredNest Instagram autopilot.

Publishes items from queue.json whose publish_at has passed, using the
Instagram API with Instagram Login (Graph API content publishing).
Media are fetched by Instagram from MEDIA_BASE_URL (GitHub Pages of this repo).

  python scripts/publish.py --check            validate queue + files, no network
  python scripts/publish.py --dry-run          show what would publish now
  python scripts/publish.py                    publish due items (needs secrets)
  python scripts/publish.py --only <id>        publish one item now (ignores time)
  python scripts/publish.py --refresh-token    print a refreshed long-lived token

Env: IG_USER_ID, IG_ACCESS_TOKEN, MEDIA_BASE_URL, GRAPH_VERSION (default v23.0).
"""
import argparse, json, os, sys, time, urllib.parse, urllib.request, urllib.error
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUEUE = os.path.join(ROOT, "queue.json")
STATE = os.path.join(ROOT, "state", "published.json")
IST = timezone(timedelta(hours=5, minutes=30))
MAX_PER_RUN = 3          # never flood the account if runs were missed
MAX_LATE = timedelta(hours=36)  # items later than this are skipped, not dumped together
CAPTION_MAX, HASHTAG_MAX = 2200, 30


def load(p, default):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def save_state(state):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=1, ensure_ascii=False)


def when(item):
    return datetime.fromisoformat(item["publish_at"])


# ---------- validation ----------
def check(queue):
    from PIL import Image
    errors, ids = [], set()
    for it in queue:
        i = it["id"]
        if i in ids: errors.append(f"{i}: duplicate id")
        ids.add(i)
        if it["type"] not in ("image", "carousel", "reel", "story"):
            errors.append(f"{i}: bad type {it['type']}")
        if it["status"] != "ready":
            continue
        cap = it.get("caption", "")
        if it["type"] != "story":
            if not cap: errors.append(f"{i}: empty caption")
            if len(cap) > CAPTION_MAX: errors.append(f"{i}: caption > {CAPTION_MAX}")
            if cap.count("#") > HASHTAG_MAX: errors.append(f"{i}: > {HASHTAG_MAX} hashtags")
        files = list(it["media"]) + ([it["cover"]] if it.get("cover") else [])
        if it["type"] == "carousel" and not 2 <= len(it["media"]) <= 10:
            errors.append(f"{i}: carousel needs 2-10 slides")
        for m in files:
            p = os.path.join(ROOT, m)
            if not os.path.exists(p):
                errors.append(f"{i}: missing {m}"); continue
            if m.endswith(".jpg"):
                with Image.open(p) as im:
                    if im.format != "JPEG": errors.append(f"{i}: {m} not JPEG")
                    w, h = im.size
                    ratio = w / h
                    if it["type"] == "story" and abs(ratio - 9 / 16) > 0.01:
                        errors.append(f"{i}: story not 9:16 ({w}x{h})")
                    if it["type"] in ("image", "carousel") and not 0.8 - 0.01 <= ratio <= 1.91:
                        errors.append(f"{i}: feed ratio {w}x{h} outside 4:5-1.91:1")
                if os.path.getsize(p) > 8 * 1024 * 1024:
                    errors.append(f"{i}: {m} > 8 MB")
    counts = {}
    for it in queue: counts[it["status"]] = counts.get(it["status"], 0) + 1
    print("Queue:", len(queue), "items", counts)
    for e in errors: print("ERROR", e)
    print("OK" if not errors else f"{len(errors)} error(s)")
    return not errors


# ---------- Graph API ----------
class API:
    def __init__(self):
        self.uid = os.environ["IG_USER_ID"]
        self.token = os.environ["IG_ACCESS_TOKEN"]
        self.base = f"https://graph.instagram.com/{os.environ.get('GRAPH_VERSION', 'v23.0')}"

    def call(self, method, path, **params):
        params["access_token"] = self.token
        data = urllib.parse.urlencode(params).encode()
        url = f"{self.base}/{path}"
        if method == "GET":
            req = urllib.request.Request(f"{url}?{data.decode()}")
        else:
            req = urllib.request.Request(url, data=data, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"{method} {path}: {e.code} {e.read().decode()[:500]}")

    def container(self, **p):
        return self.call("POST", f"{self.uid}/media", **p)["id"]

    def wait(self, cid, minutes=10):
        end = time.time() + minutes * 60
        while time.time() < end:
            s = self.call("GET", cid, fields="status_code,status").get("status_code")
            if s == "FINISHED": return
            if s in ("ERROR", "EXPIRED"): raise RuntimeError(f"container {cid}: {s}")
            time.sleep(10)
        raise RuntimeError(f"container {cid}: timed out")

    def publish(self, cid):
        return self.call("POST", f"{self.uid}/media_publish", creation_id=cid)["id"]


def url_for(path):
    base = os.environ.get("MEDIA_BASE_URL", "").rstrip("/")
    if not base: raise RuntimeError("MEDIA_BASE_URL not set")
    return f"{base}/{path}"


def reachable(url):
    try:
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status == 200
    except Exception:
        return False


def publish_item(api, it):
    for m in it["media"] + ([it["cover"]] if it.get("cover") else []):
        if not reachable(url_for(m)):
            raise RuntimeError(f"media not reachable yet: {url_for(m)} (Pages still building?)")
    t, cap = it["type"], it.get("caption", "")
    if t == "image":
        cid = api.container(image_url=url_for(it["media"][0]), caption=cap)
    elif t == "story":   # each frame is its own story, in order
        ids = []
        for m in it["media"]:
            c = api.container(image_url=url_for(m), media_type="STORIES")
            api.wait(c); ids.append(api.publish(c))
        return ",".join(ids)
    elif t == "reel":
        p = dict(video_url=url_for(it["media"][0]), media_type="REELS", caption=cap, share_to_feed="true")
        if it.get("cover"): p["cover_url"] = url_for(it["cover"])
        cid = api.container(**p)
    elif t == "carousel":
        kids = []
        for m in it["media"]:
            k = api.container(image_url=url_for(m), is_carousel_item="true")
            api.wait(k); kids.append(k)
        cid = api.container(media_type="CAROUSEL", children=",".join(kids), caption=cap)
    else:
        raise RuntimeError(f"unknown type {t}")
    api.wait(cid, minutes=15 if t == "reel" else 5)
    return api.publish(cid)


def due(queue, state, now):
    out = []
    for it in queue:
        if it["id"] in state: continue
        if it["status"] != "ready": continue
        if when(it) > now: continue
        if now - when(it) > MAX_LATE: continue
        out.append(it)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only")
    ap.add_argument("--now", help="pretend time (ISO) for dry runs")
    ap.add_argument("--refresh-token", action="store_true")
    a = ap.parse_args()
    queue = load(QUEUE, [])
    state = load(STATE, {})

    if a.check:
        sys.exit(0 if check(queue) else 1)
    if a.refresh_token:
        tok = os.environ["IG_ACCESS_TOKEN"]
        q = urllib.parse.urlencode({"grant_type": "ig_refresh_token", "access_token": tok})
        with urllib.request.urlopen(f"https://graph.instagram.com/refresh_access_token?{q}") as r:
            d = json.load(r)
        print("New token expires in", round(d.get("expires_in", 0) / 86400), "days. Update the IG_ACCESS_TOKEN secret.")
        print(d["access_token"])
        return

    now = datetime.fromisoformat(a.now) if a.now else datetime.now(IST)
    byid = {it["id"]: it for it in queue}
    if a.only:
        items = [byid[a.only]]
    else:
        items = due(queue, state, now)

    # a teaser story is dropped if the post it points to is not ready
    final = []
    for it in items:
        req = it.get("requires")
        if req and byid.get(req, {}).get("status") != "ready":
            print(f"SKIP {it['id']}: linked post {req} is not ready")
            state[it["id"]] = {"skipped": now.isoformat(), "reason": f"{req} not ready"}
            continue
        final.append(it)
    items = final[:MAX_PER_RUN]

    print(f"Now {now:%Y-%m-%d %H:%M} IST. Due: {[i['id'] for i in items] or 'nothing'}")
    if a.dry_run:
        for it in items:
            print(f"  would publish {it['type']:8} {it['id']}  ({len(it['media'])} file(s))")
        return

    api, failed = API(), 0
    for it in items:
        try:
            mid = publish_item(api, it)
            state[it["id"]] = {"media_id": mid, "published": datetime.now(IST).isoformat()}
            print(f"PUBLISHED {it['id']} -> {mid}")
        except Exception as e:
            failed += 1
            print(f"FAILED {it['id']}: {e}")
        save_state(state)
    save_state(state)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
