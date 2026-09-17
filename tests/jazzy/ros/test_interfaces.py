# SPDX-License-Identifier: BSD-3-Clause
"""Jazzy import, generated type support, and CDR round-trip regression tests."""

import importlib
import os
import sys

import pytest


def test_jazzy_runtime_and_python_version():
    assert os.environ.get('ROS_DISTRO') == 'jazzy'
    assert sys.version_info >= (3, 12), sys.version
    import rclpy  # noqa: F401
    import as2_msgs  # noqa: F401


@pytest.mark.parametrize('name', [
    'as2_python_api.drone_interface_base',
    'as2_python_api.drone_interface',
    'as2_python_api.drone_interface_gps',
    'as2_python_api.drone_interface_teleop',
    'as2_python_api.behavior_actions.takeoff_behavior',
    'as2_python_api.behavior_actions.behavior_handler',
    'as2_python_api.service_clients.arming',
])
def test_python_api_imports(name):
    assert importlib.import_module(name) is not None


@pytest.mark.parametrize('kind', ['platform', 'goal', 'feedback', 'result'])
def test_generated_types_round_trip(kind):
    from as2_msgs.action import Takeoff
    from as2_msgs.msg import PlatformInfo
    from rclpy.serialization import deserialize_message, serialize_message

    if kind == 'platform':
        message = PlatformInfo()
        message.connected, message.armed, message.offboard = True, True, False
    elif kind == 'goal':
        message = Takeoff.Goal(takeoff_height=1.25, takeoff_speed=0.5)
    elif kind == 'feedback':
        message = Takeoff.Feedback(actual_takeoff_height=0.75, actual_takeoff_speed=0.25)
    else:
        message = Takeoff.Result(takeoff_success=True)
    assert deserialize_message(serialize_message(message), type(message)) == message


def test_behavior_modify_service_type_matches_generated_goal():
    from as2_msgs.action import Takeoff
    from as2_python_api.tools.utils import get_sendgoal_action_msg
    from rclpy.serialization import deserialize_message, serialize_message

    service_type = get_sendgoal_action_msg(Takeoff)
    request = service_type.Request()
    request.goal = Takeoff.Goal(takeoff_height=1.5, takeoff_speed=0.25)
    assert deserialize_message(serialize_message(request), type(request)) == request
