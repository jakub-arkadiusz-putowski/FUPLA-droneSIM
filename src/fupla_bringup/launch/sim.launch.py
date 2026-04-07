import os
from launch import LaunchDescription
from launch.actions import ExecuteProcess, DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

def launch_setup(context, *args, **kwargs):
    world = LaunchConfiguration('world').perform(context)
    model = LaunchConfiguration('model').perform(context)
    
    # Podstawowe ścieżki
    current_dir = os.path.dirname(__file__)
    repo_root = current_dir
    while repo_root != '/' and not os.path.exists(os.path.join(repo_root, 'external', 'PX4-Autopilot')):
        repo_root = os.path.dirname(repo_root)
    px4_dir = os.path.join(repo_root, 'external', 'PX4-Autopilot')

    # 1. Micro-XRCE-DDS Agent
    xrce_agent = ExecuteProcess(cmd=['MicroXRCEAgent', 'udp4', '-p', '8888'], output='screen')

    # 2. QGroundControl
    qgc_path = os.path.expanduser('~/QGroundControl/QGroundControl.AppImage')
    qgc = ExecuteProcess(cmd=[qgc_path], additional_env={'LIBGL_ALWAYS_SOFTWARE': '1'}, output='screen')

    # 3. PX4 + Gazebo (Single Instance - najstabilniejszy tryb)
    px4_sim = ExecuteProcess(
        cmd=['make', 'px4_sitl', model],
        cwd=px4_dir,
        additional_env={
            'PX4_GZ_WORLD': world,
            'PX4_GZ_HEADLESS': '0',
            'LIBGL_ALWAYS_SOFTWARE': '1'
        },
        output='screen'
    )

    # 4. Mostek kamery (Zostawiamy, bo to działało!)
    camera_bridge = Node(
        package='ros_gz_bridge',
        executable='parameter_bridge',
        arguments=['/camera@sensor_msgs/msg/Image[gz.msgs.Image'],
        remappings=[('/camera', '/image_raw')],
        output='screen'
    )

    return [xrce_agent, qgc, px4_sim, camera_bridge]

def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('world', default_value='default'),
        DeclareLaunchArgument('model', default_value='gz_x500_depth'),
        OpaqueFunction(function=launch_setup)
    ])