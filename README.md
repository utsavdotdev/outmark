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

`data/` and `models/` are gitignored. The service creates `data/` on startup. It does not download a model.

## Layout

```text
app.yaml                  App Lab manifest
python/main.py            Linux entry point
python/outmark/           Importable application package
python/requirements.txt   Board dependencies
sketch/                   Added when the matrix is integrated
tests/                    Automated checks that do not need the board
```

Open the repository as an Arduino App Lab app when the board is available. The session engine in `python/outmark/engine.py` stores proposals and sessions in `data/outmark.json`. The webpage does not accept or report commitments yet. Matrix rendering and local inference come in later stages. See `docs/BUILD_PLAN.md`.

## Checks

```bash
python -m ruff check python tests
python -m ruff format --check python tests
pytest
```
