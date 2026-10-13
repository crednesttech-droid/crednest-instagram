#!/usr/bin/env python3
"""Comment -> DM lead flow for @crednest.io (no webhook server needed).

Every run (inside the autopilot workflow) it reads comments on our posts from the
last N days. When a comment contains a keyword from engage.json (e.g. CHECKLIST),
it sends ONE private reply (Instagram DM) to that commenter with the free checklist
and the WhatsApp link, and leaves a short public reply. Every comment is handled
once; handled IDs are kept in state/engaged.json.

Rules from Instagram: one private reply per comment, within 7 days of the comment.

  python scripts/engage.py            handle new keyword comments
  python scripts/engage.py --dry-run  only list what it would do
"""
import argparse, json, os, re, sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import publish as P

ROOT = P.ROOT
CFG = os.path.join(ROOT, "engage.json")
STATE = os.path.join(ROOT, "state", "engaged.json")


def matches(text, keywords):
    t = (text or "").lower()
    return any(re.search(r"\b" + re.escape(k) + r"\b", t) for k in keywords)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    cfg = json.load(open(CFG, encoding="utf-8"))
    state = P.load(STATE, {})
    api = P.API()
    me = api.call("GET", "me", fields="user_id,username")
    my_name = (me.get("username") or "").lower()
    since = datetime.now(timezone.utc) - timedelta(days=cfg.get("lookback_days", 7))
    media = api.call("GET", f"{api.uid}/media", fields="id,timestamp,permalink", limit=50).get("data", [])
    checklist_url = P.url_for(cfg["checklist_path"])
    text = cfg["private_reply"].format(checklist_url=checklist_url, whatsapp_url=cfg["whatsapp_url"])
    done = 0
    for m in media:
        ts = datetime.strptime(m["timestamp"], "%Y-%m-%dT%H:%M:%S%z")
        if ts < since:
            continue
        comments = api.call("GET", f"{m['id']}/comments", fields="id,text,username,timestamp", limit=100).get("data", [])
        for c in comments:
            cid = c["id"]
            if cid in state or (c.get("username") or "").lower() == my_name:
                continue
            if not matches(c.get("text"), cfg["keywords"]):
                continue
            if done >= cfg.get("max_per_run", 25):
                break
            who = c.get("username", "?")
            if a.dry_run:
                print(f"would DM @{who} for comment '{c.get('text','')[:40]}' on {m.get('permalink')}")
                continue
            rec = {"username": who, "media": m["id"], "at": datetime.now(P.IST).isoformat()}
            try:
                api.call("POST", f"{api.uid}/messages",
                         recipient=json.dumps({"comment_id": cid}), message=json.dumps({"text": text}))
                rec["dm"] = "sent"
            except Exception as e:
                rec["dm"] = f"failed: {str(e)[:200]}"
            try:
                api.call("POST", f"{cid}/replies", message=cfg["public_reply"])
                rec["reply"] = "sent"
            except Exception as e:
                rec["reply"] = f"failed: {str(e)[:200]}"
            state[cid] = rec
            done += 1
            print(f"@{who}: dm {rec['dm']}, reply {rec['reply']}")
    if not a.dry_run:
        os.makedirs(os.path.dirname(STATE), exist_ok=True)
        json.dump(state, open(STATE, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print(f"engage: checked {len(media)} posts, handled {done} new keyword comment(s)")


if __name__ == "__main__":
    main()
