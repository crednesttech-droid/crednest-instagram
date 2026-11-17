#!/usr/bin/env python3
"""Auto-replies for @crednest.io comments and DMs (no webhook server needed).

Runs inside every autopilot run (every 15 min). For comments from the last N days on our posts:
  keyword (CHECKLIST, ...)  -> private reply (DM) with the checklist + WhatsApp, public "DM bhej diya"
  question (kya/kaise/?...) -> private reply with WhatsApp + checklist, public "DM mein detail bheja"
  anything else             -> one short public thank-you (rotating)
  complaint/abuse words     -> no auto reply; flagged to the Inbox issue for Amrut
  links / own comments      -> skipped
For DMs: a new inbound message gets the welcome auto-reply (at most once per conversation per
cooldown), and every new DM is flagged to the Inbox issue so a human answers within the day.

Instagram rules: one private reply per comment within 7 days; DM replies only inside the
24-hour window after the person's last message. Handled ids live in state/engaged.json.

  python scripts/engage.py            handle new comments and DMs
  python scripts/engage.py --dry-run  only list what it would do
"""
import argparse, json, os, re, sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import publish as P

ROOT = P.ROOT
CFG = os.path.join(ROOT, "engage.json")
STATE = os.path.join(ROOT, "state", "engaged.json")
INBOX = os.environ.get("INBOX_FILE", os.path.join(ROOT, ".inbox.txt"))


def matches(text, words):
    t = (text or "").lower()
    return any((w in t) if not w.isalnum() else re.search(r"\b" + re.escape(w) + r"\b", t) for w in words)


