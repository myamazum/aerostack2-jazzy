# as2_swarm_web_ui

Browser-based fleet status and group command prototype for Aerostack2.

The package adds a fleet-level operator interface without replacing an aerial-platform backend. In
particular, it does not require `as2_platform_crazyswarm` and does not change the current
`as2_platform_crazyflie` / `crazyflie_cpp` transport path.

## Scope

The initial implementation provides:

- one fleet table for multiple Aerostack2 namespaces;
- selected-aircraft and named-group operation;
- arm/disarm and offboard/manual service fan-out;
- takeoff, land, and GoTo behavior fan-out;
- emergency hover, emergency land, and guarded kill-switch publication;
- telemetry age/stale detection from `platform/info`, localization pose, and twist;
- measured host-side dispatch span for each command batch;
- optional startup discovery through the standard `/<namespace>/set_arming_state` service.

A group operation is implemented as a short sequence of ROS 2 calls to each namespace. It is
**not** a Crazyradio broadcast operation and it has no hard synchronization guarantee. Endpoint
availability is checked for the whole target set before ordinary service/action commands are sent;
a failed preflight therefore prevents a deliberately partial takeoff/land/GoTo batch. Emergency
alerts are published without this preflight.

The HTTP server binds to `127.0.0.1` by default and has no authentication layer. Binding to a
non-loopback address is rejected unless `--allow-remote` is explicitly supplied. If remote access
is enabled, restrict it at the host/network boundary.

## Build

From a ROS 2 Jazzy environment that can already build this Aerostack2 workspace:

```bash
colcon build --packages-select as2_swarm_web_ui
source install/setup.bash
```

For this fork's Pixi environment, enter the Jazzy environment first and run the same commands:

```bash
pixi run --as-is -e jazzy bash
colcon build --packages-select as2_swarm_web_ui
source install/setup.bash
```

## Run

Explicit namespaces:

```bash
ros2 run as2_swarm_web_ui swarm_web_ui --drones cf0 cf1 cf2 cf3
```

Configuration file with named groups:

```bash
ros2 run as2_swarm_web_ui swarm_web_ui \
  --config src/aerostack2/as2_user_interfaces/as2_swarm_web_ui/config/fleet.example.json
```

If the current working tree itself is the Aerostack2 source tree, adjust the path accordingly.
Open `http://127.0.0.1:8080/` in a browser.

Discovery-only startup is also supported:

```bash
ros2 run as2_swarm_web_ui swarm_web_ui --discover --discovery-wait 3
```

The discovery rule is intentionally narrow: a namespace must expose
`/<namespace>/set_arming_state` as `std_srvs/srv/SetBool`.

## HTTP API

The UI uses a small same-origin API:

- `GET /api/config`: namespaces, named groups, capabilities and dispatch semantics;
- `GET /api/fleet`: current aggregated fleet state;
- `POST /api/command`: command one explicit target set or configured group.

Example request body:

```json
{
  "action": "takeoff",
  "targets": ["cf0", "cf1"],
  "params": {"height": 0.7, "speed": 0.3}
}
```

The response includes `dispatch_span_ms`, which measures only how long the local bridge took to
submit the per-namespace ROS requests. It is not a measurement of radio arrival time or aircraft
motion synchronization.

## Before real-aircraft use

Validate at least the namespace list, coordinate frame, takeoff/landing parameters, stale-state
handling, emergency path, and multi-aircraft command behavior in simulation first. The prototype
does not implement authentication, operator roles, geofencing, inter-aircraft collision avoidance,
or a radio-level synchronized broadcast primitive.
