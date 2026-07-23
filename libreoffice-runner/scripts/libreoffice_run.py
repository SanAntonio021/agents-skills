from __future__ import annotations

import sys
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from libreoffice_runner.core import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
