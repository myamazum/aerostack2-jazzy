"""HTTP server and CLI for the Aerostack2 swarm web UI."""

from __future__ import annotations

import argparse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
from typing import Any

from ament_index_python.packages import get_package_share_directory
import rclpy
from rclpy.executors import MultiThreadedExecutor

from .bridge import SwarmBridge


MAX_REQUEST_BODY = 64 * 1024
LOOPBACK_HOSTS = {'127.0.0.1', 'localhost', '::1'}


def _load_config(path: str | None) -> dict[str, Any]:
    if not path:
        return {}
    with open(path, 'r', encoding='utf-8') as stream:
        data = json.load(stream)
    if not isinstance(data, dict):
        raise ValueError('config root must be a JSON object')
    return data


def _validate_groups(groups: Any) -> dict[str, list[str]]:
    if groups is None:
        return {}
    if not isinstance(groups, dict):
        raise ValueError('groups must be an object mapping names to drone lists')
    result: dict[str, list[str]] = {}
    for group, members in groups.items():
        if not isinstance(group, str) or not group.strip():
            raise ValueError('group names must be non-empty strings')
        if not isinstance(members, list) or not all(isinstance(x, str) for x in members):
            raise ValueError(f'group {group!r} must contain a list of namespace strings')
        normalized = []
        for raw in members:
            name = raw.strip().strip('/')
            if name and name not in normalized:
                normalized.append(name)
        result[group.strip()] = normalized
    return result


def _find_static_index() -> Path:
    share = Path(get_package_share_directory('as2_swarm_web_ui'))
    return share / 'static' / 'index.html'


