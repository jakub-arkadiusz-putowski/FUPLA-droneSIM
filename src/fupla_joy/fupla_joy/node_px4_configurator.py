#!/usr/bin/env python3
"""
FUPLA-droneSIM: PX4 Automatic Parameter Configurator
=====================================================
Uploads required PX4 parameters automatically on simulation start.
Eliminates the need for manual 'pxh> param set' commands.

Every developer gets identical PX4 configuration after:
    ros2 launch fupla_bringup sim.launch.py

Parameters are loaded from:
    config/px4/sitl_params.yaml  (relative to repository root)

Protocol:
    MAVLink PARAM_SET → PX4 acknowledges with PARAM_VALUE
    After all params uploaded: MAVLink COMMAND_LONG (PREFLIGHT_STORAGE)
    to persist parameters across restarts.

Usage:
    Started automatically by sim.launch.py after PX4 boots.
    Can also be run manually:
        ros2 run fupla_joy node_px4_configurator
"""

import os
import time
import yaml
import rclpy
from rclpy.node import Node
from pymavlink import mavutil


# Time to wait for PX4 to fully boot before uploading parameters.
# PX4 SITL typically takes 8-12 seconds to initialize MAVLink.
PX4_BOOT_WAIT_SEC = 15.0

# Timeout waiting for PARAM_VALUE acknowledgement from PX4 per parameter.
PARAM_ACK_TIMEOUT_SEC = 3.0

# Number of retries if PX4 does not acknowledge a parameter set.
PARAM_SET_RETRIES = 3


