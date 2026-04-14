import os
from launch import LaunchDescription
from launch.actions import ExecuteProcess

def generate_launch_description():
    home = os.path.expanduser('~')
    px4_path = os.path.join(home, 'FUPLA-droneSIM/external/PX4-Autopilot')

    #adding just one drone to sim
    drone_cmd = f"cd {px4_path} && PX4_SYS_AUTOSTART=4001 PX4_SIM_MODEL=gz_x500 ./build/px4_sitl_default/bin/px4 -i 1"

    return LaunchDescription([
        ExecuteProcess(cmd=['MicroXRCEAgent', 'udp4', '-p', '8888'], output='screen'),
        ExecuteProcess(cmd=[os.path.join(home, 'QGroundControl/QGroundControl.AppImage')], output='screen'),
        ExecuteProcess(
            cmd=['gnome-terminal', '--', 'bash', '-c', f"{drone_cmd}; exec bash"],
            output='screen'
        )
    ])