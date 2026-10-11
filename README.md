# Outmark

Outmark is a local self-accountability companion for the Arduino UNO Q. A person asks for a short screen-free outdoor commitment, steps away, and later reports whether they kept it. Kept reports leave a mark on an 8×13 LED matrix, thirteen days wide. The device does not check that the person went outside.

The Linux side of the board owns sessions, the timer, history, and activity text. The STM32 only draws the matrix. A local open-weight model may suggest the words. It cannot start a timer or mark a session kept.

This repository has been run on a development computer. It has not been run on a UNO Q. Sections below say which steps were checked here and which are still board steps.

The product spec is [docs.md](docs.md). The implementation record is [docs/BUILD_PLAN.md](docs/BUILD_PLAN.md).

## Run on a computer

Checked on this machine (macOS, Python 3.14.5) from the repository root. The code targets Python 3.11 or newer. That older version was not the one used for these checks. The UNO Q local-model examples use Python 3.13.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r python/requirements-dev.txt
python -m pytest
python -m ruff check python tests
python -m ruff format --check python tests
```

`app.yaml` publishes port 8765. Port 8080 was already taken on this machine, so the app listens on 8765 instead. Start it with:

```bash
OUTMARK_HOST=127.0.0.1 python python/main.py
```

Opening `http://127.0.0.1:8765/` loaded the page. `GET /health` with no model file responded with:

```json
{"data_dir_ready": true, "model_present": false, "status": "ok"}
```

Stop the server with Ctrl-C. On macOS, ports 5000 and 7000 are often taken by AirPlay.

`python/requirements.txt` is what App Lab installs on the board (`flask==3.1.3`). `python/requirements-dev.txt` adds pytest and ruff for a computer. There is no application `LICENSE` file in this repository. The intended model weights are Apache 2.0, as noted below.

## Webpage

The page is the only input. It asks for 5, 10, or 15 minutes and one of eight categories, then shows one suggestion.

- **Another suggestion** rejects that proposal. Nothing is timed.
- **Accept and start** is the only action that starts the timer. The timer keeps going if the browser closes.
- When the time is up, the session stays active until the person chooses **I kept it** or **I did not keep it**. Expiry does not count as kept.
- A reflection is optional. Only a kept report lights a history cell. A not-kept report is stored and does not clear older cells.
- If no model file is installed, or the local model does not answer, the page says so and uses a built-in catalog. That catalog path was used in the browser check on this computer.

## Architecture

```text
browser  ->  Flask on the Linux MPU  ->  session engine and data/outmark.json
                |                          |
                v                          v
         local llama-server          Arduino Router Bridge
         (optional)                         |
                                            v
                                    STM32 sketch draws the matrix
```

The model returns text only. Display commands are small integers: a mode, a progress count from 0 to 13, and eight row masks. Application code must not open `/dev/ttyHS1`; the router owns that port. On the board, Python calls `arduino.app_utils.Bridge`. On a computer without that package, the web service still starts and the matrix is left unchanged. That computer path was the one checked here.

## State machine

| State | How it is entered | Timer | Matrix |
| --- | --- | --- | --- |
| Proposed | A suggestion is accepted by the validator or the catalog | Not started | Stays idle, or on the history grid if a cell is already lit |
| Rejected | The person asks for another suggestion | Not started | Unchanged |
| Active | The person accepts | Started and stored | A center column, then a progress bar |
| Active, time up | Derived from the stored start time. The status is not rewritten | Held at the deadline for display | A small done mark. This is not a kept cell |
| Kept | The person reports that they kept it | Closed | History grid. One cell for that category and local day |
| Not kept | The person reports that they did not | Closed | History grid, with no new cell |

Several kept activities in one category on one day still light one cell. Older sessions stay in `data/outmark.json` after they leave the 13-day window.

Matrix rows, from the first frame row: walking, nature observation, quiet outdoor time, social connection, outdoor care, exploring, creative observation, other. Column 0 is the oldest day in the window. Column 12 is today. Which physical edge of the glass is row 0 has not been checked.

## Hardware setup

**Not run on a board.** The sketch was not compiled, and no LED was observed.

1. Open this repository in Arduino App Lab as an app. The entry points are `python/main.py`, `app.yaml`, `sketch/sketch.ino`, and `sketch/sketch.yaml`.
2. `sketch/sketch.yaml` pins `Arduino_RouterBridge` 0.3.0 and the libraries from Arduino's led-matrix-painter example. Those versions were not resolved on this machine. `Arduino_LED_Matrix` is expected from the UNO Q core, not from that file.
3. Run the app. The sketch exposes `set_mode`, `set_progress`, and `set_grid_row` with `Bridge.provide_safe`. `loop()` redraws when the state changes and does not wait for the timer.
4. From a phone or computer on the same network, open the published web port. `app.yaml` lists port 8765. Reachability from another device was not checked. Whether an App Lab container can see the host's `127.0.0.1` was not checked.

