#!/usr/bin/env bash

set -eu
set -o pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

if [[ ! -d "${SCRIPT_DIR}/venv" ]]; then
  python3 -m venv "${SCRIPT_DIR}/venv"
  "${SCRIPT_DIR}/venv/bin/pip3" install -e "${REPO_DIR}"

  echo "Run this script again"
  exit 1
fi

"${SCRIPT_DIR}/venv/bin/xemu-pgraph-run" "$@"
