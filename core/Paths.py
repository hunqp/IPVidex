"""Application root; data, assets and the media subprocess are resolved from here."""

from pathlib import Path
import os
import sys

ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
DATA_ROOT = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "IPVidex" if getattr(sys, "frozen", False) else ROOT
ICONS = ROOT / "assets" / "icons"
