# SPDX-License-Identifier: BSD-3-Clause
"""Actual AS2 Python interfaces with mock ROS endpoints, not a flight simulator."""

from functools import partial
import threading
import time
import uuid

import pytest
import rclpy
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data, qos_profile_system_default
from as2_msgs.msg import PlatformInfo
from as2_python_api.drone_interface_base import DroneInterfaceBase
from geometry_msgs.msg import PoseStamped, TwistStamped
from rosgraph_msgs.msg import Clock
from std_srvs.srv import SetBool


def eventually(predicate, stimulate=lambda: None, timeout=8.0):
    """Use wall time: waiting must terminate even while ROS time is stopped."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        stimulate()
        if predicate():
            return
        time.sleep(0.025)
    raise AssertionError('Condition was not reached before the wall-time deadline')


@pytest.fixture
def fleet():
    rclpy.init(args=[])
    tag = 'as2_jazzy_test_' + uuid.uuid4().hex[:10]
    names = [tag + '_0', tag + '_1']
    mock = Node(tag + '_mock')
    executor = SingleThreadedExecutor()
    executor.add_node(mock)
    stop = threading.Event()
    spin_errors = []

    def spin():
        try:
            while not stop.is_set():
                executor.spin_once(timeout_sec=0.05)
        except Exception as error:  # propagate worker failures at teardown
            spin_errors.append(error)

    thread = threading.Thread(target=spin, daemon=True)
    calls = [[], []]

    def set_bool(index, request, response):
        calls[index].append(request.data)
        response.success = True
        return response

    # Only unique test namespaces are ever targeted. No transport to any real UAV.
    services = [mock.create_service(
        SetBool, '/' + name + '/set_arming_state', partial(set_bool, i))
        for i, name in enumerate(names)]
    pose = [mock.create_publisher(
        PoseStamped, '/' + name + '/self_localization/pose', qos_profile_sensor_data)
        for name in names]
    twist = [mock.create_publisher(
        TwistStamped, '/' + name + '/self_localization/twist', qos_profile_sensor_data)
        for name in names]
    info = [mock.create_publisher(
        PlatformInfo, '/' + name + '/platform/info', qos_profile_system_default)
        for name in names]
    clock = mock.create_publisher(Clock, '/clock', 1)
    thread.start()
    drones = []
    try:
        for name in names:
            drones.append(DroneInterfaceBase(name, use_sim_time=True))
        yield names, drones, pose, twist, info, clock, calls
    finally:
        for drone in reversed(drones):
            drone.shutdown()
            assert not drone.spin_thread.is_alive(), 'AS2 spin thread leaked'
            drone.destroy_node()
        stop.set()
        thread.join(timeout=3.0)
        executor.shutdown(timeout_sec=3.0)
        for service in services:
            mock.destroy_service(service)
        mock.destroy_node()
        rclpy.shutdown()
        assert not thread.is_alive(), 'Mock executor thread leaked'
        assert not spin_errors, spin_errors


def test_two_namespaces_sensor_qos_and_frames(fleet):
    names, drones, pose_pubs, twist_pubs, info_pubs, _, _ = fleet
    for name, drone in zip(names, drones):
        assert drone.get_namespace() == '/' + name
        assert drone.base_frame_id == name + '/base_link'
        assert drone.earth_frame_id == 'earth'

    def publish(x0=1.0):
        for i in range(2):
            pose = PoseStamped()
            pose.header.frame_id = 'earth'
            pose.pose.orientation.w = 1.0
            pose.pose.position.x = x0 if i == 0 else 2.0
            twist = TwistStamped()
            twist.header.frame_id = 'earth'
            twist.twist.linear.x = 0.25 if i == 0 else -0.5
            info = PlatformInfo()
            info.connected = True
            info.armed = i == 0
            pose_pubs[i].publish(pose)
            twist_pubs[i].publish(twist)
            info_pubs[i].publish(info)

    def expected():
        return (drones[0].position[0] == 1.0 and drones[1].position[0] == 2.0
                and drones[0].speed[0] == 0.25 and drones[1].speed[0] == -0.5
                and drones[0].info['armed'] and not drones[1].info['armed']
                and all(d.info['connected'] for d in drones))

    eventually(expected, publish)
    eventually(lambda: drones[0].position[0] == 8.0, lambda: publish(8.0))
    # Continue publishing for a finite observation window, not just one read.
    deadline = time.monotonic() + 0.5
    while time.monotonic() < deadline:
        publish(8.0)
        assert drones[1].position[0] == 2.0
        time.sleep(0.025)


def test_arming_service_is_routed_only_to_the_selected_namespace(fleet):
    _, drones, _, _, _, _, calls = fleet
    assert drones[0].arm()
    assert calls == [[True], []]
    assert drones[1].disarm()
    assert calls == [[True], [False]]
    assert drones[0].disarm()
    assert calls == [[True, False], [False]]


def test_sim_clock_advances_pauses_and_accepts_a_backward_jump(fleet):
    _, drones, _, _, _, clock_pub, _ = fleet
    for seconds in (12, 21, 3):
        clock = Clock()
        clock.clock.sec = seconds
        eventually(
            lambda: all(d.get_clock().now().nanoseconds == seconds * 10**9 for d in drones),
            lambda: clock_pub.publish(clock))
        time.sleep(0.2)
        assert all(d.get_clock().now().nanoseconds == seconds * 10**9 for d in drones)


def test_two_arming_requests_complete_concurrently(fleet):
    from concurrent.futures import ThreadPoolExecutor

    _, drones, _, _, _, _, calls = fleet
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(drone.arm) for drone in drones]
        assert all(future.result(timeout=8.0) for future in futures)
    assert calls == [[True], [True]]
