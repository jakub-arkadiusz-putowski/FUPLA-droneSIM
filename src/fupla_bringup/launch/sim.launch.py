"""
FUPLA-droneSIM: Main Simulation Launch File
============================================
Starts the complete simulation infrastructure:
  1. Micro-XRCE-DDS Agent  - communication bridge between PX4 and ROS 2
  2. QGroundControl         - ground control station
  3. Master Drone (ID=1)    - PX4 SITL instance that owns the Gazebo server

Usage:
    ros2 launch fupla_bringup sim.launch.py
    ros2 launch fupla_bringup sim.launch.py model:=gz_x500_depth
    ros2 launch fupla_bringup sim.launch.py model:=gz_x500 pose:='0,0,0.2,0,0,0'

Notes:
    - This launch file starts the Gazebo SERVER (via drone ID=1).
    - Additional drones are added via add_drone.launch.py.
    - QGroundControl connects automatically via MAVLink UDP (port 14550).
"""

import os
import subprocess
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    ExecuteProcess,
    OpaqueFunction,
    TimerAction,
)
from launch.substitutions import LaunchConfiguration


def _find_repo_root() -> str:
    """
    Locates the repository root directory at runtime.

    This function is necessary because after 'colcon build --symlink-install',
    launch files are symlinked into install/ and __file__ cannot be used
    to reliably navigate to the repository root.

    Resolution order:
      1. git rev-parse --show-toplevel  (most reliable, works anywhere in repo)
      2. Walk up from COLCON_PREFIX_PATH env variable (install/ -> repo root)
      3. Walk up from __file__ location  (fallback for direct source execution)

    Raises:
        RuntimeError: If repository root cannot be located by any strategy.
    """
    # Strategy 1: Ask git directly - works from any directory inside the repo
    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--show-toplevel'],
            capture_output=True,
            text=True,
            check=True
        )
        root = result.stdout.strip()
        if os.path.isfile(os.path.join(root, 'tools', 'run_px4_instance.sh')):
            return root
    except Exception:
        pass

    # Strategy 2: COLCON_PREFIX_PATH points to install/ which is one level
    # below repo root (e.g. /home/user/FUPLA-droneSIM/install)
    colcon_prefix = os.environ.get('COLCON_PREFIX_PATH', '')
    if colcon_prefix:
        candidate = os.path.abspath(
            os.path.join(colcon_prefix.split(':')[0], '..')
        )
        if os.path.isfile(os.path.join(candidate, 'tools', 'run_px4_instance.sh')):
            return candidate

    # Strategy 3: Walk up directory tree from __file__ (up to 8 levels)
    current = os.path.dirname(os.path.realpath(__file__))
    for _ in range(8):
        if os.path.isfile(os.path.join(current, 'tools', 'run_px4_instance.sh')):
            return current
        current = os.path.abspath(os.path.join(current, '..'))

    raise RuntimeError(
        '[sim.launch.py] Cannot locate repository root.\n'
        'Ensure tools/run_px4_instance.sh exists in the repository root.'
    )


def launch_setup(context, *args, **kwargs):
    """
    Resolves launch arguments and constructs the process list.
    OpaqueFunction is required to evaluate LaunchConfiguration values at runtime.
    """
    model = LaunchConfiguration('model').perform(context)
    pose  = LaunchConfiguration('pose').perform(context)

    # --- Path Resolution ------------------------------------------------------
    repo_root   = _find_repo_root()
    run_script  = os.path.join(repo_root, 'tools', 'run_px4_instance.sh')
    qgc_appimage = os.path.join(
        os.path.expanduser('~'), 'QGroundControl', 'QGroundControl.AppImage'
    )

    # --- Validation -----------------------------------------------------------
    if not os.path.isfile(qgc_appimage):
        raise FileNotFoundError(
            f'[sim.launch.py] QGroundControl not found at: {qgc_appimage}\n'
            f'Please run tools/install.sh first.'
        )

        # --- Process Definitions --------------------------------------------------

    # 1. Micro-XRCE-DDS Agent
    dds_agent = ExecuteProcess(
        cmd=['MicroXRCEAgent', 'udp4', '-p', '8888'],
        output='screen',
        name='micro_xrce_dds_agent',
    )

    # 2. QGroundControl
    qgc = ExecuteProcess(
        cmd=[qgc_appimage],
        output='screen',
        name='qgroundcontrol',
    )

    # 3. Gazebo Server - started FIRST, standalone, before PX4 connects.
    #    PX4 will detect "gazebo already running" and attach to it.
    #    We use gz sim directly so we can control the startup timing.
    world_path = os.path.join(
        repo_root,
        'external', 'PX4-Autopilot',
        'Tools', 'simulation', 'gz', 'worlds', 'default.sdf'
    )

    gazebo = ExecuteProcess(
        cmd=['gz', 'sim', '--verbose=1', '-r', world_path],
        output='screen',
        name='gazebo_server',
        additional_env={
            'GZ_SIM_RESOURCE_PATH': os.environ.get('GZ_SIM_RESOURCE_PATH', ''),
        }
    )

    # 4. Master Drone (Instance 1)
    #    Delayed by 10 seconds to allow Gazebo to fully initialize.
    #    PX4 runs directly in the launch process (output visible in ros2 launch terminal)
    # gnome-terminal is NOT used here because ros2 launch runs without
    # a DBUS session, which is required by gnome-terminal
    master_drone = TimerAction(
        period=10.0,
        actions=[
            ExecuteProcess(
                cmd=['bash', run_script, '1', model, pose],
                output='screen',
                name='px4_drone_1_master',
            )
        ]
    )

    return [dds_agent, qgc, gazebo, master_drone]


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument(
            'model',
            default_value='gz_x500',
            description='PX4 Gazebo model. Options: gz_x500, gz_x500_depth'
        ),
        DeclareLaunchArgument(
            'pose',
            default_value='0,0,0.2,0,0,0',
            description='Spawn pose of the master drone: "x,y,z,roll,pitch,yaw"'
        ),
        OpaqueFunction(function=launch_setup),
    ])