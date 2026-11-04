# Activity status

A generic two-state display for an agent, task, appliance or other activity.
The manifest listens for `event:working` while it is active and
`event:waiting` when it needs attention. Both states are generic and can be
reused across domains.

Requires a Wignet whose capabilities include `scene` (runtime 2, RGB). No
speaker, motion sensor, buttons or assets are required. Before use, preview
`scene.json` with `push_scene` and `dry_run: true`; publish it and send the
current state again, then send events as the state changes. The Wignet server
does not monitor the activity for you.

For a standing display, call `push_scene` with `{"scene": <scene.json>,
"standing": true}`; this replaces the current slides. After it is active,
call `send_scene_event` with `{"name": "working"}` or
`{"name": "waiting"}`. The `event:` prefix belongs in the manifest, not
in the tool argument.

Licence: CC0-1.0. No owner data is included.

Example: an agent maintaining a build can send `working` during a build and
`waiting` when a decision is needed. An agent monitoring a household task can
reuse the same scene and send the same events for that task.
