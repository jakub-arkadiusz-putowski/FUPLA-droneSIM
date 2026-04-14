"""
FUPLA-droneSIM: Main Simulation Launch File
============================================
Starts the complete simulation infrastructure:
  1. Micro-XRCE-DDS Agent  - communication bridge between PX4 and ROS 2
  2. QGroundControl         - ground control station
  3. Gazebo                 - physics simulator
  4. Master Drone (ID=1)    - PX4 SITL instance that owns the Gazebo server
  5. Joy Node               - reads physical joystick (/dev/input/js0)
  6. RC Bridge              - translates /joy → MAVLink MANUAL_CONTROL → PX4

Usage:
    ros2 launch fupla_bringup sim.launch.py
    ros2 launch fupla_bringup sim.launch.py model:=gz_x500_depth
    ros2 launch fupla_bringup sim.launch.py joy_device_id:=1

Notes:
    - This launch file starts the Gazebo SERVER (via drone ID=1).
    - Additional drones are added via add_drone.launch.py.
    - QGroundControl connects automatically via MAVLink UDP (port 14550).
    - PX4 requires: param set COM_RC_IN_MODE 1  (set once, then param save)
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
from launch_ros.actions import Node as RosNode


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
    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--show-toplevel'],
            capture_output=True, text=True, check=True
        )
        root = result.stdout.strip()
        if os.path.isfile(os.path.join(root, 'tools', 'run_px4_instance.sh')):
            return root
    except Exception:
        pass

    colcon_prefix = os.environ.get('COLCON_PREFIX_PATH', '')
    if colcon_prefix:
        candidate = os.path.abspath(
            os.path.join(colcon_prefix.split(':')[0], '..')
        )
        if os.path.isfile(os.path.join(candidate, 'tools', 'run_px4_instance.sh')):
            return candidate

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
    model         = LaunchConfiguration('model').perform(context)
    pose          = LaunchConfiguration('pose').perform(context)
    joy_device_id = int(LaunchConfiguration('joy_device_id').perform(context))
    target_system = int(LaunchConfiguration('target_system').perform(context))

    # --- Path Resolution ------------------------------------------------------
    repo_root    = _find_repo_root()
    run_script   = os.path.join(repo_root, 'tools', 'run_px4_instance.sh')
    qgc_appimage = os.path.join(
        os.path.expanduser('~'), 'QGroundControl', 'QGroundControl.AppImage'
    )
    world_path = os.path.join(
        repo_root,
        'external', 'PX4-Autopilot',
        'Tools', 'simulation', 'gz', 'worlds', 'default.sdf'
    )
    gz_env_script = os.path.join(
        repo_root,
        'external', 'PX4-Autopilot',
        'build', 'px4_sitl_default', 'rootfs', 'gz_env.sh'
    )

    # --- Gazebo Environment ---------------------------------------------------
    # Parse gz_env.sh to extract Gazebo environment variables.
    # These are passed explicitly to the gz sim process because
    # ros2 launch does not inherit shell environment variables.
    # Without GZ_SIM_RESOURCE_PATH, Gazebo cannot find PX4 drone models,
    # resulting in "Error finding file [x500/model.sdf]".
    gz_env = {}
    if os.path.isfile(gz_env_script):
        result = subprocess.run(
            ['bash', '-c', f'source {gz_env_script} && env'],
            capture_output=True, text=True
        )
        for line in result.stdout.splitlines():
            if '=' in line and any(k in line for k in ['GZ_SIM', 'PX4_GZ']):
                key, _, value = line.partition('=')
                gz_env[key] = value
    else:
        raise FileNotFoundError(
            f'[sim.launch.py] gz_env.sh not found: {gz_env_script}\n'
            'Please run tools/install.sh first (PX4 must be built).'
        )

    # --- Validation -----------------------------------------------------------
    for path, label in [
        (run_script,   'tools/run_px4_instance.sh'),
        (qgc_appimage, 'QGroundControl.AppImage'),
        (world_path,   'default.sdf'),
    ]:
        if not os.path.isfile(path):
            raise FileNotFoundError(
                f'[sim.launch.py] {label} not found at: {path}\n'
                'Please run tools/install.sh first.'
            )

    # --- MAVLink Port Resolution ----------------------------------------------
    # Verified from 'pxh> mavlink status':
    #   instance #0: UDP (18571, remote 14550) — GCS/Normal mode
    #   instance #1: UDP (14581, remote 14541) — Onboard mode
    #
    # PX4 SITL listens for incoming MAVLink on port 18570 + drone_id.
    # RC Bridge must send to this port for MANUAL_CONTROL to be accepted.
    # Formula: 18570 + target_system  (drone 1 → 18571, drone 2 → 18572)
    mavlink_port = 18571

    # =========================================================================
    # Process Definitions
    # =========================================================================

    # 1. Micro-XRCE-DDS Agent
    #    Bridges PX4 uORB topics to ROS 2 DDS domain.
    #    Port 8888 is the PX4 SITL default for uxrce_dds_client.
    dds_agent = ExecuteProcess(
        cmd=['MicroXRCEAgent', 'udp4', '-p', '8888'],
        output='screen',
        name='micro_xrce_dds_agent',
    )

    # 2. QGroundControl
    #    Connects automatically via MAVLink UDP broadcast on port 14550.
    qgc = ExecuteProcess(
        cmd=[qgc_appimage],
        output='screen',
        name='qgroundcontrol',
    )

    # 3. Gazebo Server
    #    Started BEFORE PX4 to avoid race condition where PX4 cannot
    #    find a running Gazebo instance and falls back to no-sim mode.
    gazebo = ExecuteProcess(
        cmd=['gz', 'sim', '--verbose=1', '-r', world_path],
        output='screen',
        name='gazebo_server',
        additional_env=gz_env,
    )

    # 4. Master Drone (PX4 SITL instance 1)
    #    Delayed 10s to allow Gazebo to fully initialize before PX4 connects.
    #    Spawned in gnome-terminal to provide interactive PX4 shell (pxh>).
    master_drone = TimerAction(
        period=10.0,
        actions=[
            ExecuteProcess(
                cmd=[
                    'gnome-terminal', '--',
                    'bash', '-c',
                    f'bash {run_script} 1 {model} "{pose}"; exec bash'
                ],
                output='screen',
                name='px4_drone_1_master',
            )
        ]
    )

    # 5. Joy Node
    #    Delayed 5s to ensure ROS 2 middleware is ready.
    #    Reads physical joystick and publishes sensor_msgs/Joy to /joy.
    #    device_id=0 corresponds to /dev/input/js0 (first detected joystick).
    #    autorepeat_rate ensures /joy publishes continuously even without input,
    #    which is required for RC Bridge to maintain a live MAVLink stream.
    joy_node = TimerAction(
        period=5.0,
        actions=[
            RosNode(
                package='joy',
                executable='joy_node',
                name='joy_node',
                parameters=[{
                    'device_id':       joy_device_id,
                    'autorepeat_rate': 20.0,
                    'deadzone':        0.05,
                }],
                output='screen',
            )
        ]
    )

    # 6. RC Bridge
    #    Delayed 15s to ensure PX4 is running and MAVLink link is established.
    #    Translates /joy axes → MAVLink MANUAL_CONTROL → PX4 instance #0.
    #
    #    Prerequisites (set once in PX4 shell, persists after param save):
    #      pxh> param set COM_RC_IN_MODE 1
    #      pxh> param save
    rc_bridge = TimerAction(
        period=15.0,
        actions=[
            RosNode(
                package='fupla_joy',
                executable='node_joy_to_rc',
                name='node_joy_to_rc',
                parameters=[{
                    'target_system': target_system,
                    'udp_port':      mavlink_port,
                }],
                output='screen',
            )
        ]
    )

    #7. px4 parameter configurator
    # delayed 20s px4 must be fully booted before parameter upload.
    # one-shot node: uploads sitl_params.yaml, saves, then exits.
    # eliminates manual 'px4> param set'.
    px4_configurator = TimerAction(
        period=20.0,
        actions=[
            RosNode(
                package='fupla_joy',
                executable='node_px4_configurator',
                name='node_px4_configurator',
                parameters=[{
                    'target_system': target_system,
                    'udp_port':      18571,
                }],
                output='screen',
            )
        ]
    )

    return [dds_agent, qgc, gazebo, master_drone, joy_node, rc_bridge, px4_configurator]


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
        DeclareLaunchArgument(
            'joy_device_id',
            default_value='0',
            description='Joystick Linux device ID. 0 = /dev/input/js0'
        ),
        DeclareLaunchArgument(
            'target_system',
            default_value='2',
            description=(
                'MAVLink system ID of the drone to control via joystick. '
                'Must match MAV_SYS_ID parameter in PX4'
                'Check with: pxh> param show MAV_SYS_ID'
            )
        ),
        OpaqueFunction(function=launch_setup),
    ])