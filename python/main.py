"""Arduino App Lab entry point for the Linux side of Outmark."""

from __future__ import annotations

import sys
from pathlib import Path

_PYTHON_ROOT = Path(__file__).resolve().parent
if str(_PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(_PYTHON_ROOT))

from outmark.app import create_app  # noqa: E402
from outmark.config import load_settings  # noqa: E402
from outmark.logsetup import configure_logging  # noqa: E402


def main() -> None:
    """Start the local web server. A missing model does not stop startup."""
    settings = load_settings()
    configure_logging(settings.log_level)
    app = create_app(settings)
    app.run(host=settings.host, port=settings.port, debug=False)


if __name__ == "__main__":
    main()
