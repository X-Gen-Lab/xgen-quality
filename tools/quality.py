"""Run the installed shared checker for this repository."""

from pathlib import Path

from xgen_quality import main

if __name__ == "__main__":
    raise SystemExit(main(root=Path(__file__).resolve().parents[1]))
