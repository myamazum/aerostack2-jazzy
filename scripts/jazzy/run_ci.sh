#!/usr/bin/env bash
# SPDX-License-Identifier: BSD-3-Clause
# Native apt-based container path, not the Pixi package-build path.
set -eo pipefail
: "${AEROSTACK2_WORKSPACE:?Missing workspace}"
: "${AEROSTACK2_PATH:?Missing source path}"
: "${AS2_TEST_RESULTS_DIR:?Missing artifact directory}"
: "${AS2_TEST_DOMAIN_ID:?Missing unused test domain}"
source /opt/ros/jazzy/setup.bash
source "$AEROSTACK2_WORKSPACE/install/setup.bash"
export ROS_DOMAIN_ID="$AS2_TEST_DOMAIN_ID"
export ROS_LOCALHOST_ONLY=1
export ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
mkdir -p "$AS2_TEST_RESULTS_DIR"
cd "$AEROSTACK2_WORKSPACE"
status=0
# Bound legacy tests as a group as well as CTest tests individually.
timeout --signal=TERM --kill-after=30s 25m \
  colcon test --executor sequential --return-code-on-test-failure \
  --event-handlers console_direct+ --ctest-args --timeout 120 || status=1
colcon test-result --verbose 2>&1 | tee "$AS2_TEST_RESULTS_DIR/upstream-test-result.txt" || status=1
python3 - <<'PY'
import os
from pathlib import Path
import shutil
root = Path(os.environ['AEROSTACK2_WORKSPACE'])
out = Path(os.environ['AS2_TEST_RESULTS_DIR']) / 'upstream'
for path in (root / 'build').rglob('*.xml'):
    if 'test_results' in path.parts or path.name == 'pytest.xml':
        target = out / path.relative_to(root)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
PY
bash "$AEROSTACK2_PATH/scripts/jazzy/run_regression.sh" || status=1
exit "$status"
