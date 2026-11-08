test:
	cd registry && python3 -m unittest discover -s tests -v

.PHONY: test
