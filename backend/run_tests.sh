#!/usr/bin/env bash
# Runs all tests (Mac/Linux). Installs pytest the first time.
cd "$(dirname "$0")"
python3 -m pip install --quiet -r requirements.txt
python3 -m pytest -v
