# SPDX-License-Identifier: BSD-3-Clause
"""Exercise AS2 BehaviorHandler against a mock Takeoff server, without flying."""

from functools import partial
import threading
import time
import uuid

import pytest
import rclpy
from action_msgs.msg import GoalStatus
from as2_msgs.action import Takeoff
from as2_msgs.msg import BehaviorStatus
from as2_python_api.behavior_actions.behavior_handler import BehaviorHandler
from as2_python_api.drone_interface_base import DroneInterfaceBase
from as2_python_api.tools.utils import get_sendgoal_action_msg
from rclpy.action import ActionServer, GoalResponse
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from std_srvs.srv import Trigger


@pytest.fixture
def behavior():
    rclpy.init(args=[])
    name = 'as2_jazzy_action_' + uuid.uuid4().hex[:10]
    mock = Node('mock', namespace=name)
    executor = MultiThreadedExecutor(num_threads=4)
    executor.add_node(mock)
    callback_group = ReentrantCallbackGroup()
    release = threading.Event()
    stopped = threading.Event()
    stop_spin = threading.Event()
    records = []
    errors = []

    def execute(handle):
        feedback = Takeoff.Feedback(actual_takeoff_height=0.5, actual_takeoff_speed=0.25)
        deadline = time.monotonic() + 10.0
        while not release.wait(0.05) and time.monotonic() < deadline:
            handle.publish_feedback(feedback)
        result = Takeoff.Result(takeoff_success=release.is_set() and not stopped.is_set())
        if result.takeoff_success:
            handle.succeed()
        else:
            handle.abort()
        return result

    server = ActionServer(
        mock, Takeoff, 'TakeoffBehavior', execute_callback=execute,
        goal_callback=lambda goal: (GoalResponse.ACCEPT if goal.takeoff_height >= 0.0
                                    else GoalResponse.REJECT),
        callback_group=callback_group)

    def trigger(operation, request, response):
        del request
        records.append(operation)
        if operation == 'stop':
            stopped.set()
            release.set()
        response.success = True
        return response

    services = [mock.create_service(
        Trigger, 'TakeoffBehavior/_behavior/' + operation,
        partial(trigger, operation), callback_group=callback_group)
        for operation in ('pause', 'resume', 'stop')]

    def modify(request, response):
        records.append(('modify', request.goal.takeoff_height))
        response.accepted = True
        return response

    services.append(mock.create_service(
        get_sendgoal_action_msg(Takeoff), 'TakeoffBehavior/_behavior/modify', modify,
        callback_group=callback_group))

    def spin():
        try:
            while not stop_spin.is_set():
                executor.spin_once(timeout_sec=0.05)
        except Exception as error:
            errors.append(error)

    thread = threading.Thread(target=spin, daemon=True)
    thread.start()
    drone = None
    handler = None
    try:
        drone = DroneInterfaceBase(name)
        # Discovery is bounded by the outer pytest timeout. Give all mock endpoints
        # one discovery interval before the production one-second constructor checks.
        time.sleep(0.3)
        handler = BehaviorHandler(drone, Takeoff, 'TakeoffBehavior')
        yield handler, release, records
    finally:
        release.set()
        if handler is not None:
            handler.destroy()
        if drone is not None:
            drone.shutdown()
            assert not drone.spin_thread.is_alive()
            drone.destroy_node()
        stop_spin.set()
        thread.join(timeout=3.0)
        executor.shutdown(timeout_sec=3.0)
        server.destroy()
        for service in services:
            mock.destroy_service(service)
        mock.destroy_node()
        rclpy.shutdown()
        assert not thread.is_alive()
        assert not errors, errors


def goal(height=1.0):
    return Takeoff.Goal(takeoff_height=height, takeoff_speed=0.5)


def test_goal_feedback_and_success_result(behavior):
    handler, release, _ = behavior
    assert handler.start(goal(), wait_result=False)
    deadline = time.monotonic() + 5.0
    while handler.feedback is None and time.monotonic() < deadline:
        time.sleep(0.025)
    assert handler.feedback is not None
    assert handler.feedback.actual_takeoff_height == pytest.approx(0.5)
    release.set()
    assert handler.wait_to_result()
    assert handler.result_status == GoalStatus.STATUS_SUCCEEDED
    assert handler.result.takeoff_success


def test_rejected_goal_is_reported(behavior):
    handler, _, _ = behavior
    with pytest.raises(BehaviorHandler.GoalRejected):
        handler.start(goal(-1.0), wait_result=False)


def test_pause_modify_resume_stop_services_and_failed_result(behavior):
    handler, _, records = behavior
    assert handler.start(goal(), wait_result=False)
    assert handler.pause()
    assert handler.status == BehaviorStatus.PAUSED
    assert handler.modify(goal(2.0))
    assert handler.resume(wait_result=False)
    assert handler.status == BehaviorStatus.RUNNING
    assert handler.stop()
    assert handler.status == BehaviorStatus.IDLE
    assert records == ['pause', ('modify', 2.0), 'resume', 'stop']
    assert not handler.wait_to_result()
    assert handler.result_status == GoalStatus.STATUS_ABORTED
