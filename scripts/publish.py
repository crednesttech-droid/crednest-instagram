#!/usr/bin/env python3
"""CredNest Instagram autopilot.

Publishes items from queue.json whose publish_at has passed, using the
Instagram API with Instagram Login (Graph API content publishing).
Media are fetched by Instagram from MEDIA_BASE_URL (GitHub Pages of this repo).

  python scripts/publish.py --check            validate queue + files, no network
  python scripts/publish.py --dry-run          show what would publish now
  python scripts/publish.py                    publish due items (needs secrets)
  python scripts/publish.py --only <id>        publish one item now (ignores time; refuses if already live)
  python scripts/publish.py --only <id> --force  re-publish even if state says it is live
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
MAX_LATE = timedelta(hours=36)  # items later than this are re-slotted (backfill), not dumped together
LATE_ALERT = timedelta(minutes=45)  # publishing later than this raises an alert
DUP_WINDOW = timedelta(hours=72)    # caption match on the live profile inside this window = already posted
SLOTS = ((12, 30), (19, 30))        # IST feed slots used for backfill
ALERTS = os.environ.get("ALERTS_FILE", os.path.join(ROOT, ".alerts.txt"))
STATUS = os.environ.get("STATUS_FILE", os.path.join(ROOT, ".status_kit.txt"))
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


def alert(msg):
    print("ALERT", msg)
    with open(ALERTS, "a", encoding="utf-8") as f:
        f.write(msg + "\n")


def save_queue(queue):
    with open(QUEUE, "w", encoding="utf-8") as f:
        json.dump(queue, f, indent=1, ensure_ascii=False)
        f.write("\n")


def norm(text):
    return " ".join((text or "").lower().split())[:120]


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

    def publish(self, cid, tries=6):
        # Instagram sometimes reports a container FINISHED but still rejects
        # media_publish with 9007 / 2207027 "Media ID is not available".
        # That error is a readiness race, so wait and retry instead of failing.
        for i in range(1, tries + 1):
            try:
                return self.call("POST", f"{self.uid}/media_publish", creation_id=cid)["id"]
            except RuntimeError as e:
                if ("2207027" not in str(e) and '"code":9007' not in str(e)) or i == tries:
                    raise
                print(f"media_publish not ready (attempt {i}/{tries}), retrying in {10 * i}s")
                time.sleep(10 * i)

    def recent(self, limit=25):
        """Live feed posts/reels: [(media_id, normalised caption, datetime)]."""
        d = self.call("GET", f"{self.uid}/media", fields="id,caption,timestamp", limit=limit)
        out = []
        for m in d.get("data", []):
            ts = datetime.strptime(m["timestamp"], "%Y-%m-%dT%H:%M:%S%z")
            out.append((m["id"], norm(m.get("caption")), ts))
        return out


def already_live(api, it, now, cache):
    """Duplicate guard: same caption already on the profile in the last 72 h."""
    if it["type"] == "story" or not it.get("caption"):
        return None
    if "recent" not in cache:
        try:
            cache["recent"] = api.recent()
        except Exception as e:
            print(f"WARN duplicate guard could not read profile: {e}")
            cache["recent"] = []
    key = norm(it["caption"])
    for mid, cap, ts in cache["recent"]:
        if cap == key and now - ts <= DUP_WINDOW:
            return mid
    return None


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


def status_kit(api, it, mid):
    """WhatsApp Status kit for Amrut: link + one line, posted to the 'whatsapp-status' issue."""
    try:
        link = api.call("GET", mid, fields="permalink").get("permalink", "")
    except Exception:
        link = ""
    hook = it.get("topic") or (it.get("caption") or "").split("\n")[0]
    kind = "reel" if it["type"] == "reel" else "post"
    with open(STATUS, "a", encoding="utf-8") as f:
        f.write(f"**{hook}**\n\nStatus line: Aaj ka {kind}: \"{hook}\" Dekho aur follow karo @crednest.io\n\n"
                f"Instagram app > this {kind} > Share > WhatsApp > My Status: {link}\n")


def due(queue, state, now):
    out = []
    for it in queue:
        if it["id"] in state: continue
        if it["status"] != "ready": continue
        if when(it) > now: continue
        if now - when(it) > MAX_LATE: continue
        out.append(it)
    return out


def missed(queue, state, now):
    return [it for it in queue
            if it["id"] not in state and it["status"] == "ready" and now - when(it) > MAX_LATE]


def backfill(queue, state, now):
    """Re-slot missed items instead of silently dropping them.

    Feed items (image/carousel/reel) move to the next free 12:30 / 19:30 IST slot
    with no other ready feed item. Stories are time-bound, so they are marked
    skipped (stale). Returns True if queue.json changed.
    """
    changed = False
    taken = {it["publish_at"][:16] for it in queue
             if it["type"] != "story" and it["status"] == "ready" and it["id"] not in state}
    for it in sorted(missed(queue, state, now), key=when):
        old = it["publish_at"]
        if it["type"] == "story":
            state[it["id"]] = {"skipped": now.isoformat(), "reason": "stale story (missed > 36 h)"}
            alert(f"MISSED story {it['id']} (was {old}) marked stale, not posted")
            continue
        day = now.date()
        slot = None
        while slot is None:
            for h, m in SLOTS:
                t = datetime(day.year, day.month, day.day, h, m, tzinfo=IST)
                if t > now + timedelta(minutes=30) and t.isoformat()[:16] not in taken:
                    slot = t; break
            day += timedelta(days=1)
        taken.discard(old[:16]); taken.add(slot.isoformat()[:16])
        it.setdefault("backfilled_from", old)
        it["publish_at"] = slot.isoformat()
        changed = True
        alert(f"BACKFILL {it['type']} {it['id']}: {old} -> {it['publish_at']}")
    return changed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only")
    ap.add_argument("--force", action="store_true", help="with --only: post even if state says live")
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
        if a.only in state and not a.force:
            print(f"REFUSED {a.only}: already in state/published.json ({state[a.only]}). Use --force to re-post.")
            return
        items = [byid[a.only]]
    else:
        if not a.dry_run and backfill(queue, state, now):
            save_queue(queue)
        items = due(queue, state, now)

    # a teaser story is dropped if the post it points to is not ready
    final = []
    for it in items:
        req = it.get("requires")
        if req and byid.get(req, {}).get("status") == "ready" and req not in state and not a.only:
            print(f"WAIT {it['id']}: linked post {req} is not live yet")
            continue
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
        for it in missed(queue, state, now):
            print(f"  would backfill {it['type']:8} {it['id']}  (was {it['publish_at']})")
        return

    api, failed, cache = API(), 0, {}
    for it in items:
        dup = None if (a.only and a.force) else already_live(api, it, now, cache)
        if dup:
            state[it["id"]] = {"media_id": dup, "published": "recovered-from-profile"}
            alert(f"DUPLICATE BLOCKED {it['id']}: caption already live as {dup}; state repaired")
            save_state(state)
            continue
        try:
            mid = publish_item(api, it)
            done = datetime.now(IST)
            state[it["id"]] = {"media_id": mid, "published": done.isoformat()}
            print(f"PUBLISHED {it['id']} -> {mid}")
            if it["type"] != "story":
                status_kit(api, it, mid)
            late = done - when(it)
            if not a.only and late > LATE_ALERT:
                alert(f"LATE {it['id']}: due {it['publish_at']}, posted {done:%d %b %H:%M} IST ({int(late.total_seconds() // 60)} min late)")
        except Exception as e:
            failed += 1
            alert(f"FAILED {it['id']}: {e}")
        save_state(state)
    save_state(state)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
