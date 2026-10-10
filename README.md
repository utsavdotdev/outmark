# Outmark

Outmark is a local self-accountability companion for the Arduino UNO Q. It helps someone make a short screen-free outdoor commitment and keep a 13-day record on the board's LED matrix.

This repository currently runs the Linux-side web service. It starts without a language model and without the board attached.

## Requirements

- Python 3.11 or newer. The development machine may be newer. The UNO Q image used by the local-model examples is Python 3.13.
- A phone or computer on the same network, once the service is running on the board.

## Run the health check

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r python/requirements-dev.txt
pytest
python python/main.py
```

Then open `http://127.0.0.1:8080/` or request the health endpoint:

```bash
curl -s http://127.0.0.1:8080/health
```

A healthy process with no model installed responds with:

```json
{"data_dir_ready": true, "model_present": false, "status": "ok"}
```

If port 8080 is already in use, pick a free port. On macOS, 5000 and 7000 are often taken by AirPlay.

```bash
OUTMARK_PORT=8765 python python/main.py
```

Stop the server with Ctrl-C.

`python/requirements.txt` is the set App Lab installs on the board. `python/requirements-dev.txt` adds pytest and ruff for this computer.

## Configuration

The process reads environment variables. See `.env.example`. Outmark does not load a `.env` file by itself.

| Variable | Default | Purpose |
| --- | --- | --- |
| `OUTMARK_HOST` | `0.0.0.0` | Address the web server binds |
| `OUTMARK_PORT` | `8080` | Port published in `app.yaml` |
| `OUTMARK_DATA_DIR` | `<app>/data` | Persistent JSON storage. App Lab reserves this folder. |
| `OUTMARK_MODEL_DIR` | `<app>/models` | Directory scanned for a `.gguf` file |
| `OUTMARK_LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, or `CRITICAL` |
| `OUTMARK_LLM_URL` | `http://127.0.0.1:8081/v1/chat/completions` | Local llama-server. Public hosts are refused. |
| `OUTMARK_LLM_MODEL` | `qwen2.5-0.5b-instruct` | Alias passed to the local server |
| `OUTMARK_LLM_TIMEOUT` | `60` | Seconds to wait for one generation |

`data/` and `models/` are gitignored. The service creates `data/` on startup. It does not download a model.

## Layout

```text
app.yaml                  App Lab manifest
python/main.py            Linux entry point
python/outmark/           Importable application package
python/requirements.txt   Board dependencies
sketch/sketch.ino          LED matrix modes, drawn on the STM32
sketch/sketch.yaml        RouterBridge libraries for the sketch
tests/                    Automated checks that do not need the board
```

Open the repository as an Arduino App Lab app when the board is available. The session engine in `python/outmark/engine.py` stores proposals and sessions in `data/outmark.json`. On the board, `main.py` sends that state to the matrix through the Arduino Bridge. On a computer without `arduino.app_utils`, the web service still starts and the matrix is left unchanged. The page at `/` asks for one activity, accepts or rejects it, runs the timer, and records an explicit kept or not-kept report. See `docs/BUILD_PLAN.md`.

## Local model

Activity text comes from a local `llama-server` (llama.cpp) speaking `POST /v1/chat/completions`. The first model to try is [Qwen2.5-0.5B-Instruct Q4_K_M](https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF), about 491 MB, Apache 2.0. Download it on the board into `models/` (that directory is gitignored):

```bash
curl -L -o models/qwen2.5-0.5b-instruct-q4_k_m.gguf \
  https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/qwen2.5-0.5b-instruct-q4_k_m.gguf
```

Start the server on port 8081 so it does not collide with Outmark's web port:

```bash
llama-server \
  --model models/qwen2.5-0.5b-instruct-q4_k_m.gguf \
  --host 127.0.0.1 \
  --port 8081 \
  --alias qwen2.5-0.5b-instruct
```

If that file does not load, use SmolLM2-360M-Instruct Q4_K_M with the same server and set `OUTMARK_LLM_MODEL` to the alias you pass. No API key is used. If the server is down or the reply is not valid JSON, Outmark uses a built-in activity catalog. Latency and memory have not been measured on a UNO Q.

The sketch was not compiled in this repository's tests. Pytest checks the display commands and the 104-pixel frame rules. It does not light a physical LED.

## Checks

```bash
python -m ruff check python tests
python -m ruff format --check python tests
pytest
```
