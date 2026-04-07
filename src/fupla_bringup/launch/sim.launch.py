"""
FUPLA-droneSIM: Global Simulation Master
---------------------------------------
Commercial-grade launch script for initializing the primary UAV simulation environment.
This script replicates the validated manual command for Instance 1.

Workflow:
1. Micro-XRCE-DDS Agent (Communication gateway)
2. QGroundControl (Operator Interface)
3. Master PX4 SITL Instance (Starts Gazebo Server)

Maintainer: Jakub Arkadiusz Putowski
"""

import os
from launch import LaunchDescription
from launch.actions import ExecuteProcess, DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration

def launch_setup(context, *args, **kwargs):
    # Retrieve dynamic parameters from user input
    model = LaunchConfiguration('model').perform(context)
    world = LaunchConfiguration('world').perform(context)
    
    # Path Resolution: Locating PX4-Autopilot within the FUPLA workspace
    current_dir = os.path.dirname(__file__)
    repo_root = current_dir
    while repo_root != '/' and not os.path.exists(os.path.join(repo_root, 'external', 'PX4-Autopilot')):
        repo_root = os.path.dirname(repo_root)
    
    px4_dir = os.path.join(repo_root, 'external', 'PX4-Autopilot')
    # Execution target: The pre-compiled SITL binary
    px4_binary = './build/px4_sitl_default/bin/px4'

    # 1. Micro-XRCE-DDS Agent: Mandatory bridge for uORB (PX4) to DDS (ROS 2) telemetry exchange.
    xrce_agent = ExecuteProcess(
        cmd=['MicroXRCEAgent', 'udp4', '-p', '8888'],
        output='screen'
    )

    # 2. QGroundControl: Ground Station for real-time monitoring and parameter management.
    qgc = ExecuteProcess(
        cmd=[os.path.expanduser('~/QGroundControl/QGroundControl.AppImage')],
        output='screen'
    )

    # 3. Master PX4 Instance (Instance 1): Initiates the simulation physics engine (Gazebo).
    # This block replicates the manual command: 
    # PX4_SYS_AUTOSTART=4001 PX4_SIM_MODEL=gz_x500 ./build/px4_sitl_default/bin/px4 -i 1
    px4_sim = ExecuteProcess(
        cmd=[px4_binary, '-i', '1'],
        cwd=px4_dir, # Ensures binary resolves local paths correctly
        additional_env={
            'PX4_SYS_AUTOSTART': '4001',
            'PX4_SIM_MODEL': model,
            'PX4_GZ_WORLD': world,
        },
        output='screen'
    )

    return [xrce_agent, qgc, px4_sim]

def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('world', default_value='default', description='World name (e.g. default, baylands)'),
        DeclareLaunchArgument('model', default_value='gz_x500', description='UAV Model (e.g. gz_x500, gz_standard_vtol)'),
        OpaqueFunction(function=launch_setup)
    ])