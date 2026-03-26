import os
from launch import LaunchDescription
from launch.actions import ExecuteProcess, DeclareLaunchArgument, OpaqueFunction, LogInfo
from launch.substitutions import LaunchConfiguration

def launch_setup(context, *args, **kwargs):
    world = LaunchConfiguration('world').perform(context)
    model = LaunchConfiguration('model').perform(context)
    
    # PX4 dodaje prefix gz_, ale w Gazebo model nazywa się bez niego + id
    # np. gz_x500_vision -> x500_vision_0
    gz_model_name = model.replace('gz_', '') + '_0'
    
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

    # 3. PX4 + Gazebo (WYŁĄCZAMY HEADLESS DLA KAMERY)
    px4_sim = ExecuteProcess(
        cmd=['make', 'px4_sitl', model],
        cwd=px4_dir,
        additional_env={
            'PX4_GZ_WORLD': world,
            'PX4_GZ_HEADLESS': '0', # Zmieniamy na 0, żeby kamera renderowała obraz!
            'GZ_PARTITION': 'fupla_sim'
        },
        output='screen'
    )

    # 4. Mostek kamery (Poprawna wersja dla ExecuteProcess)
    camera_gz_topic = f'/world/{world}/model/{gz_model_name}/link/camera_link/sensor/camera/image'
    
    camera_bridge = ExecuteProcess(
        cmd=[
            'ros2', 'run', 'ros_gz_bridge', 'parameter_bridge',
            f'{camera_gz_topic}@sensor_msgs/msg/Image[gz.msgs.Image',
            '--ros-args', 
            '-r', f'{camera_gz_topic}:=/image_raw' # Mapowanie tematu przez argumenty CLI
        ],
        additional_env={'GZ_PARTITION': 'fupla_sim'},
        output='screen'
    )

    return [xrce_agent, qgc, px4_sim, camera_bridge]

def generate_launch_description():
    return LaunchDescription([
        # Tutaj definiujemy, co użytkownik może wpisać w terminalu
        DeclareLaunchArgument('world', default_value='default', description='Nazwa świata'),
        DeclareLaunchArgument('model', default_value='gz_x500', description='Model drona (np. gz_x500, gz_x500_vision)'),
        OpaqueFunction(function=launch_setup)
    ])