class SwarmHTTPServer(ThreadingHTTPServer):
    """Threaded HTTP server carrying bridge/config references."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        server_address: tuple[str, int],
        handler_class: type[BaseHTTPRequestHandler],
        bridge: SwarmBridge,
        groups: dict[str, list[str]],
        index_html: bytes,
    ) -> None:
        super().__init__(server_address, handler_class)
        self.bridge = bridge
        self.groups = groups
        self.index_html = index_html


class SwarmRequestHandler(BaseHTTPRequestHandler):
    """Serve the UI and a deliberately small same-origin JSON API."""

    server: SwarmHTTPServer

    def log_message(self, fmt: str, *args: Any) -> None:
        self.server.bridge.get_logger().info('HTTP ' + (fmt % args))

    def _security_headers(self) -> None:
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header(
            'Content-Security-Policy',
            "default-src 'self'; style-src 'self' 'unsafe-inline'; "
            "script-src 'self' 'unsafe-inline'; connect-src 'self'; "
            "img-src 'self' data:; frame-ancestors 'none'",
        )
        self.send_header('Cache-Control', 'no-store')

    def _send_json(self, status: int, payload: Any) -> None:
        body = json.dumps(payload, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self._security_headers()
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = self.path.split('?', 1)[0]
        if path == '/':
            body = self.server.index_html
            self.send_response(HTTPStatus.OK)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self._security_headers()
            self.end_headers()
            self.wfile.write(body)
            return
        if path == '/api/fleet':
            self._send_json(HTTPStatus.OK, self.server.bridge.snapshot())
            return
        if path == '/api/config':
            self._send_json(
                HTTPStatus.OK,
                {
                    'drones': self.server.bridge.drone_names,
                    'groups': self.server.groups,
                    'command_mode': 'concurrent_unicast',
                    'synchronization_guarantee': False,
                    'capabilities': [
                        'arm', 'disarm', 'offboard', 'manual', 'takeoff', 'land',
                        'go_to', 'emergency_land', 'emergency_hover', 'kill_switch',
                    ],
                },
            )
            return
        self._send_json(HTTPStatus.NOT_FOUND, {'error': 'not found'})

    def do_POST(self) -> None:
        path = self.path.split('?', 1)[0]
        if path != '/api/command':
            self._send_json(HTTPStatus.NOT_FOUND, {'error': 'not found'})
            return
        content_type = self.headers.get('Content-Type', '')
        if not content_type.lower().startswith('application/json'):
            self._send_json(
                HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
                {'error': 'Content-Type must be application/json'},
            )
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            self._send_json(HTTPStatus.BAD_REQUEST, {'error': 'invalid Content-Length'})
            return
        if length <= 0 or length > MAX_REQUEST_BODY:
            self._send_json(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                {'error': 'request body must be between 1 and 65536 bytes'},
            )
            return
        try:
            payload = json.loads(self.rfile.read(length).decode('utf-8'))
            if not isinstance(payload, dict):
                raise ValueError('request must be a JSON object')
            action = str(payload.get('action', '')).strip()
            targets = self._resolve_targets(payload)
            params = payload.get('params') or {}
            if not isinstance(params, dict):
                raise ValueError('params must be a JSON object')
            result = self.server.bridge.execute(
                action, targets, params, confirm=payload.get('confirm')
            )
            status = HTTPStatus.OK if result.get('ok') else HTTPStatus.CONFLICT
            self._send_json(status, result)
        except (KeyError, TypeError, ValueError) as error:
            self._send_json(HTTPStatus.BAD_REQUEST, {'error': str(error)})
        except Exception as error:
            self.server.bridge.get_logger().error(f'command failed: {error!r}')
            self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {'error': str(error)})

    def _resolve_targets(self, payload: dict[str, Any]) -> list[str]:
        if 'targets' in payload:
            targets = payload['targets']
            if not isinstance(targets, list) or not all(isinstance(x, str) for x in targets):
                raise ValueError('targets must be a list of namespace strings')
            return targets
        group = payload.get('group')
        if group == 'all':
            return self.server.bridge.drone_names
        if isinstance(group, str) and group in self.server.groups:
            return self.server.groups[group]
        raise ValueError('provide targets or a configured group')


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Serve an HTML fleet UI backed by Aerostack2 ROS 2 endpoints.'
    )
    parser.add_argument('--config', help='JSON fleet configuration file')
    parser.add_argument('--drones', nargs='*', help='AS2 namespaces to manage')
    parser.add_argument(
        '--discover',
        action='store_true',
        help='also discover namespaces exposing /<name>/set_arming_state',
    )
    parser.add_argument(
        '--discovery-wait', type=float, default=2.0, help='ROS graph discovery wait [s]'
    )
    parser.add_argument('--host', default='127.0.0.1', help='HTTP bind host')
    parser.add_argument('--port', type=int, default=8080, help='HTTP TCP port')
    parser.add_argument(
        '--allow-remote',
        action='store_true',
        help='allow a non-loopback bind; no authentication is provided by this prototype',
    )
    parser.add_argument('--stale-after', type=float, help='telemetry stale threshold [s]')
    parser.add_argument('--earth-frame', help='default GoTo reference frame')
    parser.add_argument('--use-sim-time', action='store_true')
    return parser.parse_args()


def main() -> None:
    """CLI entry point."""
    args = _parse_args()
    if args.host not in LOOPBACK_HOSTS and not args.allow_remote:
        raise SystemExit(
            'Refusing non-loopback bind without --allow-remote. '
            'The prototype has no authentication layer.'
        )
    if not 1 <= args.port <= 65535:
        raise SystemExit('--port must be in the range 1..65535')

    config = _load_config(args.config)
    config_drones = config.get('drones', [])
    if config_drones and (
        not isinstance(config_drones, list)
        or not all(isinstance(item, str) for item in config_drones)
    ):
        raise SystemExit('config drones must be a list of namespace strings')
    drones = list(config_drones)
    if args.drones:
        drones.extend(args.drones)
    groups = _validate_groups(config.get('groups'))
    stale_after_s = (
        args.stale_after
        if args.stale_after is not None
        else float(config.get('stale_after_s', 2.0))
    )
    earth_frame = args.earth_frame or str(config.get('earth_frame', 'earth'))
    if stale_after_s <= 0.0:
        raise SystemExit('stale threshold must be positive')

    rclpy.init(args=[])
    bridge = SwarmBridge(
        drones,
        stale_after_s=stale_after_s,
        earth_frame=earth_frame,
        use_sim_time=args.use_sim_time,
    )
    executor = None
    spin_thread = None
    httpd = None
    try:
        if args.discover or not bridge.drone_names:
            discovered = bridge.discover_drones(args.discovery_wait)
            if discovered:
                bridge.get_logger().info('Discovered AS2 namespaces: ' + ', '.join(discovered))
        if not bridge.drone_names:
            raise RuntimeError(
                'No AS2 namespaces configured or discovered. Use --drones or --config.'
            )

        known = set(bridge.drone_names)
        for group, members in groups.items():
            unknown = sorted(set(members) - known)
            if unknown:
                raise RuntimeError(
                    f'group {group!r} refers to unknown namespace(s): {", ".join(unknown)}'
                )

        executor = MultiThreadedExecutor(num_threads=max(2, min(8, len(known) + 1)))
        executor.add_node(bridge)
        spin_thread = threading.Thread(target=executor.spin, daemon=True)
        spin_thread.start()

        index_html = _find_static_index().read_bytes()
        httpd = SwarmHTTPServer(
            (args.host, args.port), SwarmRequestHandler, bridge, groups, index_html
        )
        bridge.get_logger().info(
            f'Swarm web UI: http://{args.host}:{args.port} '
            f'({len(known)} namespace(s), concurrent ROS fan-out; not RF broadcast)'
        )
        if args.host not in LOOPBACK_HOSTS:
            bridge.get_logger().warning(
                'Remote HTTP access is enabled without authentication. '
                'Restrict access at the network boundary.'
            )
        httpd.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        if httpd is not None:
            httpd.shutdown()
            httpd.server_close()
        if executor is not None:
            executor.shutdown(timeout_sec=3.0)
        if spin_thread is not None:
            spin_thread.join(timeout=3.0)
        bridge.destroy_bridge()
        bridge.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
