"""The real static export of shop.dsl through the pinned Structurizr, then served behind the lock.

Skipped unless TM_C4_CONFORMANCE=1 and `docker info` succeeds:
    cd webapp/backend && TM_C4_CONFORMANCE=1 uv run --frozen pytest -q tests/test_diagrams_docker.py
The export runs with --network none, like every Docker run here.
"""
import base64
import hashlib
import json
import os
import re
import subprocess
import urllib.parse
from html.parser import HTMLParser

import pytest
from fastapi.testclient import TestClient

from conftest import BASE, REPO_ROOT
from tmreg import c4
from tmweb import diagrams
from tmweb.app import CSP, create_app

SHOP = REPO_ROOT / "registry" / "tests" / "fixtures" / "c4" / "shop.dsl"
# c4.EXPECTED_INLINE_HASHES sits beside c4.STRUCTURIZR_IMAGE. The pinned image's index.html is the
# same for every workspace, with one inline script. If the image changes, review its exported JS
# against the CSP again (eval, workers, frames, fonts, requests to other origins) before updating
# them together.
PINNED_HASHES = list(c4.EXPECTED_INLINE_HASHES)


def _skip_reason():
    if os.environ.get("TM_C4_CONFORMANCE") != "1":
        return "the Docker export test needs TM_C4_CONFORMANCE=1"
    try:
        ok = subprocess.run(["docker", "info"], capture_output=True, timeout=60).returncode == 0
    except (OSError, subprocess.SubprocessError):
        ok = False
    return None if ok else "the Docker export test needs a running Docker (`docker info` failed)"


pytestmark = pytest.mark.skipif(bool(_skip_reason()), reason=_skip_reason() or "")


@pytest.fixture(scope="module")
def exported(tmp_path_factory):
    root = tmp_path_factory.mktemp("diagrams")
    data = SHOP.read_bytes()
    model = c4.parse(data)  # Structurizr only ever sees bytes tmreg accepts
    assert c4.problems(model) == []
    sha = hashlib.sha256(data).hexdigest()
    result = diagrams.export(root, "main", "shop", data, sha)
    site = diagrams.site_dir(root, "main", "shop", sha) / "in" / "site"
    return {"root": root, "sha": sha, "model": model, "result": result, "site": site,
            "base": f"/diagrams/main/shop/{sha}/"}


def site_views(site) -> set[str]:
    """The view keys in the site's own workspace.js (the model as base64 JSON)."""
    text = (site / "workspace.js").read_text(encoding="utf-8")
    m = re.fullmatch(r"const jsonAsString = '([A-Za-z0-9+/=]*)';\s*", text)
    assert m, text[:80]
    views = json.loads(base64.b64decode(m.group(1)))["views"]
    return {v["key"] for entries in views.values() if isinstance(entries, list) for v in entries}


class _Refs(HTMLParser):
    """Every src and href in index.html, and every attribute name."""

    def __init__(self):
        super().__init__()
        self.refs, self.attrs = [], set()

    def handle_starttag(self, tag, attrs):
        for k, v in attrs:
            self.attrs.add(k)
            if k in ("src", "href") and v:
                self.refs.append(v)


def test_real_export_is_accepted(exported):
    result, site = exported["result"], exported["site"]
    assert result["state"] == "accepted", result["message"]
    assert (site / "index.html").is_file() and (site / "workspace.js").is_file()
    target = site.parent.parent
    assert json.loads((target / "result.json").read_text()) == result
    assert sorted(p.name for p in target.iterdir()) == ["in", "result.json"]
    assert sorted(p.name for p in target.parent.iterdir()) == [exported["sha"]]  # no temp left
    assert sorted(p.name for p in (target / "in").iterdir()) == ["site", "workspace.dsl"]
    assert (target / "in" / "workspace.dsl").read_bytes() == SHOP.read_bytes()
    # --rm with --name: the named container is gone once the export ends.
    names = subprocess.run(["docker", "ps", "-a", "--filter", "name=tm-c4-export-",
                            "--format", "{{.Names}}"], capture_output=True, text=True, timeout=60)
    assert names.returncode == 0 and names.stdout.strip() == "", names.stdout


