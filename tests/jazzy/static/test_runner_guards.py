# SPDX-License-Identifier: BSD-3-Clause
"""Run shell preflight failures without ROS, DDS, containers, or a network."""

import os
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / 'scripts/jazzy/run_regression.sh'


def environment():
    result = os.environ.copy()
    result.pop('AS2_TEST_DOMAIN_ID', None)
    result.pop('ROS_DISTRO', None)
    return result


def test_missing_domain_fails_before_python_starts():
    result = subprocess.run(['bash', str(SCRIPT)], env=environment(),
                            capture_output=True, text=True, timeout=5)
    assert result.returncode != 0
    assert 'AS2_TEST_DOMAIN_ID' in result.stderr


@pytest.mark.parametrize('domain', ['0', '101', '-1', 'abc', '1;echo BAD', '18446744073709551617'])
def test_invalid_domain_is_rejected(domain):
    env = environment()
    env.update(AS2_TEST_DOMAIN_ID=domain, ROS_DISTRO='jazzy')
    result = subprocess.run(['bash', str(SCRIPT)], env=env,
                            capture_output=True, text=True, timeout=5)
    assert result.returncode == 2
    assert 'must be an unused integer' in result.stderr


@pytest.mark.parametrize('distro', ['', 'humble'])
def test_missing_or_wrong_distribution_is_rejected(distro):
    env = environment()
    env.update(AS2_TEST_DOMAIN_ID='71', ROS_DISTRO=distro)
    result = subprocess.run(['bash', str(SCRIPT)], env=env,
                            capture_output=True, text=True, timeout=5)
    assert result.returncode == 2
    assert 'Activate a Jazzy environment' in result.stderr


def test_zero_padded_domain_uses_decimal_not_bash_octal(tmp_path):
    # Stub only the runner's Python subprocess. This tests shell arguments and
    # environment normalization; it is not a ROS or pytest execution result.
    shim = tmp_path / 'python3'
    log = tmp_path / 'calls.txt'
    shim.write_text('#!/bin/sh\nprintf "%s\\n" "$ROS_DOMAIN_ID" >> "$GUARD_LOG"\n')
    shim.chmod(0o755)
    env = environment()
    env.update(AS2_TEST_DOMAIN_ID='008', ROS_DISTRO='jazzy',
               AS2_TEST_RESULTS_DIR=str(tmp_path / 'results'), GUARD_LOG=str(log),
               PATH=str(tmp_path) + os.pathsep + env['PATH'])
    result = subprocess.run(['bash', str(SCRIPT)], env=env,
                            capture_output=True, text=True, timeout=5)
    assert result.returncode == 0, result.stderr
    assert log.read_text().splitlines() == ['8', '8', '8']


def test_runner_includes_communication_timeout_unit_tests():
    text = SCRIPT.read_text()
    assert 'test_*timeouts.py' in text
    assert 'communication-timeouts.txt' in text
