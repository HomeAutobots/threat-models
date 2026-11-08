test: hooks
	cd registry && python3 -m unittest discover -s tests -v

# Point git at .githooks/, which refuses commits and pushes that carry risk data.
hooks:
	@git config core.hooksPath .githooks 2>/dev/null || true

.PHONY: test hooks
