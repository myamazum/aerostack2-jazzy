#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
"""Check the installed Pixi workspace without starting nodes or DDS discovery."""

import importlib
import os
from pathlib import Path
import sys
import xml.etree.ElementTree as ET


def main():
    if os.environ.get('ROS_DISTRO') != 'jazzy':
        raise RuntimeError('Run this check with pixi run -e jazzy jazzy-check')
    prefix = Path(os.environ['CONDA_PREFIX']).resolve()
    for variable in ('AMENT_PREFIX_PATH', 'CMAKE_PREFIX_PATH', 'PYTHONPATH',
                     'LD_LIBRARY_PATH'):
        if '/opt/ros/' in os.environ.get(variable, ''):
            raise RuntimeError(f'{variable} contains an apt ROS underlay; use a clean shell')

    from ament_index_python.packages import get_package_prefix
    from as2_msgs.action import Takeoff
    from rclpy.serialization import deserialize_message, serialize_message

    root = Path(__file__).resolve().parents[2]
    manifest = ET.parse(root / 'aerostack2/package.xml').getroot()
    packages = ['aerostack2', *(item.text for item in manifest.findall('exec_depend'))]
    for package in packages:
        installed = Path(get_package_prefix(package)).resolve()
        if not installed.is_relative_to(prefix):
            raise RuntimeError(f'{package} resolved outside Pixi: {installed}')

    for name in ('rclpy', 'as2_python_api.drone_interface',
                 'as2_python_api.drone_interface_gps',
                 'as2_python_api.drone_interface_teleop'):
        module = importlib.import_module(name)
        if not Path(module.__file__).resolve().is_relative_to(prefix):
            raise RuntimeError(f'{name} imported outside Pixi: {module.__file__}')

    goal = Takeoff.Goal(takeoff_height=1.0, takeoff_speed=0.5)
    if deserialize_message(serialize_message(goal), type(goal)) != goal:
        raise RuntimeError('AS2 generated message type support failed')
    print(f'Jazzy OK: {len(packages)} AS2 packages, Python API, CDR type support')
    print(f'Python: {sys.executable}')
    print(f'Prefix: {prefix}')


if __name__ == '__main__':
    main()
