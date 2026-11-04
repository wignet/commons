# Activity status

A generic two-state display for an agent, task, appliance or other activity.
Send `event:working` while it is active and `event:waiting` when it needs
attention. Both states are generic and can be reused across domains.

Requires a Wignet whose capabilities include `scene` (runtime 2, RGB). No
speaker, motion sensor, buttons or assets are required. Before use, preview
`scene.json` with `push_scene` and `dry_run: true`; publish it and send the
current state again, then send events as the state changes. The Wignet server
does not monitor the activity for you.

Licence: CC0-1.0. No owner data is included.