def test_the_constant_matches_the_real_export(exported):
    """c4.EXPECTED_INLINE_HASHES is what the pinned image's viewer really has."""
    html = (exported["site"] / "index.html").read_text(encoding="utf-8")
    assert tuple(diagrams.inline_script_hashes(html)) == c4.EXPECTED_INLINE_HASHES
    assert len(c4.EXPECTED_INLINE_HASHES) == 1


def test_hashes_match_index_html(exported):
    html = (exported["site"] / "index.html").read_text(encoding="utf-8")
    assert diagrams.inline_script_hashes(html) == exported["result"]["hashes"] == PINNED_HASHES
    # The same hash by a plain reading of the one inline <script> block.
    (inline,) = re.findall(r"<script>(.*?)</script>", html, re.S)
    digest = base64.b64encode(hashlib.sha256(inline.encode("utf-8")).digest()).decode()
    assert PINNED_HASHES == [f"'sha256-{digest}'"]


def test_view_url_points_at_a_key_the_site_knows(exported):
    known = site_views(exported["site"])
    assert set(exported["result"]["views"]) == known == set(exported["model"].views)
    html = (exported["site"] / "index.html").read_text(encoding="utf-8")
    # What the site's code reads: the hash, without its "#", URI-decoded, then the view with that
    # exact key; and it follows later hash changes.
    assert "diagramIdentifier = window.location.hash;" in html
    assert "diagramIdentifier = decodeURIComponent(diagramIdentifier.substring(1));" in html
    assert "const view = structurizr.workspace.findViewByKey(diagramIdentifier);" in html
    assert "window.onhashchange = function () {" in html
    base = exported["base"]
    for key in exported["result"]["views"]:
        page, fragment = diagrams.view_url(base, key).split("#", 1)
        assert page == base
        assert urllib.parse.unquote(fragment) == key and key in known


def test_the_site_needs_only_the_hashes(exported):
    """The CSP review of the export, kept as a check: nothing the CSP would block is needed."""
    site = exported["site"]
    html = (site / "index.html").read_text(encoding="utf-8")
    refs = _Refs()
    refs.feed(html)
    assert not [a for a in refs.attrs if a.startswith("on")]  # no event-handler attributes
    assert all(r.startswith("./") for r in refs.refs), refs.refs  # nothing from elsewhere
    assert "<iframe" not in html and "<base" not in html
    scripts = "\n".join(p.read_text(encoding="utf-8") for p in sorted(site.rglob("*.js")))
    for needle in ("eval(", "new Function", "Worker(", "importScripts", "WebSocket",
                   "EventSource", "sendBeacon", "fetch(", "document.write"):
        assert needle not in scripts and needle not in html, needle
    # The only Function constructor is core-js's fallback in JointJS, after globalThis and window.
    assert re.findall(r"(?<![\w$.])Function\([^)]*\)", scripts) == ["Function('return this')"]
    css = "\n".join(p.read_text(encoding="utf-8") for p in sorted(site.rglob("*.css")))
    assert "@import" not in css and "@font-face" not in css
    assert all(u.startswith(("'data:", '"data:', "data:"))
               for u in re.findall(r"url\(\s*([^)]{0,6})", css))


def test_served_behind_the_lock(exported):
    app = create_app(exported["root"], port=8765, signin_token="T0KEN")
    base = exported["base"]
    with TestClient(app, base_url=BASE) as c:
        assert c.get(base).status_code == 401
        assert c.get("/signin", params={"token": "T0KEN"}, follow_redirects=False).status_code == 303
        page = c.get(base)
        assert page.status_code == 200
        assert page.headers["content-security-policy"] == CSP.replace(
            "script-src 'self';", f"script-src 'self' {PINNED_HASHES[0]};")
        assert page.headers["x-content-type-options"] == "nosniff"
        assert page.headers["cross-origin-opener-policy"] == "same-origin"
        assert page.headers["referrer-policy"] == "no-referrer"
        # nosniff makes the browser check each type, so every file the page loads must have one.
        refs = _Refs()
        refs.feed(page.text)
        types = {".js": "text/javascript", ".css": "text/css", ".png": "image/png"}
        assert refs.refs
        for ref in refs.refs:
            r = c.get(base + ref.removeprefix("./"))
            assert r.status_code == 200, ref
            ext = os.path.splitext(ref)[1]
            assert r.headers["content-type"].split(";")[0] == types[ext], ref
        assert c.get(base + "css/structurizr-static-dark.css").status_code == 200  # dark mode