def inbox(line):
    print("INBOX", line)
    with open(INBOX, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def classify(text, cfg):
    t = (text or "").lower()
    if "http" in t or "www." in t:
        return "skip"
    if matches(t, cfg.get("human_words", [])):
        return "human"
    if matches(t, cfg["keywords"]):
        return "keyword"
    if matches(t, cfg.get("question_words", [])):
        return "question"
    return "thanks" if cfg.get("auto_reply_all_comments") else "skip"


def handle_comments(api, cfg, state, my_name, fill, dry):
    since = datetime.now(timezone.utc) - timedelta(days=cfg.get("lookback_days", 7))
    media = api.call("GET", f"{api.uid}/media", fields="id,timestamp,permalink", limit=50).get("data", [])
    done, n_thanks = 0, sum(1 for v in state.values() if v.get("kind") == "thanks")
    for m in media:
        if datetime.strptime(m["timestamp"], "%Y-%m-%dT%H:%M:%S%z") < since:
            continue
        comments = api.call("GET", f"{m['id']}/comments", fields="id,text,username,timestamp", limit=100).get("data", [])
        for c in comments:
            cid, who, text = c["id"], c.get("username", "?"), c.get("text", "")
            if cid in state or who.lower() == my_name or done >= cfg.get("max_per_run", 25):
                continue
            kind = classify(text, cfg)
            rec = {"username": who, "media": m["id"], "kind": kind, "at": datetime.now(P.IST).isoformat()}
            if dry:
                print(f"would handle [{kind}] @{who}: '{text[:50]}' on {m.get('permalink')}")
                continue
            if kind == "human":
                inbox(f"COMMENT needs you: @{who}: \"{text[:150]}\" {m.get('permalink')}")
            elif kind in ("keyword", "question"):
                dm = fill(cfg["private_reply"] if kind == "keyword" else cfg["question_private_reply"])
                pub = cfg["public_reply"] if kind == "keyword" else cfg["question_public_reply"]
                for step, fn in (("dm", lambda: api.call("POST", f"{api.uid}/messages",
                                                         recipient=json.dumps({"comment_id": cid}),
                                                         message=json.dumps({"text": dm}))),
                                 ("reply", lambda: api.call("POST", f"{cid}/replies", message=pub))):
                    try:
                        fn(); rec[step] = "sent"
                    except Exception as e:
                        rec[step] = f"failed: {str(e)[:200]}"
                if kind == "question":
                    inbox(f"QUESTION (auto-replied, follow up on WhatsApp): @{who}: \"{text[:150]}\" {m.get('permalink')}")
            elif kind == "thanks":
                msg = cfg["thanks_replies"][n_thanks % len(cfg["thanks_replies"])]
                n_thanks += 1
                try:
                    api.call("POST", f"{cid}/replies", message=msg); rec["reply"] = "sent"
                except Exception as e:
                    rec["reply"] = f"failed: {str(e)[:200]}"
            state[cid] = rec
            done += 1
            print(f"[{kind}] @{who}: {rec.get('dm', '-')} / {rec.get('reply', '-')}")
    return len(media), done


def handle_dms(api, cfg, state, my_id, fill, dry):
    """Welcome auto-reply to new inbound DMs + flag each to the Inbox issue."""
    try:
        convs = api.call("GET", "me/conversations", platform="instagram",
                         fields="id,updated_time,messages.limit(3){id,from,message,created_time}").get("data", [])
    except Exception as e:
        print(f"WARN DMs skipped (token may lack instagram_business_manage_messages): {str(e)[:200]}")
        return 0
    now = datetime.now(timezone.utc)
    cool = timedelta(hours=cfg.get("dm_reply_cooldown_hours", 12))
    n = 0
    for cv in convs:
        msgs = (cv.get("messages") or {}).get("data", [])
        if not msgs:
            continue
        last = msgs[0]                       # newest first
        frm = last.get("from") or {}
        if str(frm.get("id")) == str(my_id) or f"dm:{last['id']}" in state:
            continue
        at = datetime.strptime(last["created_time"], "%Y-%m-%dT%H:%M:%S%z")
        if now - at > timedelta(hours=23):  # outside the 24 h reply window: just record
            state[f"dm:{last['id']}"] = {"kind": "dm-old", "at": now.isoformat()}
            continue
        who = frm.get("username") or frm.get("id")
        if dry:
            print(f"would auto-reply DM from @{who}: '{(last.get('message') or '')[:50]}'"); continue
        rec = {"kind": "dm", "username": who, "at": datetime.now(P.IST).isoformat()}
        conv_key = f"conv:{cv['id']}"
        last_auto = state.get(conv_key, {}).get("auto_at")
        if not last_auto or now - datetime.fromisoformat(last_auto) > cool:
            try:
                api.call("POST", f"{api.uid}/messages", recipient=json.dumps({"id": frm.get("id")}),
                         message=json.dumps({"text": fill(cfg["dm_auto_reply"])}))
                rec["reply"] = "sent"
                state[conv_key] = {"auto_at": now.isoformat()}
            except Exception as e:
                rec["reply"] = f"failed: {str(e)[:200]}"
        else:
            rec["reply"] = "cooldown"
        inbox(f"DM needs you: @{who}: \"{(last.get('message') or '[attachment]')[:150]}\" (auto-reply: {rec['reply']})")
        state[f"dm:{last['id']}"] = rec
        n += 1
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    cfg = json.load(open(CFG, encoding="utf-8"))
    state = P.load(STATE, {})
    api = P.API()
    me = api.call("GET", "me", fields="user_id,username")
    my_name, my_id = (me.get("username") or "").lower(), me.get("user_id") or api.uid
    checklist_url = P.url_for(cfg["checklist_path"])
    fill = lambda t: t.format(checklist_url=checklist_url, whatsapp_url=cfg["whatsapp_url"])
    posts, done = handle_comments(api, cfg, state, my_name, fill, a.dry_run)
    dms = handle_dms(api, cfg, state, my_id, fill, a.dry_run)
    if not a.dry_run:
        os.makedirs(os.path.dirname(STATE), exist_ok=True)
        json.dump(state, open(STATE, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print(f"engage: checked {posts} posts, handled {done} comment(s), {dms} DM(s)")


if __name__ == "__main__":
    main()
