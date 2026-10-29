#!/usr/bin/env python3
"""CredNest Facebook Page cross-post.

Posts the feed items that are already live on Instagram (state/published.json)
to the CredNest Facebook Page, using the same media URLs on GitHub Pages.

  python scripts/fb_publish.py --dry-run               show what would post
  python scripts/fb_publish.py                         sync: items live on IG in the last 36 h
  python scripts/fb_publish.py --backfill              every post on the Instagram profile not yet on FB
                                                       (read live from the Instagram API, so manual posts count too)
  python scripts/fb_publish.py --backfill --limit 10   ...at most 10 this run
  python scripts/fb_publish.py --only D02-feed         one item now

Env: IG_ACCESS_TOKEN (backfill only, to list the Instagram posts),
     FB_PAGE_TOKEN (Page access token with pages_manage_posts),
     FB_PAGE_ID (optional; read from the token when blank),
     MEDIA_BASE_URL, GRAPH_VERSION (default v23.0).

Stories are not cross-posted. Reels go up as Page videos.
Instagram-only CTAs ("Comment CHECKLIST ... DM") are swapped for the WhatsApp CTA,
because comment-to-DM runs on Instagram only.
"""
import argparse, json, os, sys, time, urllib.parse, urllib.request, urllib.error
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUEUE = os.path.join(ROOT, "queue.json")
IG_STATE = os.path.join(ROOT, "state", "published.json")
FB_STATE = os.path.join(ROOT, "state", "fb_published.json")
IST = timezone(timedelta(hours=5, minutes=30))
SYNC_WINDOW = timedelta(hours=36)
FEED_TYPES = ("image", "carousel", "reel")
WHATSAPP_CTA = 'WhatsApp "Hi" to +91 98199 99057.'
IG_ONLY_CTAS = (
    "💬 Comment CHECKLIST and we'll DM you the free credit-pack checklist.",
    "💬 Comment CHECKLIST and we will DM you our free credit-pack checklist.",
)


def load(p, default):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def save(p, data):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)


def fb_caption(cap):
    for cta in IG_ONLY_CTAS:
        if cta in cap:
            cap = cap.replace(cta, "" if WHATSAPP_CTA in cap else WHATSAPP_CTA)
    while "\n\n\n" in cap:
        cap = cap.replace("\n\n\n", "\n\n")
    return cap.strip()


def url_for(path):
    if path.startswith("http"):
        return path
    base = os.environ.get("MEDIA_BASE_URL", "").rstrip("/")
    if not base:
        raise RuntimeError("MEDIA_BASE_URL not set")
    return f"{base}/{path}"


class Page:
    def __init__(self):
        self.token = os.environ["FB_PAGE_TOKEN"]
        self.base = f"https://graph.facebook.com/{os.environ.get('GRAPH_VERSION', 'v23.0')}"
        self.id = os.environ.get("FB_PAGE_ID") or self.call("GET", "me", fields="id")["id"]

    def call(self, method, path, **params):
        params["access_token"] = self.token
        data = urllib.parse.urlencode(params).encode()
        url = f"{self.base}/{path}"
        req = (urllib.request.Request(f"{url}?{data.decode()}") if method == "GET"
               else urllib.request.Request(url, data=data, method="POST"))
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"{method} {path}: {e.code} {e.read().decode()[:500]}")

    def post(self, it, backdate=None):
        t, msg = it["type"], fb_caption(it.get("caption", ""))
        extra = {}
        if backdate:
            extra = {"backdated_time": str(int(backdate.timestamp())), "backdated_time_granularity": "min"}
        if t == "image":
            return self.call("POST", f"{self.id}/photos", url=url_for(it["media"][0]), message=msg, **extra)["id"]
        if t == "carousel":
            ids = [self.call("POST", f"{self.id}/photos", url=url_for(m), published="false")["id"]
                   for m in it["media"]]
            media = {f"attached_media[{n}]": json.dumps({"media_fbid": i}) for n, i in enumerate(ids)}
            return self.call("POST", f"{self.id}/feed", message=msg, **media, **extra)["id"]
        if t == "reel":
            return self.call("POST", f"{self.id}/videos", file_url=url_for(it["media"][0]),
                             description=msg, **extra)["id"]
        raise RuntimeError(f"{it['id']}: type {t} is not cross-posted")


