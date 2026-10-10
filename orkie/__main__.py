"""Allow ``python -m orkie``."""

from orkie.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
