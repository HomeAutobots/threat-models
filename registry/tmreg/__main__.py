"""python3 registry/tmreg-package: `python3 -m tmreg` from the registry directory."""
import sys

if sys.version_info < (3, 11):
    sys.exit(f"tmreg needs Python 3.11 or later (for tomllib); this is {sys.version.split()[0]}. "
             "Use Homebrew's python3.")

from .cli import main  # noqa: E402

sys.exit(main(sys.argv[1:]))
