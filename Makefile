test: hooks
	cd registry && python3 -m unittest discover -s tests -v

# Point git at .githooks/, which refuses commits and pushes that carry risk data.
hooks:
	@git config core.hooksPath .githooks 2>/dev/null || true

# Start the web app. Run it in your own terminal; it refuses to start in a Claude Code shell.
web:
	cd webapp/backend && uv sync --frozen
	cd webapp/frontend && { [ -f node_modules/.package-lock.json ] && [ ! package-lock.json -nt node_modules/.package-lock.json ] || npm ci; } && npm run build
	cd webapp/backend && exec uv run --frozen python -m tmweb

# Run the c4 dialect through the pinned Structurizr in Docker (needs a running Docker).
test-c4:
	cd registry && TM_C4_CONFORMANCE=1 python3 -m unittest discover -s tests -p 'test_c4_conformance.py' -v

test-web:
	cd webapp/backend && uv run --frozen pytest -q
	cd webapp/frontend && npm test

.PHONY: test test-web test-c4 web hooks
