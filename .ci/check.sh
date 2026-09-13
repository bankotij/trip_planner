#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
project_root=$(pwd)
cd "$project_root/."
python -m pip install -r requirements.txt
cd "$project_root/."
python manage.py test