The onboard control is a power button. The UNO Q manual says a press of about five seconds reboots Linux. It does not document a short press that an application can handle. This was read from the manual, not from a press on this board. Do not bind accept, reject, or report to that button. Use the webpage.

Do not depend on the RGB LEDs. They are unused.

## Local model

**The download and the server command below have not been run.**

Activity text is requested from `llama-server` (llama.cpp) at `POST /v1/chat/completions`. The first model to try is [Qwen2.5-0.5B-Instruct Q4_K_M](https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF), about 491 MB, Apache 2.0. Put it in `models/` on the board. That directory is gitignored. No API key is sent.

```bash
curl -L -o models/qwen2.5-0.5b-instruct-q4_k_m.gguf \
  https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/qwen2.5-0.5b-instruct-q4_k_m.gguf
```

```bash
llama-server \
  --model models/qwen2.5-0.5b-instruct-q4_k_m.gguf \
  --host 127.0.0.1 \
  --port 8081 \
  --alias qwen2.5-0.5b-instruct
```

Port 8081 keeps the model off the web port. If that GGUF does not load, use SmolLM2-360M-Instruct Q4_K_M with the same server and set `OUTMARK_LLM_MODEL` to the alias you pass. SmolLM2-360M is also Apache 2.0. It was not downloaded. Do not add a second runtime. Latency and memory have not been measured.

Outmark refuses a model URL that is not local. If the server is down, the reply is not valid JSON, or the text claims the activity is already complete, the catalog is used and the timer can still run. Point `OUTMARK_LLM_URL` at `HOST_IP` only after a board check shows the container cannot reach host `127.0.0.1`. That check has not been done.

## Configuration

The process reads environment variables. See `.env.example`. Outmark does not load a `.env` file by itself.

| Variable | Default | Purpose |
| --- | --- | --- |
| `OUTMARK_HOST` | `0.0.0.0` | Address the web server binds |
| `OUTMARK_PORT` | `8765` | Port published in `app.yaml` |
| `OUTMARK_DATA_DIR` | `<app>/data` | Persistent JSON storage. App Lab reserves this folder. |
| `OUTMARK_MODEL_DIR` | `<app>/models` | Directory scanned for a `.gguf` file |
| `OUTMARK_LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, or `CRITICAL` |
| `OUTMARK_LLM_URL` | `http://127.0.0.1:8081/v1/chat/completions` | Local llama-server. Public hosts are refused. |
| `OUTMARK_LLM_MODEL` | `qwen2.5-0.5b-instruct` | Alias passed to the local server |
| `OUTMARK_LLM_TIMEOUT` | `60` | Seconds to wait for one generation |

`data/` and `models/` are gitignored. The service creates `data/` on startup. It does not download a model.

## Privacy and limits

Sessions and reflections stay in `data/outmark.json` on the device. There are no accounts, no cloud model, and no API key. The page does not ask for a photograph or a location.

A kept cell is a self-report, not evidence. Outmark cannot tell whether the report is honest, and it does not punish a missed commitment.

Known limits, still open until a board is available:

- Which glass edge is row 0, and whether Bridge integer masks arrive as 0 through 8191.
- Whether a phone can open the App Lab web port, and whether the app container must use `HOST_IP` to reach `llama-server`.
- Generation latency and memory for the Qwen file.
- Whether `data/outmark.json` survives an App Lab restart.
- A real lit cell after a kept report.

## Demo

The product is done when these steps happen on a UNO Q. The right-hand column is what this repository has already checked.

| Step | On a board | Checked here |
| --- | --- | --- |
| 1. Start Outmark | Run the App Lab app | Started on this computer with `OUTMARK_PORT=8765`. Not started on a board. |
| 2. Generate an activity with the local model | `llama-server` on port 8081 | Not run. The page used the catalog after the model request failed. |
| 3. Reject it and ask for another | Webpage | Done in the browser. No timer started. |
| 4. Accept one | Webpage | Done. The timer counted down. |
| 5. Close the browser | Timer keeps going | A new process restored an active session from the file, including after the deadline, and did not mark it kept. A browser was not closed mid-timer. |
| 6. Report kept or not kept | Webpage, after returning | Done. Both reports were used. Expiry did not report by itself. |
| 7. History file still has the session | `data/outmark.json` | Tests read the file back. The page showed the reflection after reload. |
| 8. The matching matrix cell changes | Only for a kept report | An in-memory display selected the history grid. No LED was seen. |
| 9. Restart and the records remain | Stop and start the App Lab app | A second process read the same file. An App Lab restart was not done. |
| 10. Disconnect external internet | After the model and dependencies are installed | Not done. A closed local port and a refused public URL were tested instead. |

## Layout

```text
app.yaml                  App Lab manifest
python/main.py            Linux entry point
python/outmark/           Importable application package
python/requirements.txt   Board dependencies
sketch/sketch.ino         LED matrix modes, drawn on the STM32
sketch/sketch.yaml        RouterBridge libraries for the sketch
tests/                    Automated checks that do not need the board
docs/BUILD_PLAN.md        What each stage checked, and what is still open
```
