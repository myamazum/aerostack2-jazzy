# SPDX-License-Identifier: BSD-3-Clause
"""Never connect these tests to an operating robot's ROS domain."""

import os

import pytest


@pytest.fixture(scope='session', autouse=True)
def require_isolated_domain():
    if os.environ.get('AS2_JAZZY_ISOLATED_TESTS') != '1':
        pytest.fail('Run scripts/jazzy/run_regression.sh with an unused AS2_TEST_DOMAIN_ID')
    assert os.environ.get('ROS_DOMAIN_ID'), 'An explicit, unused ROS domain is required'
    assert os.environ.get('ROS_DISTRO') == 'jazzy'
