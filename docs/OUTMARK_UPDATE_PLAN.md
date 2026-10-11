# Outmark interaction and animation update

This plan adapts the working application. It does not replace the session store, the local model adapter, or the paper-and-ink theme.

Baseline before these changes: `main` is 8 commits ahead of `origin/main`. `pytest` collected 54 tests and all passed on Python 3.14.5. No existing failure was recorded. `.DS_Store` is untracked and stays out of commits.

## What stays

- Flask, vanilla HTML/CSS/JS, and the `Iowan Old Style` / system-sans pairing.
- Colors already in `style.css`: `--ink #1a1814`, `--paper #f3efe6`, `--rule #2f5f8a`, `--muted #5c564c`.
- Linux owns sessions, the timer, history, and plant progression. The STM32 only draws.
- Stored session status remains `active`, `kept`, or `not_kept`. An expired timer still does not write `kept`.
- One JSON file, atomic replace, local llama-server, catalog fallback, no API key, no cloud model.
- Bridge entry points stay `Bridge.provide_safe` and `matrix.draw` of 104 pixels. The sketch must not call `delay`, `loadSequence`, or `playSequence`. The official UNO Q example uses those, and they block the loop. `setGrayscaleBits(3)` exists in that example. This update keeps 1-bit frames, which the current sketch already uses. Multi-bit brightness was not checked on the glass.

## Lifecycle

`awaiting_report` is derived, not stored. `GET /api/session` uses it when status is `active` and the deadline has passed.

| Phase | Stored status | Timer | Plant | Matrix steady frame |
| --- | --- | --- | --- | --- |
| `proposed` | proposal `proposed` | Not started | Unchanged | Chart idle, or the current plant |
| `rejected` | proposal `rejected` | Not started | Unchanged | Unchanged |
| `active` | `active`, deadline not passed | Running | Unchanged | Progress, without writing a history cell |
| `awaiting_report` | `active`, deadline passed | Stopped at the duration | Unchanged | Done mark. Not a growth frame |
| `kept` | `kept` | Closed | One stage, once | Growth animation, then the new plant or the chart |
| `not_kept` | `not_kept` | Closed | Unchanged | A short acknowledgement, then the previous plant or the chart |

`engine.report` refuses both `kept` and `not_kept` until `elapsed >= duration`. The HTTP route returns 409 with `error` and `remaining_seconds`. A second report on the same session stays a 409 and does not add another kept session.

Elapsed time inside one process uses the monotonic clock. After a restart, elapsed time is recovered from the stored `started_at` and the wall clock, which is the behavior already in `SessionEngine._recover_anchors`.

## Plant

Stage is `min(5, number of kept sessions)`. It is computed from the file, so a restart cannot award growth twice and a duplicate report cannot grow the plant if the report itself is rejected.

| Kept sessions | Stage | Picture |
| --- | --- | --- |
| 0 | 0 | Seed |
| 1 | 1 | Split seed |
| 2 | 2 | Sprout |
| 3 | 3 | Two leaves |
| 4 | 4 | Taller plant |
| 5 or more | 5 | Flower |

A later kept session after stage 5 does not raise the stage. The matrix plays a short flourish instead of a new silhouette. `not_kept` and rejection do not remove stages.

## Matrix mode

`settings.display_mode` is `chart` or `plant`. Missing field on an older file means `chart`, so existing files still load. New saves write the field. The document version stays 1.

Steady publish (including the 5-second refresh) sends mode, progress, row masks, the view, and the plant stage. It does not replay an event.

`set_event(code, generation)` is sent once per real transition. The sketch ignores a generation it has already played, so a reconnect snapshot does not replay an old growth.

Event codes: 1 startup, 2 proposal, 3 accept, 4 timer expired, 5 kept, 6 not kept, 7 mode switch.

The sketch advances frames with `millis()` and keeps calling `matrix.draw`. Incoming bridge handlers only store the next event. Loop stays short.

Pixel orientation of row 0 is still unverified on the glass. Frame tests check the 104-pixel contract, not a photographed LED.

## Web

Same theme and fonts. The page is reorganized into a header, one primary action, a dedicated timer with a circular progress ring, the plant drawing, a compact day-grouped log, and a plant/chart switch. "I kept it" and "I did not keep it" stay disabled until `phase` is `awaiting_report`. The ring uses the server's `remaining_seconds`, not an independent countdown.

`prefers-reduced-motion` removes the web plant's idle motion and short transitions.

## Tests

Timer tests move the fake clock to the deadline before a legal report, and add a case one second earlier that leaves the file unchanged. Plant tests count kept sessions. Frame tests check stage silhouettes and that a refresh publish does not emit a new event. Hardware playback, Bridge integer pairs, and which glass edge is row 0 stay listed as not run.

## Stages

Each stage is one commit, in order, after `ruff` and `pytest`. Nothing is pushed.

## Progress

- Stage 1: `engine.report` rejects both outcomes until the monotonic clock reaches the duration. The route returns 409 and `remaining_seconds`. `phase` is `awaiting_report` after the deadline while status stays `active`. 57 tests passed.
- Stage 2: the page uses the same type and colors, with a dedicated countdown ring. Report buttons stay disabled until `awaiting_report`.
- Stage 3: history entries are grouped by day and show time, duration, category, outcome, and an optional reflection. An expired timer stays on the countdown instead of returning to the setup form.
- Stage 4: plant stage is `min(5, kept sessions)`, returned on the session and history payloads. The page draws that stage. Reject, expiry, `not_kept`, an early report, and a duplicate report do not advance it. 63 tests passed.
- Stage 5: `frames.py` and the sketch share plant rows and event lengths. The sketch advances with `millis()` and `matrix.draw`. Playback on the physical glass was not run.
- Stage 6: `display_mode` is stored with older files defaulting to `chart`. A kept report sends event 5 before the new stage. Restart sends startup, not another growth event. An open proposal holds the pending pattern. 77 tests passed.
