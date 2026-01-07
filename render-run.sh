#!/usr/bin/env bash
set -o errexit

export PATH="/opt/render/project/.render/chrome/opt/google/chrome:$PATH"

python scrap_all.py
