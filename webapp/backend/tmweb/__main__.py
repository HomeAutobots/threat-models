"""Start the local web app. Refuses without an interactive terminal or under Claude Code."""
import argparse
import secrets
import sys
from pathlib import Path

from . import REPO_ROOT

from tmreg import core  # noqa: E402  (REPO_ROOT import puts registry/ on sys.path)


def main(argv: list[str] | None = None, *, root: Path = REPO_ROOT) -> int:
    parser = argparse.ArgumentParser(prog="tmweb")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--dev", action="store_true")
    args = parser.parse_args(argv)

    try:
        core.require_interactive("web")
    except core.RegistryError as exc:
        print(exc, file=sys.stderr)
        return 1

    import uvicorn

    from .app import create_app

    token = secrets.token_urlsafe(32)
    app = create_app(
        root,
        port=args.port,
        signin_token=token,
        static_dir=REPO_ROOT / "webapp/frontend/dist",
        dev=args.dev,
    )
    host = "localhost:5173" if args.dev else f"127.0.0.1:{args.port}"
    print(f"Sign in: http://{host}/signin?token={token}", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
