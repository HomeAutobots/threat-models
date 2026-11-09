"""Start the local web app. Refuses without an interactive terminal or under Claude Code."""
import argparse
import errno
import logging
import secrets
import socket
import sys
from pathlib import Path

from . import REPO_ROOT
from .security import DEV_PORT

from tmreg import core  # noqa: E402  (REPO_ROOT import puts registry/ on sys.path)


def _port(text: str) -> int:
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{text!r} is not a number") from None
    if not 1 <= value <= 65535:
        raise argparse.ArgumentTypeError(f"{value} is not a port from 1 to 65535")
    return value


def main(argv: list[str] | None = None, *, root: Path = REPO_ROOT) -> int:
    parser = argparse.ArgumentParser(prog="tmweb")
    parser.add_argument("--port", type=_port, default=8765)
    parser.add_argument("--dev", action="store_true")
    args = parser.parse_args(argv)

    try:
        core.require_interactive("web")
    except core.RegistryError as exc:
        print(exc, file=sys.stderr)
        return 1

    # Bind before printing the link, so the link never points at another process holding the
    # port. SO_REUSEADDR lets a restart bind past the TIME_WAIT connections a just-stopped app
    # leaves; a socket still listening on 127.0.0.1:<port> makes the bind fail all the same.
    # Never set SO_REUSEPORT, which would let two listeners share the port.
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(("127.0.0.1", args.port))
    except OSError as exc:
        sock.close()
        if exc.errno == errno.EADDRINUSE:
            print(
                f"tmweb: port {args.port} is in use. Is the app already running in another Terminal window?",
                file=sys.stderr,
            )
        else:
            print(f"tmweb: cannot listen on 127.0.0.1:{args.port}: {exc.strerror or exc}",
                  file=sys.stderr)
        return 1
    port = sock.getsockname()[1]
    # Unhandled API errors are logged to "tmweb" (app.py) with their traceback; print them here.
    logging.basicConfig(level=logging.WARNING, format="%(name)s %(levelname)s: %(message)s")

    try:
        import uvicorn

        from .app import create_app

        token = secrets.token_urlsafe(32)
        app = create_app(
            root,
            port=port,
            signin_token=token,
            static_dir=REPO_ROOT / "webapp/frontend/dist",
            dev=args.dev,
        )
        host = f"localhost:{DEV_PORT}" if args.dev else f"127.0.0.1:{port}"
        print(f"Sign in: http://{host}/signin?token={token}", flush=True)
        try:
            uvicorn.Server(uvicorn.Config(app, log_level="warning")).run(sockets=[sock])
        except KeyboardInterrupt:  # Ctrl+C, as uvicorn.run() handles it
            pass
    finally:
        sock.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
