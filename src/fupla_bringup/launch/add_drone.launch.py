# src/fupla_bringup/launch/add_drone.launch.py
"""
FUPLA-droneSIM: Dynamic Drone Spawner
======================================
Adds a new PX4 SITL drone instance to the already-running simulation.
Each drone runs in its own gnome-terminal window for independent monitoring.

Prerequisites:
    - sim.launch.py must be running (Gazebo server + DDS Agent must be active).

Usage:
    ros2 launch fupla_bringup add_drone.launch.py id:=2
    ros2 launch fupla_bringup add_drone.launch.py id:=2 model:=gz_x500_depth pose:='2,0,0.2,0,0,0'
    ros2 launch fupla_bringup add_drone.launch.py id:=3 model:=gz_x500 pose:='-2,0,0.2,0,0,0'

Notes:
    - 'id' must be unique and >= 2 (ID=1 is reserved for the master drone).
    - Each ID offsets MAVLink UDP port: id=2 → port 14541, id=3 → 14542, etc.
    - PX4_GZ_STANDALONE=1 is set automatically by run_px4_instance.sh for id >= 2.
"""

import os
import subprocess
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    ExecuteProcess,
    OpaqueFunction,
)
from launch.substitutions import LaunchConfiguration


def _find_repo_root() -> str:
    """
    Locates the repository root directory at runtime.

    Resolution order:
      1. git rev-parse --show-toplevel
      2. Walk up from COLCON_PREFIX_PATH
      3. Walk up from __file__ location

    Raises:
        RuntimeError: If repository root cannot be located.
    """
    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--show-toplevel'],
            capture_output=True, text=True, check=True
        )
        root = result.stdout.strip()
        if os.path.isfile(os.path.join(root, 'tools', 'run_px4_instance.sh')):
            return root
    except Exception:
        pass

    colcon_prefix = os.environ.get('COLCON_PREFIX_PATH', '')
    if colcon_prefix:
        candidate = os.path.abspath(
            os.path.join(colcon_prefix.split(':')[0], '..')
        )
        if os.path.isfile(
            os.path.join(candidate, 'tools', 'run_px4_instance.sh')
        ):
            return candidate

    current = os.path.dirname(os.path.realpath(__file__))
    for _ in range(8):
        if os.path.isfile(
            os.path.join(current, 'tools', 'run_px4_instance.sh')
        ):
            return current
        current = os.path.abspath(os.path.join(current, '..'))

    raise RuntimeError(
        '[add_drone.launch.py] Cannot locate repository root.\n'
        'Ensure tools/run_px4_instance.sh exists in the repository root.'
    )


def launch_setup(context, *args, **kwargs):
    """
    Resolves launch arguments and constructs the drone spawn command.
    OpaqueFunction is required to evaluate LaunchConfiguration values at runtime.
    """
    drone_id = LaunchConfiguration('id').perform(context)
    model    = LaunchConfiguration('model').perform(context)
    pose     = LaunchConfiguration('pose').perform(context)

    # --- Validation -----------------------------------------------------------
    try:
        drone_id_int = int(drone_id)
    except ValueError:
        raise ValueError(
            f"[add_drone.launch.py] 'id' must be an integer, got: '{drone_id}'"
        )

    if drone_id_int < 2:
        raise ValueError(
            f"[add_drone.launch.py] Drone ID must be >= 2. "
            f"ID=1 is reserved for the master drone (sim.launch.py). "
            f"Got: {drone_id}"
        )

    # --- Path Resolution ------------------------------------------------------
    repo_root  = _find_repo_root()
    run_script = os.path.join(repo_root, 'tools', 'run_px4_instance.sh')

    if not os.path.isfile(run_script):
        raise FileNotFoundError(
            f"[add_drone.launch.py] run_px4_instance.sh not found at: "
            f"{run_script}\n"
            f"Please ensure tools/run_px4_instance.sh exists in the repository."
        )

    # --- MAVLink Port Info ----------------------------------------------------
    # PX4 instance ports (verified from mavlink status):
    #   instance 1: MAV_SYS_ID=2, MAVLink UDP 18571
    #   instance 2: MAV_SYS_ID=3, MAVLink UDP 18572
    #   formula: 18570 + drone_id
    mavlink_port = 18570 + drone_id_int
    mav_sys_id   = drone_id_int + 1

    # --- Process Definition ---------------------------------------------------
    drone = ExecuteProcess(
        cmd=[
            'gnome-terminal',
            '--',
            'bash', '-c',
            f'bash {run_script} {drone_id} {model} "{pose}"; exec bash'
        ],
        output='screen',
        name=f'px4_drone_{drone_id}',
    )

    return [drone]


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument(
            'id',
            default_value='2',
            description=(
                'Unique drone instance ID. Must be >= 2. '
                'ID=1 is reserved for master drone (sim.launch.py).'
            )
        ),
        DeclareLaunchArgument(
            'model',
            default_value='gz_x500',
            description='PX4 Gazebo model. Options: gz_x500, gz_x500_depth'
        ),
        DeclareLaunchArgument(
            'pose',
            default_value='2,0,0.2,0,0,0',
            description='Spawn pose: "x,y,z,roll,pitch,yaw"'
        ),
        OpaqueFunction(function=launch_setup),
    ])