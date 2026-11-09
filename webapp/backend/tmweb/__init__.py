"""Local web app for the threat-model registry. Imports tmreg from registry/."""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

_REGISTRY_DIR = str(REPO_ROOT / "registry")
if _REGISTRY_DIR not in sys.path:
    sys.path.insert(0, _REGISTRY_DIR)
