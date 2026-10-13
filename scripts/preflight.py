#!/usr/bin/env python3
"""Preflight: prove the next items would publish, WITHOUT publishing anything.

For each selected item it checks the public media URLs, creates the Instagram
media container(s) and waits for status FINISHED. It never calls media_publish,
so nothing appears on the account; unused containers expire on their own.

  python scripts/preflight.py --next 5          next 5 unpublished items
  python scripts/preflight.py --types reel,story,carousel,image   one of each type (default)
"""
import argparse, json, os, sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import publish as P  # reuse API, url_for, reachable


def containers_only(api, it):
    files = it["media"] + ([it["cover"]] if it.get("cover") else [])
    for m in files:
        if not P.reachable(P.url_for(m)):
            raise RuntimeError(f"not reachable: {P.url_for(m)}")
    t = it["type"]
    if t == "image":
        c = api.container(image_url=P.url_for(it["media"][0]), caption=it["caption"]); api.wait(c, 5)
    elif t == "story":
        for m in it["media"]:
            c = api.container(image_url=P.url_for(m), media_type="STORIES"); api.wait(c, 5)
    elif t == "reel":
        p = dict(video_url=P.url_for(it["media"][0]), media_type="REELS", caption=it["caption"], share_to_feed="true")
        if it.get("cover"): p["cover_url"] = P.url_for(it["cover"])
        c = api.container(**p); api.wait(c, 15)
    elif t == "carousel":
        kids = []
        for m in it["media"]:
            k = api.container(image_url=P.url_for(m), is_carousel_item="true"); api.wait(k, 5); kids.append(k)
        c = api.container(media_type="CAROUSEL", children=",".join(kids), caption=it["caption"]); api.wait(c, 5)
    return "FINISHED"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--next", type=int, default=0)
    ap.add_argument("--types", default="story,carousel,reel,image")
    a = ap.parse_args()
    q = P.load(P.QUEUE, []); st = P.load(P.STATE, {})
    todo = [i for i in q if i["status"] == "ready" and i["id"] not in st]
    todo.sort(key=lambda i: i["publish_at"])
    if a.next:
        items = todo[:a.next]
    else:
        items, seen = [], set()
        for i in todo:
            if i["type"] in a.types.split(",") and i["type"] not in seen:
                items.append(i); seen.add(i["type"])
    api, bad = P.API(), 0
    print(f"Preflight {datetime.now(P.IST):%d %b %H:%M} IST - nothing will be published")
    for it in items:
        try:
            print(f"OK    {it['type']:8} {it['id']:18} {it['publish_at'][:16]}  container {containers_only(api, it)}")
        except Exception as e:
            bad += 1; print(f"FAIL  {it['type']:8} {it['id']:18} {e}")
    print("RESULT:", "ALL PASS" if not bad else f"{bad} FAILED")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
