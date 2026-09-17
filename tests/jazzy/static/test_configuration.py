# SPDX-License-Identifier: BSD-3-Clause
"""Source-only checks; these do not establish ROS build or flight correctness."""

from pathlib import Path
import tomllib

ROOT = Path(__file__).resolve().parents[3]


def manifest():
    return tomllib.loads((ROOT / 'pixi.toml').read_text(encoding='utf-8'))


def test_jazzy_is_default_and_humble_is_retained():
    env = manifest()['environments']
    assert env['default'] == ['jazzy']
    assert env['jazzy'] == ['jazzy']
    assert env['humble'] == ['humble']


def test_distro_channels_are_not_mixed():
    data = manifest()
    assert data['feature']['jazzy']['channels'] == ['robostack-jazzy']
    assert data['feature']['humble']['channels'] == ['robostack-humble']
    assert not any('robostack-' in c for c in data['workspace']['channels'])
    assert data['environments']['jazzy-tests'] == ['jazzy', 'jazzy-tests']


def test_docker_wrappers_select_local_jazzy_image():
    tasks = manifest()['tasks']
    assert tasks['docker:build'].endswith('build jazzy')
    assert tasks['docker:run'].endswith('aerostack2/jazzy')
    assert tasks['docker:build-humble'].endswith('build humble')
    assert tasks['docker:run-humble'].endswith('aerostack2/humble')
    assert 'docker:pull-humble' in tasks


def test_rosdep_is_explicit_and_does_not_continue_after_errors():
    text = (ROOT / 'docker/jazzy/Dockerfile').read_text()
    assert 'FROM osrf/ros:jazzy-desktop' in text
    command = next(line for line in text.splitlines() if 'rosdep install ' in line)
    assert '--rosdistro jazzy' in command
    assert '-r' not in command.split()
    assert 'ARG BUILD_TESTING=ON' in text
    assert '-DBUILD_TESTING=${BUILD_TESTING}' in text


def test_tests_do_not_call_radio_or_udp_transport():
    # A source guard, not a security sandbox. Real runtime tests use generated namespaces.
    for path in (ROOT / 'tests/jazzy/ros').glob('*.py'):
        text = path.read_text()
        assert 'import cflib' not in text
        assert 'radio://' not in text
        assert 'udp://' not in text


def test_runtime_runner_requires_explicit_isolated_domain():
    text = (ROOT / 'scripts/jazzy/run_regression.sh').read_text()
    assert 'AS2_TEST_DOMAIN_ID:?' in text
    assert 'ROS_DOMAIN_ID="$AS2_TEST_DOMAIN_ID"' in text
    assert '--timeout-method=thread' in text
    assert 'AS2_JAZZY_ISOLATED_TESTS=1' in text
