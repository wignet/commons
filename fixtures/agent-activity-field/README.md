# Agent activity field

Eight original geometric robots represent up to eight independent activities.
Each can be thinking, working, waiting for a person, done, asleep, or gone.
The artwork is original and released under CC0-1.0; it is not Clawd.

Requires `scene2` on a fast RGB Wignet. For each activity slot 1 to 8,
send `send_scene_event` with `{"name": "s1_working"}` (replace 1 with the
slot and working with thinking, working, waiting, done, asleep or gone).
Resend the current states after publishing: all robots start hidden. The
agent supplies its own activity driver and sends new states as they change;
Wignet does not observe the agent. Avoid putting personal information in
events or contributions.

Read `scene.json`, call `push_scene` with `dry_run: true`, then choose whether
to publish it temporarily or replace the slides. For a screen with different
dimensions, Wignet scales the design and reports memory use; reduce the
number of robots if the device cannot hold it. The scene uses no sound and
therefore also works on devices without a speaker.

To keep only the first N slots (1–8), keep objects whose `id` is at most N,
keep only `event:s<id>_...` entries for those ids, and keep the assets named
by the remaining sprites plus their `from` sources. Keep `robot`, which is
also the cover icon. Run `dry_run` again and send only the retained slot
events. This removes unused colour variants as well as sprites and events.

The robots start hidden, so include `"simulate": [{"at": 0, "event":
"event:s1_working"}]` alongside `dry_run: true` to see the first robot in
the preview. For a real `send_scene_event` call omit the `event:` prefix.
