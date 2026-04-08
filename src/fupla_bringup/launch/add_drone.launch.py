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
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    ExecuteProcess,
    OpaqueFunction,
)
from launch.substitutions import LaunchConfiguration


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
        raise ValueError(f"[add_drone.launch.py] 'id' must be an integer, got: '{drone_id}'")

    if drone_id_int < 2:
        raise ValueError(
            f"[add_drone.launch.py] Drone ID must be >= 2. "
            f"ID=1 is reserved for the master drone (sim.launch.py). Got: {drone_id}"
        )

    # --- Path Resolution ------------------------------------------------------
    this_file_dir = os.path.dirname(os.path.realpath(__file__))
    repo_root = os.path.abspath(os.path.join(this_file_dir, '..', '..', '..', '..'))
    run_script = os.path.join(repo_root, 'tools', 'run_px4_instance.sh')

    if not os.path.isfile(run_script):
        raise FileNotFoundError(
            f"[add_drone.launch.py] run_px4_instance.sh not found at: {run_script}\n"
            f"Please ensure tools/run_px4_instance.sh exists in the repository."
        )

    # --- Process Definition ---------------------------------------------------
    drone = ExecuteProcess(
        cmd=[
            'gnome-terminal',
            f'--title=PX4 | Drone {drone_id} | {model}',
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
            description='Unique drone instance ID. Must be >= 2. ID=1 is reserved for master.'
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