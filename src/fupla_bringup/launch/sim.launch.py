import os
from launch import LaunchDescription
from launch.actions import ExecuteProcess, DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration

def generate_launch_description():
    world_arg = DeclareLaunchArgument('world', default_value='default') # Zmieniamy domyślny na default, by był szybszy!
    model_arg = DeclareLaunchArgument('model', default_value='gz_x500')

    return LaunchDescription([world_arg, model_arg, OpaqueFunction(function=launch_setup)])

def launch_setup(context, *args, **kwargs):
    world = LaunchConfiguration('world').perform(context)
    model = LaunchConfiguration('model').perform(context)

    current_dir = os.path.dirname(__file__)
    repo_root = current_dir
    while repo_root != '/' and not os.path.exists(os.path.join(repo_root, 'external', 'PX4-Autopilot')):
        repo_root = os.path.dirname(repo_root)
    
    px4_dir = os.path.join(repo_root, 'external', 'PX4-Autopilot')

    # 1. Micro-XRCE-DDS Agent
    xrce_agent = ExecuteProcess(
        cmd=['MicroXRCEAgent', 'udp4', '-p', '8888'],
        output='screen'
    )

    # 2. QGroundControl (wymuszenie renderowania CPU w Dockerze)
    qgc_path = os.path.expanduser('~/QGroundControl/QGroundControl.AppImage')
    qgc = ExecuteProcess(
        cmd=[qgc_path],
        additional_env={
            'QT_X11_NO_MITSHM': '1',
            'LIBGL_ALWAYS_SOFTWARE': '1'
        },
        output='screen'
    )

    # 3. Uruchomienie PX4 + Gazebo (TUTAJ DODAJEMY ZMIENNE GRAFICZNE DLA GAZEBO)
    px4_sim = ExecuteProcess(
        cmd=['make', 'px4_sitl', model],
        cwd=px4_dir,
        additional_env={
            'PX4_GZ_WORLD': world,
            'QT_X11_NO_MITSHM': '1',
            'LIBGL_ALWAYS_SOFTWARE': '1',  # To uratuje czarne okno Gazebo!
            'PX4_GZ_HEADLESS': '1',
            'GZ_PARTITION': 'fupla_sim'
        },
        output='screen'
    )

    return [xrce_agent, qgc, px4_sim]