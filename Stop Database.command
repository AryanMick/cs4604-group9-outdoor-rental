#!/bin/zsh
set -e
cd -- "${0:A:h}"
python3 db_tools.py stop