def ig_posts():
    """Every feed post on the Instagram profile, oldest first."""
    base = f"https://graph.instagram.com/{os.environ.get('GRAPH_VERSION', 'v23.0')}"
    q = urllib.parse.urlencode({
        "fields": "id,caption,media_type,media_url,timestamp,children{media_type,media_url}",
        "limit": 50, "access_token": os.environ["IG_ACCESS_TOKEN"]})
    url, out = f"{base}/me/media?{q}", []
    while url:
        with urllib.request.urlopen(url, timeout=60) as r:
            d = json.load(r)
        out += d.get("data", [])
        url = d.get("paging", {}).get("next")
    return sorted(out, key=lambda m: m["timestamp"])


def ig_to_item(m):
    """Shape an Instagram post like a queue item, with absolute media URLs."""
    kind = m["media_type"]
    if kind == "CAROUSEL_ALBUM":
        photos = [c["media_url"] for c in m.get("children", {}).get("data", []) if c["media_type"] == "IMAGE"]
        t, media = ("carousel", photos) if len(photos) > 1 else ("image", photos)
    elif kind == "VIDEO":
        t, media = "reel", [m["media_url"]]
    else:
        t, media = "image", [m["media_url"]]
    return {"id": f"ig:{m['id']}", "type": t, "media": media, "caption": m.get("caption", ""),
            "topic": (m.get("caption") or "").split("\n")[0][:70],
            "_when": datetime.fromisoformat(m["timestamp"].replace("+0000", "+00:00"))}


def pick(queue, ig, fb, now, backfill, only, done_ig=frozenset()):
    items = {i["id"]: i for i in queue}
    if only:
        return [items[only]]
    out = []
    for iid, rec in sorted(ig.items(), key=lambda kv: kv[1]["published"]):
        it = items.get(iid)
        if not it or it["type"] not in FEED_TYPES or iid in fb or str(rec.get("media_id")) in done_ig:
            continue
        if not backfill and now - datetime.fromisoformat(rec["published"]) > SYNC_WINDOW:
            continue
        out.append(it)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--backfill", action="store_true")
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--only")
    a = ap.parse_args()

    queue, ig, fb = load(QUEUE, []), load(IG_STATE, {}), load(FB_STATE, {})
    now = datetime.now(IST)
    done_ig = {str(r.get("ig_media_id")) for r in fb.values()} | {k[3:] for k in fb if k.startswith("ig:")}
    if a.backfill and not a.only:
        if not os.environ.get("IG_ACCESS_TOKEN"):
            sys.exit("IG_ACCESS_TOKEN not set; backfill reads the Instagram profile.")
        todo = [ig_to_item(m) for m in ig_posts() if m["id"] not in done_ig]
        todo = [t for t in todo if t["media"]][: a.limit]
    else:
        todo = pick(queue, ig, fb, now, a.backfill, a.only, done_ig)[: a.limit]
    print(f"{len(todo)} item(s) to post on Facebook")
    for it in todo:
        print(f"- {it['id']} ({it['type']}, {len(it['media'])} file(s)): {it.get('topic', '')}")
    if a.dry_run or not todo:
        if todo:
            print("\nCaption preview:\n" + fb_caption(todo[0].get("caption", "")))
        return

    if not os.environ.get("FB_PAGE_TOKEN"):
        print("FB_PAGE_TOKEN not set. Nothing posted.")
        return
    page = Page()
    failures = 0
    for it in todo:
        rec = ig.get(it["id"], {})
        backdate = it.get("_when") if a.backfill else None
        try:
            pid = page.post(it, backdate)
            fb[it["id"]] = {"post_id": pid, "published": datetime.now(IST).isoformat(),
                            "ig_media_id": it["id"][3:] if it["id"].startswith("ig:") else rec.get("media_id")}
            save(FB_STATE, fb)
            print(f"OK {it['id']} -> {pid}")
        except Exception as e:
            failures += 1
            print(f"FAIL {it['id']}: {e}")
        time.sleep(5)
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
