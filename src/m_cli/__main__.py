"""Allow ``python -m m_cli`` as an alias for the ``m`` entry point."""

from __future__ import annotations

import sys

from m_cli.cli import main

if __name__ == "__main__":
    sys.exit(main())
