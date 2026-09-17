#!/usr/bin/env bash
# SPDX-License-Identifier: BSD-3-Clause
# Run only on an unused, isolated ROS domain. No aircraft is needed.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
: "${AS2_TEST_DOMAIN_ID:?Set an unused AS2_TEST_DOMAIN_ID (for example 71)}"
if [[ ! "$AS2_TEST_DOMAIN_ID" =~ ^[0-9]{1,3}$ ]]; then
  echo "AS2_TEST_DOMAIN_ID must be an unused integer in 1..100" >&2
  exit 2
fi
DOMAIN=$((10#$AS2_TEST_DOMAIN_ID))
if (( DOMAIN < 1 || DOMAIN > 100 )); then
  echo "AS2_TEST_DOMAIN_ID must be an unused integer in 1..100" >&2
  exit 2
fi
AS2_TEST_DOMAIN_ID="$DOMAIN"
if [[ "${ROS_DISTRO:-}" != jazzy ]]; then
  echo "Activate a Jazzy environment first; ROS_DISTRO=${ROS_DISTRO:-unset}" >&2
  exit 2
fi
export ROS_DOMAIN_ID="$AS2_TEST_DOMAIN_ID"
export ROS_LOCALHOST_ONLY=1
export ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
export AS2_JAZZY_ISOLATED_TESTS=1
RESULTS="${AS2_TEST_RESULTS_DIR:-$ROOT/test-results/jazzy}"
mkdir -p "$RESULTS"
RESULTS="$(cd "$RESULTS" && pwd)"
python3 - <<'PY'
import importlib
import os
import sys
from pathlib import Path
assert sys.version_info >= (3, 12), sys.version
for name in ('pytest', 'pytest_timeout', 'rclpy', 'as2_msgs', 'as2_python_api', 'rosgraph_msgs'):
    module = importlib.import_module(name)
    print(f'{name}: {getattr(module, "__file__", None)}')
# Catch the common accidental Humble underlay, not all possible ABI mismatches.
for variable in ('AMENT_PREFIX_PATH', 'CMAKE_PREFIX_PATH', 'PYTHONPATH', 'LD_LIBRARY_PATH'):
    assert '/opt/ros/humble' not in os.environ.get(variable, ''), variable
print('python:', sys.executable)
print('ROS_DOMAIN_ID:', os.environ['ROS_DOMAIN_ID'])
print('RMW_IMPLEMENTATION:', os.environ.get('RMW_IMPLEMENTATION', '(default)'))
PY
cd "$ROOT"
if ! env PYTHONPATH="$ROOT/as2_python_api${PYTHONPATH:+:$PYTHONPATH}" \
  python3 -m unittest discover -s as2_python_api/as2_python_api/test \
  -p 'test_*timeouts.py' -v 2>&1 | tee "$RESULTS/communication-timeouts.txt"; then
  exit 1
fi
python3 -m pytest -q tests/jazzy/static tests/jazzy/ros \
  --timeout=30 --timeout-method=thread \
  --junitxml="$RESULTS/regression.xml"
