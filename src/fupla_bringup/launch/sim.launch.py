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
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    ExecuteProcess,
    OpaqueFunction,
)
from launch.substitutions import LaunchConfiguration


def launch_setup(context, *args, **kwargs):
    """
    Resolves launch arguments and constructs the process list.
    OpaqueFunction is required to evaluate LaunchConfiguration values at runtime.
    """
    model = LaunchConfiguration('model').perform(context)
    pose  = LaunchConfiguration('pose').perform(context)

    # --- Path Resolution ------------------------------------------------------
    # Locate the launcher script using environment variable set by the installer,
    # falling back to a path relative to this file for development convenience.
    this_file_dir = os.path.dirname(os.path.realpath(__file__))
    repo_root = os.path.abspath(os.path.join(this_file_dir, '..', '..', '..', '..'))
    run_script = os.path.join(repo_root, 'tools', 'run_px4_instance.sh')
    qgc_appimage = os.path.join(os.path.expanduser('~'), 'QGroundControl', 'QGroundControl.AppImage')

    # --- Validation -----------------------------------------------------------
    if not os.path.isfile(run_script):
        raise FileNotFoundError(
            f"[sim.launch.py] run_px4_instance.sh not found at: {run_script}\n"
            f"Please ensure tools/run_px4_instance.sh exists in the repository."
        )

    if not os.path.isfile(qgc_appimage):
        raise FileNotFoundError(
            f"[sim.launch.py] QGroundControl not found at: {qgc_appimage}\n"
            f"Please run tools/install.sh first."
        )

    # --- Process Definitions --------------------------------------------------

    # 1. Micro-XRCE-DDS Agent
    #    Bridges PX4 uORB topics to ROS 2 DDS.
    #    Port 8888 is the PX4 default for SITL.
    dds_agent = ExecuteProcess(
        cmd=['MicroXRCEAgent', 'udp4', '-p', '8888'],
        output='screen',
        name='micro_xrce_dds_agent',
    )

    # 2. QGroundControl
    #    Launched in a separate process; connects via MAVLink UDP automatically.
    qgc = ExecuteProcess(
        cmd=[qgc_appimage],
        output='screen',
        name='qgroundcontrol',
    )

    # 3. Master Drone (Instance 1) - Gazebo Server
    #    Opened in a dedicated gnome-terminal window for visibility.
    #    'exec bash' keeps the terminal open after PX4 exits (useful for debugging).
    master_drone = ExecuteProcess(
        cmd=[
            'gnome-terminal',
            f'--title=PX4 | Drone 1 (Master) | {model}',
            '--',
            'bash', '-c',
            f'bash {run_script} 1 {model} "{pose}"; exec bash'
        ],
        output='screen',
        name='px4_drone_1_master',
    )

    return [dds_agent, qgc, master_drone]


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument(
            'model',
            default_value='gz_x500',
            description='PX4 Gazebo model for the master drone. Options: gz_x500, gz_x500_depth'
        ),
        DeclareLaunchArgument(
            'pose',
            default_value='0,0,0.2,0,0,0',
            description='Spawn pose of the master drone: "x,y,z,roll,pitch,yaw"'
        ),
        OpaqueFunction(function=launch_setup),
    ])