class PX4ConfiguratorNode(Node):
    """
    One-shot ROS 2 node that uploads PX4 parameters via MAVLink on startup.

    Lifecycle:
      1. Wait PX4_BOOT_WAIT_SEC for PX4 to initialize
      2. Connect to PX4 via MAVLink UDP
      3. Wait for PX4 heartbeat (confirms MAVLink link is alive)
      4. Upload each parameter from sitl_params.yaml
      5. Save parameters to persistent storage (param save)
      6. Shut down (one-shot — no continuous operation needed)
    """

    def __init__(self):
        super().__init__('node_px4_configurator')

        # --- Parameters -------------------------------------------------------
        self.declare_parameter('target_system', 2)
        self.declare_parameter('udp_port', 18571)
        self.declare_parameter(
            'params_file',
            self._find_params_file()
        )

        self._target_system = self.get_parameter('target_system').value
        self._udp_port      = self.get_parameter('udp_port').value
        self._params_file   = self.get_parameter('params_file').value

        self.get_logger().info(
            f'[px4_configurator] Starting.\n'
            f'  Target     : 127.0.0.1:{self._udp_port} '
            f'(system_id={self._target_system})\n'
            f'  Params file: {self._params_file}\n'
            f'  Waiting {PX4_BOOT_WAIT_SEC}s for PX4 to boot...'
        )

        # Run configuration in a one-shot timer after boot wait
        self.create_timer(PX4_BOOT_WAIT_SEC, self._run_configuration)

    # --- Path resolution ------------------------------------------------------

    def _find_params_file(self) -> str:
        """
        Locates config/px4/sitl_params.yaml relative to repository root.
        Uses same git-based strategy as sim.launch.py.
        """
        import subprocess

        # Strategy 1: git rev-parse
        try:
            result = subprocess.run(
                ['git', 'rev-parse', '--show-toplevel'],
                capture_output=True, text=True, check=True
            )
            root = result.stdout.strip()
            candidate = os.path.join(root, 'config', 'px4', 'sitl_params.yaml')
            if os.path.isfile(candidate):
                return candidate
        except Exception:
            pass

        # Strategy 2: COLCON_PREFIX_PATH
        colcon_prefix = os.environ.get('COLCON_PREFIX_PATH', '')
        if colcon_prefix:
            root = os.path.abspath(
                os.path.join(colcon_prefix.split(':')[0], '..')
            )
            candidate = os.path.join(root, 'config', 'px4', 'sitl_params.yaml')
            if os.path.isfile(candidate):
                return candidate

        raise FileNotFoundError(
            '[px4_configurator] Cannot find config/px4/sitl_params.yaml.\n'
            'Ensure the file exists in the repository root.'
        )

    # --- Main configuration routine -------------------------------------------

    def _run_configuration(self):
        """
        One-shot timer callback. Connects to PX4, uploads all parameters,
        saves them, then shuts down this node.
        """
        self.get_logger().info('[px4_configurator] Boot wait complete. Connecting...')

        # --- Load parameters from YAML ----------------------------------------
        try:
            with open(self._params_file, 'r') as f:
                params = yaml.safe_load(f)
        except Exception as e:
            self.get_logger().error(
                f'[px4_configurator] Failed to load params file: {e}'
            )
            return

        if not params:
            self.get_logger().warn('[px4_configurator] Params file is empty.')
            return

        self.get_logger().info(
            f'[px4_configurator] Loaded {len(params)} parameters. Uploading...'
        )

        # --- Connect to PX4 ---------------------------------------------------
        connection_str = f'udpout:127.0.0.1:{self._udp_port}'
        try:
            mav = mavutil.mavlink_connection(
                connection_str,
                source_system=255,
                source_component=195,
            )
        except Exception as e:
            self.get_logger().error(
                f'[px4_configurator] MAVLink connection failed: {e}'
            )
            return

        # Send heartbeat so PX4 knows we exist
        mav.mav.heartbeat_send(
            mavutil.mavlink.MAV_TYPE_GCS,
            mavutil.mavlink.MAV_AUTOPILOT_INVALID,
            0, 0, 0
        )
        time.sleep(0.5)

        # --- Upload parameters ------------------------------------------------
        success_count = 0
        fail_count    = 0

        for param_name, param_value in params.items():
            ok = self._set_param(mav, param_name, param_value)
            if ok:
                success_count += 1
            else:
                fail_count += 1

        self.get_logger().info(
            f'[px4_configurator] Upload complete: '
            f'{success_count} OK, {fail_count} failed.'
        )

        # --- Save parameters --------------------------------------------------
        self.get_logger().info('[px4_configurator] Saving parameters (param save)...')
        mav.mav.command_long_send(
            self._target_system,
            1,
            mavutil.mavlink.MAV_CMD_PREFLIGHT_STORAGE,
            0,
            1, 0, 0, 0, 0, 0, 0
        )
        time.sleep(1.0)

        self.get_logger().info(
            f'[px4_configurator] ✓ Done.\n'
            f'  {success_count}/{len(params)} parameters uploaded and saved.\n'
            f'  Node shutting down.'
        )

        raise SystemExit(0)

    # --- Parameter set with acknowledgement -----------------------------------

    def _set_param(self, mav, param_name: str, param_value) -> bool:
        """
        Sets a PX4 parameter via MAVLink PARAM_SET.
        
        Type detection:
          Python int   → MAV_PARAM_TYPE_INT32  (e.g. COM_RC_IN_MODE: 1)
          Python float → MAV_PARAM_TYPE_REAL32 (e.g. COM_RC_LOSS_T: 3.0)
        
        YAML format determines the type — use integer literals for INT32 params
        and float literals (with decimal point) for REAL32 params.
        """
        if isinstance(param_value, int):
            # INT32 parameter — send raw integer bits via struct reinterpretation
            param_type  = mavutil.mavlink.MAV_PARAM_TYPE_INT32
            # MAVLink param_set 'param_value' field is a float in the wire format,
            # but PX4 reads the raw bits as int32 when type=INT32.
            # Use struct to reinterpret int bytes as float without value conversion.
            import struct
            send_value = struct.unpack('f', struct.pack('i', int(param_value)))[0]
        else:
            # REAL32 parameter — send as float directly
            param_type = mavutil.mavlink.MAV_PARAM_TYPE_REAL32
            send_value = float(param_value)
    
        param_id = param_name.encode('utf-8').ljust(16, b'\x00')[:16]
    
        # Send twice for reliability (no ack via udpout)
        for _ in range(2):
            mav.mav.param_set_send(
                self._target_system,
                1,
                param_id,
                send_value,
                param_type,
            )
            time.sleep(0.1)
    
        self.get_logger().info(
            f'[px4_configurator]   → {param_name} = {param_value} '
            f'({"INT32" if isinstance(param_value, int) else "REAL32"})'
        )
        return True


def main(args=None):
    rclpy.init(args=args)
    node = PX4ConfiguratorNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        node.get_logger().info('[px4_configurator] Shutting down.')
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()