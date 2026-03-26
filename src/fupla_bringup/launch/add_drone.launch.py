import os
from launch import LaunchDescription
from launch.actions import ExecuteProcess, DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration

def launch_setup(context, *args, **kwargs):
    drone_id = LaunchConfiguration('id').perform(context)
    model = LaunchConfiguration('model').perform(context)
    
    # ID 2 -> Instance 1
    instance_num = str(int(drone_id) - 1)
    
    # Szukanie głównego folderu repozytorium
    current_dir = os.path.dirname(__file__)
    repo_root = current_dir
    while repo_root != '/' and not os.path.exists(os.path.join(repo_root, 'external', 'PX4-Autopilot')):
        repo_root = os.path.dirname(repo_root)
    
    px4_dir = os.path.join(repo_root, 'external', 'PX4-Autopilot')
    px4_binary = os.path.join(px4_dir, 'build/px4_sitl_default/bin/px4')
    
    # BUDUJEMY ŚCIEŻKI ABSOLUTNE (Pancerne)
    # W PX4 v1.14 plik rcS jest tutaj:
    romfs_dir = os.path.join(px4_dir, 'ROMFS/px4fmu_common')
    rc_script = os.path.join(romfs_dir, 'etc/init.d-posix/rcS')

    # Tworzymy osobny folder roboczy dla instancji, żeby drony nie nadpisywały sobie logów
    instance_work_dir = os.path.join(px4_dir, f'build/instance_{instance_num}')
    os.makedirs(instance_work_dir, exist_ok=True)

    add_drone = ExecuteProcess(
        cmd=[
            px4_binary,
            '-s', rc_script,      # PEŁNA ŚCIEŻKA DO SKRYPTU
            '-i', instance_num,   # NUMER INSTANCJI
            '-d'                  # TRYB DEMONA (SITL)
        ],
        cwd=instance_work_dir,    # Każdy dron ma swój folder na logi/pliki
        additional_env={
            'PX4_SYS_AUTOSTART': '4001',
            'PX4_GZ_MODEL_NAME': f'x500_{drone_id}',
            'PX4_SIM_MODEL': model,
            'PX4_GZ_WORLD': 'default',
            'PX4_GZ_HEADLESS': '1',
            'GZ_PARTITION': 'fupla_sim',
            'PX4_ROMFS_DIR': romfs_dir # KLUCZOWE: Wskazujemy gdzie jest folder 'etc'
        },
        output='screen'
    )
    
    return [add_drone]

def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('id', default_value='2'),
        DeclareLaunchArgument('model', default_value='gz_x500'),
        OpaqueFunction(function=launch_setup)
    ])