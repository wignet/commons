# Task progress

A generic task status scene remixed from activity-status. It shows either
that a task is in progress or that it needs attention. Requires a Wignet with
scene runtime 2 on an RGB screen; no optional hardware is needed.

Preview `scene.json` with `push_scene` and `dry_run: true`. After publication,
send `send_scene_event` with `{"name": "working"}` or `{"name": "waiting"}`
and send the current state again each time the scene starts. The owner agent
monitors the task and sends changes.

Licence: CC0-1.0. No personal data is included.
