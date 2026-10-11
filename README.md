# Outmark

Outmark is a self-accountability companion for the Arduino UNO Q. You choose a few minutes and a kind of time outside, get one activity from a model running on the board, step away, and later say whether you kept the promise. A kept report lights one cell on the 8×13 LED matrix.

The mark is your report. Outmark does not track your location, take a photo, or decide for you. The timer ending does not count as kept. You do.

## How it works

The page is the whole interaction.

1. Pick **5, 10, or 15 minutes** and one of eight categories.
2. **Suggest an activity.** The on-board model writes one. **Another suggestion** throws it out and asks again. Nothing is timed until you accept.
3. **Accept and start.** The ring counts down from the board, so closing the browser does not stop it.
4. When the time is up, the page asks how it went. A reflection is optional.
5. **I kept it** lights one cell for that category and day. **I did not keep it** is stored and leaves older cells as they are.

Past activity stays collapsed at the bottom. The board in the middle is the same thirteen-day chart the matrix shows: eight categories down, today in the last column. Several kept sessions in one category on one day still fill a single cell.

Suggestions stay inside the duration and category you picked. The first line of the activity states both. If the model wanders into a different kind of activity, Outmark uses a built-in activity for the category you chose, and the timer still runs.

## On the board

Open this repository in Arduino App Lab and run it. The app serves the page on port **8765**. The LED matrix updates through the Arduino Router Bridge. The sketch draws frames as they change and does not wait on the timer.

`app.yaml` starts the App Lab LLM brick with **Qwen3.5-0.8B-Q4_0**. The model stays on the UNO Q. No API key is sent, and a public model address is refused. The first suggestion after a restart can take a minute while the weights load.

Sessions and reflections are stored in `data/outmark.json` on the device.

## Develop on a computer

Python 3.11 or newer. App Lab on the board uses Python 3.13.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r python/requirements-dev.txt
python -m pytest
OUTMARK_HOST=127.0.0.1 python python/main.py
```

Open `http://127.0.0.1:8765/`. Without the board, suggestions come from the built-in catalog and the matrix is left unchanged. `python/requirements.txt` is what the board installs (`flask==3.1.3`).

| Variable | Default | Purpose |
| --- | --- | --- |
| `OUTMARK_HOST` | `0.0.0.0` | Address the web server binds |
| `OUTMARK_PORT` | `8765` | Port published in `app.yaml` |
| `OUTMARK_DATA_DIR` | `<app>/data` | JSON storage |
| `OUTMARK_MODEL_DIR` | `<app>/models` | Folder scanned for a `.gguf` file |
| `OUTMARK_LLM_URL` | `http://llamacpp-models-runner:9999/v1/chat/completions` | On-board model |
| `OUTMARK_LLM_MODEL` | `Qwen3.5-0.8B-Q4_0` | Model name sent to that server |
| `OUTMARK_LLM_TIMEOUT` | `180` | Seconds to wait, including the first load |

Outmark reads the process environment. It does not load a `.env` file. See `.env.example`.

## Layout

```text
app.yaml                 App Lab manifest and the LLM brick
python/main.py           Linux entry point
python/outmark/          Sessions, timer, model, and the page
sketch/sketch.ino        Matrix drawing on the STM32
sketch/sketch.yaml       Router Bridge libraries
tests/                   Workflow tests
```

The Linux side owns the session, the timer, the history, and the activity text. The STM32 only draws. The model only proposes words. It cannot start the timer or mark a session kept.
