"""
FUPLA-droneSIM: Scalability Extension
-------------------------------------
Industrial-grade script for dynamic UAV fleet scaling.
Uses the 'STANDALONE' flag to attach new instances to an existing Gazebo server.

This block replicates the manual command:
PX4_GZ_STANDALONE=1 PX4_SYS_AUTOSTART=4001 PX4_GZ_MODEL_POSE="0,1" PX4_SIM_MODEL=gz_x500 ./build/px4_sitl_default/bin/px4 -i 2
"""

import os
from launch import LaunchDescription
from launch.actions import ExecuteProcess, DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration

def launch_setup(context, *args, **kwargs):
    drone_id = LaunchConfiguration('id').perform(context)
    model = LaunchConfiguration('model').perform(context)
    
    # Path Resolution
    current_dir = os.path.dirname(__file__)
    repo_root = current_dir
    while repo_root != '/' and not os.path.exists(os.path.join(repo_root, 'external', 'PX4-Autopilot')):
        repo_root = os.path.dirname(repo_root)
    
    px4_dir = os.path.join(repo_root, 'external', 'PX4-Autopilot')
    px4_binary = './build/px4_sitl_default/bin/px4'

    # Automatic Pose Calculation: Places new drones on a grid (offset by 1 meter per ID)
    y_pos = str(int(drone_id) - 1)

    # Secondary PX4 Instance (Instance N):
    # Logic: PX4_GZ_STANDALONE=1 forces the instance to join the current Gazebo partition.
    add_drone = ExecuteProcess(
        cmd=[px4_binary, '-i', drone_id],
        cwd=px4_dir,
        additional_env={
            'PX4_GZ_STANDALONE': '1',        # Crucial for multi-vehicle integration
            'PX4_SYS_AUTOSTART': '4001',
            'PX4_GZ_MODEL_POSE': f'0,{y_pos}',
            'PX4_SIM_MODEL': model,          # Allows mixing drone types (e.g. x500 and VTOL)
        },
        output='screen'
    )
    
    return [add_drone]

def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('id', default_value='2', description='Unique instance ID'),
        DeclareLaunchArgument('model', default_value='gz_x500', description='UAV Model'),
        OpaqueFunction(function=launch_setup)
    ])