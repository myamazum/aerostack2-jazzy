"""ROS 2 bridge for browser-driven Aerostack2 fleet operations."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import partial
import threading
import time
from typing import Any, Iterable

from as2_msgs.action import GoToWaypoint, Land, Takeoff
from as2_msgs.msg import AlertEvent, PlatformInfo, YawMode
from geometry_msgs.msg import PoseStamped, TwistStamped
import rclpy
from rclpy.action import ActionClient
from rclpy.node import Node
from rclpy.parameter import Parameter
from rclpy.qos import qos_profile_sensor_data, qos_profile_system_default
from std_srvs.srv import SetBool


STATE_LABELS = {
    -1: 'EMERGENCY',
    0: 'DISARMED',
    1: 'LANDED',
    2: 'TAKING_OFF',
    3: 'FLYING',
    4: 'LANDING',
}


@dataclass
class DroneState:
    """Last state received for one Aerostack2 namespace."""

    connected: bool = False
    armed: bool = False
    offboard: bool = False
    state: int = 0
    yaw_mode: int = 0
    control_mode: int = -1
    position: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    velocity: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    info_seen: bool = False
    pose_seen: bool = False
    twist_seen: bool = False
    last_seen_monotonic: float | None = None


@dataclass
class DroneEndpoints:
    """ROS endpoints used to control one namespace."""

    arm: Any
    offboard: Any
    takeoff: ActionClient
    land: ActionClient
    go_to: ActionClient
    alert: Any


class SwarmBridge(Node):
    """Aggregate fleet status and fan commands out to AS2 namespaces."""

    def __init__(
        self,
        drones: Iterable[str],
        *,
        stale_after_s: float = 2.0,
        earth_frame: str = 'earth',
        use_sim_time: bool = False,
    ) -> None:
        super().__init__('as2_swarm_web_bridge')
        self.set_parameters(
            [Parameter('use_sim_time', Parameter.Type.BOOL, bool(use_sim_time))]
        )
        self.stale_after_s = float(stale_after_s)
        self.earth_frame = earth_frame.lstrip('/') or 'earth'
        self._state_lock = threading.Lock()
        self._command_lock = threading.Lock()
        self._states: dict[str, DroneState] = {}
        self._endpoints: dict[str, DroneEndpoints] = {}
        self._subscriptions: list[Any] = []
        self._clients: list[Any] = []
        self._publishers: list[Any] = []
        self._action_clients: list[ActionClient] = []

        for name in self._normalize_names(drones):
            self.add_drone(name)

    @staticmethod
    def _normalize_names(drones: Iterable[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for raw in drones:
            name = str(raw).strip().strip('/')
            if name and name not in seen:
                seen.add(name)
                result.append(name)
        return result

    @property
    def drone_names(self) -> list[str]:
        """Return known namespaces in stable order."""
        with self._state_lock:
            return list(self._states.keys())

    def add_drone(self, name: str) -> None:
        """Register ROS endpoints for one AS2 namespace."""
        name = name.strip().strip('/')
        if not name:
            raise ValueError('drone namespace must not be empty')
        if name in self._states:
            return

        with self._state_lock:
            self._states[name] = DroneState()

        prefix = f'/{name}'
        self._subscriptions.extend(
            [
                self.create_subscription(
                    PlatformInfo,
                    f'{prefix}/platform/info',
                    partial(self._on_info, name),
                    qos_profile_system_default,
                ),
                self.create_subscription(
                    PoseStamped,
                    f'{prefix}/self_localization/pose',
                    partial(self._on_pose, name),
                    qos_profile_sensor_data,
                ),
                self.create_subscription(
                    TwistStamped,
                    f'{prefix}/self_localization/twist',
                    partial(self._on_twist, name),
                    qos_profile_sensor_data,
                ),
            ]
        )

        arm = self.create_client(SetBool, f'{prefix}/set_arming_state')
        offboard = self.create_client(SetBool, f'{prefix}/set_offboard_mode')
        takeoff = ActionClient(self, Takeoff, f'{prefix}/TakeoffBehavior')
        land = ActionClient(self, Land, f'{prefix}/LandBehavior')
        go_to = ActionClient(self, GoToWaypoint, f'{prefix}/GoToBehavior')
        alert = self.create_publisher(
            AlertEvent, f'{prefix}/alert_event', qos_profile_system_default
        )
        self._clients.extend([arm, offboard])
        self._action_clients.extend([takeoff, land, go_to])
        self._publishers.append(alert)
        self._endpoints[name] = DroneEndpoints(
            arm=arm,
            offboard=offboard,
            takeoff=takeoff,
            land=land,
            go_to=go_to,
            alert=alert,
        )

    def discover_drones(self, wait_s: float = 2.0) -> list[str]:
        """Discover namespaces exposing the standard AS2 arming service."""
        deadline = time.monotonic() + max(0.0, wait_s)
        found: set[str] = set()
        while rclpy.ok():
            for service_name, service_types in self.get_service_names_and_types():
                if not service_name.endswith('/set_arming_state'):
                    continue
                if 'std_srvs/srv/SetBool' not in service_types:
                    continue
                namespace = service_name[: -len('/set_arming_state')].strip('/')
                if namespace:
                    found.add(namespace)
            if found or time.monotonic() >= deadline:
                break
            time.sleep(0.1)
        for name in sorted(found):
            self.add_drone(name)
        return sorted(found)

    def _mark_seen(self, name: str) -> DroneState:
        state = self._states[name]
        state.last_seen_monotonic = time.monotonic()
        return state

    def _on_info(self, name: str, msg: PlatformInfo) -> None:
        with self._state_lock:
            state = self._mark_seen(name)
            state.connected = bool(msg.connected)
            state.armed = bool(msg.armed)
            state.offboard = bool(msg.offboard)
            state.state = int(msg.status.state)
            state.yaw_mode = int(msg.current_control_mode.yaw_mode)
            state.control_mode = int(msg.current_control_mode.control_mode)
            state.info_seen = True

    def _on_pose(self, name: str, msg: PoseStamped) -> None:
        with self._state_lock:
            state = self._mark_seen(name)
            state.position = [
                float(msg.pose.position.x),
                float(msg.pose.position.y),
                float(msg.pose.position.z),
            ]
            state.pose_seen = True

    def _on_twist(self, name: str, msg: TwistStamped) -> None:
        with self._state_lock:
            state = self._mark_seen(name)
            state.velocity = [
                float(msg.twist.linear.x),
                float(msg.twist.linear.y),
                float(msg.twist.linear.z),
            ]
            state.twist_seen = True

    def snapshot(self) -> dict[str, Any]:
        """Return JSON-serializable fleet state."""
        now = time.monotonic()
        drones: list[dict[str, Any]] = []
        with self._state_lock:
            for name, state in self._states.items():
                age = (
                    None
                    if state.last_seen_monotonic is None
                    else max(0.0, now - state.last_seen_monotonic)
                )
                stale = age is None or age > self.stale_after_s
                drones.append(
                    {
                        'name': name,
                        'connected': state.connected,
                        'armed': state.armed,
                        'offboard': state.offboard,
                        'state': state.state,
                        'state_label': STATE_LABELS.get(state.state, str(state.state)),
                        'yaw_mode': state.yaw_mode,
                        'control_mode': state.control_mode,
                        'position': list(state.position),
                        'velocity': list(state.velocity),
                        'info_seen': state.info_seen,
                        'pose_seen': state.pose_seen,
                        'twist_seen': state.twist_seen,
                        'age_s': None if age is None else round(age, 3),
                        'stale': stale,
                    }
                )
        return {
            'drones': drones,
            'count': len(drones),
            'stale_after_s': self.stale_after_s,
        }

    def execute(
        self,
        action: str,
        targets: Iterable[str],
        params: dict[str, Any] | None = None,
        *,
        confirm: str | None = None,
    ) -> dict[str, Any]:
        """Execute one serialized fleet command batch."""
        names = self._normalize_names(targets)
        unknown = [name for name in names if name not in self._endpoints]
        if not names:
            raise ValueError('at least one target is required')
        if unknown:
            raise ValueError(f'unknown target(s): {", ".join(unknown)}')

        params = params or {}
        with self._command_lock:
            if action == 'arm':
                return self._service_bool_batch('arm', names, 'arm', True)
            if action == 'disarm':
                return self._service_bool_batch('disarm', names, 'arm', False)
            if action == 'offboard':
                return self._service_bool_batch('offboard', names, 'offboard', True)
            if action == 'manual':
                return self._service_bool_batch('manual', names, 'offboard', False)
            if action == 'takeoff':
                return self._takeoff_batch(names, params)
            if action == 'land':
                return self._land_batch(names, params)
            if action == 'go_to':
                return self._go_to_batch(names, params)
            if action == 'emergency_land':
                return self._alert_batch(names, AlertEvent.EMERGENCY_LAND, action)
            if action == 'emergency_hover':
                return self._alert_batch(names, AlertEvent.EMERGENCY_HOVER, action)
            if action == 'kill_switch':
                if confirm != 'KILL':
                    raise ValueError('kill_switch requires confirm="KILL"')
                return self._alert_batch(names, AlertEvent.KILL_SWITCH, action)
        raise ValueError(f'unsupported action: {action}')

    @staticmethod
    def _dispatch_span_ms(stamps_ns: list[int]) -> float:
        if len(stamps_ns) < 2:
            return 0.0
        return round((max(stamps_ns) - min(stamps_ns)) / 1_000_000.0, 3)

    @staticmethod
    def _wait_futures(futures: dict[str, Any], timeout_s: float) -> set[str]:
        pending = set(futures)
        deadline = time.monotonic() + timeout_s
        while pending and time.monotonic() < deadline:
            for name in list(pending):
                if futures[name].done():
                    pending.remove(name)
            if pending:
                time.sleep(0.01)
        return pending

    def _service_bool_batch(
        self, action: str, names: list[str], endpoint_attr: str, value: bool
    ) -> dict[str, Any]:
        unavailable = [
            name
            for name in names
            if not getattr(self._endpoints[name], endpoint_attr).wait_for_service(
                timeout_sec=0.5
            )
        ]
        if unavailable:
            return self._preflight_failure(action, names, unavailable, 'service unavailable')

        futures: dict[str, Any] = {}
        stamps: list[int] = []
        for name in names:
            request = SetBool.Request()
            request.data = value
            stamps.append(time.perf_counter_ns())
            futures[name] = getattr(self._endpoints[name], endpoint_attr).call_async(request)

        pending = self._wait_futures(futures, timeout_s=3.0)
        results: dict[str, Any] = {}
        for name in names:
            if name in pending:
                results[name] = {'ok': False, 'error': 'response timeout'}
                continue
            future = futures[name]
            error = future.exception()
            if error is not None:
                results[name] = {'ok': False, 'error': str(error)}
                continue
            response = future.result()
            results[name] = {
                'ok': bool(response.success),
                'message': str(response.message),
            }
        return self._batch_result(action, names, results, stamps)

    def _action_batch(
        self,
        action: str,
        names: list[str],
        endpoint_attr: str,
        goals: dict[str, Any],
    ) -> dict[str, Any]:
        unavailable = [
            name
            for name in names
            if not getattr(self._endpoints[name], endpoint_attr).wait_for_server(
                timeout_sec=0.5
            )
        ]
        if unavailable:
            return self._preflight_failure(
                action, names, unavailable, 'action server unavailable'
            )

        futures: dict[str, Any] = {}
        stamps: list[int] = []
        for name in names:
            stamps.append(time.perf_counter_ns())
            futures[name] = getattr(self._endpoints[name], endpoint_attr).send_goal_async(
                goals[name]
            )

        pending = self._wait_futures(futures, timeout_s=3.0)
        results: dict[str, Any] = {}
        for name in names:
            if name in pending:
                results[name] = {
                    'ok': False,
                    'accepted': None,
                    'error': 'goal acknowledgement timeout; terminal state is unknown',
                }
                continue
            future = futures[name]
            error = future.exception()
            if error is not None:
                results[name] = {'ok': False, 'accepted': False, 'error': str(error)}
                continue
            goal_handle = future.result()
            accepted = bool(goal_handle is not None and goal_handle.accepted)
            results[name] = {'ok': accepted, 'accepted': accepted}
        return self._batch_result(action, names, results, stamps)

    def _takeoff_batch(self, names: list[str], params: dict[str, Any]) -> dict[str, Any]:
        height = float(params.get('height', 1.0))
        speed = float(params.get('speed', 0.5))
        if height <= 0.0 or speed <= 0.0:
            raise ValueError('takeoff height and speed must be positive')
        goals: dict[str, Any] = {}
        for name in names:
            goal = Takeoff.Goal()
            goal.takeoff_height = height
            goal.takeoff_speed = speed
            goals[name] = goal
        return self._action_batch('takeoff', names, 'takeoff', goals)

    def _land_batch(self, names: list[str], params: dict[str, Any]) -> dict[str, Any]:
        speed = float(params.get('speed', 0.5))
        if speed <= 0.0:
            raise ValueError('landing speed must be positive')
        goals: dict[str, Any] = {}
        for name in names:
            goal = Land.Goal()
            goal.land_speed = speed
            goals[name] = goal
        return self._action_batch('land', names, 'land', goals)

    def _go_to_batch(self, names: list[str], params: dict[str, Any]) -> dict[str, Any]:
        x = float(params['x'])
        y = float(params['y'])
        z = float(params['z'])
        speed = float(params.get('speed', 0.5))
        if speed <= 0.0:
            raise ValueError('go_to speed must be positive')
        frame_id = str(params.get('frame_id') or self.earth_frame).lstrip('/')
        stamp = self.get_clock().now().to_msg()
        goals: dict[str, Any] = {}
        for name in names:
            goal = GoToWaypoint.Goal()
            goal.target_pose.header.stamp = stamp
            goal.target_pose.header.frame_id = frame_id
            goal.target_pose.point.x = x
            goal.target_pose.point.y = y
            goal.target_pose.point.z = z
            goal.max_speed = speed
            goal.yaw.mode = YawMode.KEEP_YAW
            goals[name] = goal
        return self._action_batch('go_to', names, 'go_to', goals)

    def _alert_batch(self, names: list[str], alert: int, action: str) -> dict[str, Any]:
        msg = AlertEvent()
        msg.alert = alert
        stamps: list[int] = []
        results: dict[str, Any] = {name: {'ok': True} for name in names}
        for repeat in range(5):
            for name in names:
                if repeat == 0:
                    stamps.append(time.perf_counter_ns())
                self._endpoints[name].alert.publish(msg)
            if repeat < 4:
                time.sleep(0.01)
        return self._batch_result(action, names, results, stamps)

    def _preflight_failure(
        self, action: str, names: list[str], unavailable: list[str], reason: str
    ) -> dict[str, Any]:
        results = {
            name: (
                {'ok': False, 'error': reason}
                if name in unavailable
                else {'ok': False, 'error': 'batch not dispatched because preflight failed'}
            )
            for name in names
        }
        return {
            'ok': False,
            'action': action,
            'targets': names,
            'mode': 'concurrent_unicast',
            'dispatch_span_ms': None,
            'preflight_failed': True,
            'results': results,
        }

    def _batch_result(
        self,
        action: str,
        names: list[str],
        results: dict[str, Any],
        stamps: list[int],
    ) -> dict[str, Any]:
        return {
            'ok': all(bool(item.get('ok')) for item in results.values()),
            'action': action,
            'targets': names,
            'mode': 'concurrent_unicast',
            'dispatch_span_ms': self._dispatch_span_ms(stamps),
            'preflight_failed': False,
            'results': results,
        }

    def destroy_bridge(self) -> None:
        """Destroy explicitly-created ROS entities before destroying the node."""
        for action_client in self._action_clients:
            action_client.destroy()
        for client in self._clients:
            self.destroy_client(client)
        for publisher in self._publishers:
            self.destroy_publisher(publisher)
        for subscription in self._subscriptions:
            self.destroy_subscription(subscription)
