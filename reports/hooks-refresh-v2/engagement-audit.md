# Instagram engagement audit (report only)

The latest five runs of **Instagram autopilot** available at inspection were scheduled runs #47 through #43. All executed **Comment -> DM leads (keyword comments get the checklist)**, completed successfully, and logged zero newly handled keyword comments. No traceback, missing-scope error, caught DM failure, or caught public-reply failure appeared in those step logs.

| Run | Created (IST, 20 Oct 2026) | Engagement output | Evidence |
|---|---|---|---|
| #47 | 23:25:45 | `engage: checked 36 posts, handled 0 new keyword comment(s)` | [Job](https://github.com/crednesttech-droid/crednest-instagram/actions/runs/39470309940/job/118792305838) |
| #46 | 18:32:47 | `engage: checked 35 posts, handled 0 new keyword comment(s)` | [Job](https://github.com/crednesttech-droid/crednest-instagram/actions/runs/39427090053/job/118642261086) |
| #45 | 13:13:17 | `engage: checked 35 posts, handled 0 new keyword comment(s)` | [Job](https://github.com/crednesttech-droid/crednest-instagram/actions/runs/39388383774/job/118513684466) |
| #44 | 07:39:36 | `engage: checked 35 posts, handled 0 new keyword comment(s)` | [Job](https://github.com/crednesttech-droid/crednest-instagram/actions/runs/39357392698/job/118415241208) |
| #43 | 05:17:09 | `engage: checked 35 posts, handled 0 new keyword comment(s)` | [Job](https://github.com/crednesttech-droid/crednest-instagram/actions/runs/39343698129/job/118371105604) |

`state/engaged.json` is `{}` both locally and on current `main`. The observed zero-handle result is consistent with that empty state. The script considers posts in the last seven days, excludes its own comments and already-recorded comments, and looks for configured whole-word keywords. The log counts all fetched media, not the number of recent posts or comments. It does not distinguish no comments, no keyword matches, or exclusions by those filters.

The workflow sets this step `continue-on-error: true`, so workflow success alone would not establish health; the actual step logs above were inspected. `engage.py` catches POST DM/reply errors and would print `dm failed: ...` / `reply failed: ...`, then record the attempted comment. None occurred here. In particular, there is **no evidence of a missing `instagram_business_manage_comments` or `instagram_business_manage_messages` scope in these five runs**. No message or reply was attempted, so DM send permission and end-to-end delivery remain unverified by this evidence.

No code, workflow, or state was changed.
