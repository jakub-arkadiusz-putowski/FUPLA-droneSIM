#!/usr/bin/env python3
"""
FUPLA-droneSIM: Joystick to MAVLink RC Override Node
=====================================================
Translates ROS 2 Joy messages from a Futaba T8J RC transmitter (connected via
USB PPM decoder) into MAVLink RC_CHANNELS_OVERRIDE commands sent directly to
a PX4 SITL instance.

Calibration is based on measured raw values from 'ros2 topic echo /joy':
  - Throttle (axes[4]): range [+0.474 ... 0.0]  (inverted: 0.474=min, 0.0=max)
  - Yaw      (axes[0]): range [-0.075 ... +0.463], center ≈ 0.0
  - Pitch    (axes[1]): range [-0.075 ... +0.463], center ≈ 0.0
  - Roll     (axes[2]): range [-0.075 ... +0.463], center ≈ 0.0

MAVLink RC channel range: 1000 (min) ... 1500 (center) ... 2000 (max)

Usage:
    ros2 run fupla_joy node_joy_to_rc
    ros2 run fupla_joy node_joy_to_rc --ros-args -p target_system:=2 -p udp_port:=14541

Parameters:
    target_system (int): MAVLink system ID of the target drone. Default: 1
    udp_port      (int): UDP port of the target PX4 instance. Default: 14540
                         Formula: 14540 + (drone_id - 1)
"""

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Joy
from pymavlink import mavutil


# --- Calibration Constants (Futaba T8J via USB PPM decoder) -------------------
# Measured from 'ros2 topic echo /joy' with physical stick movements.
# These values represent the raw normalized output of ros2 joy_node.

# Throttle axis (axes[4]): physically inverted - resting low = high value
THR_RAW_MIN = 0.474   # Stick at bottom (zero throttle)
THR_RAW_MAX = 0.000   # Stick at top    (full throttle)

# Directional axes (axes[0,1,2]): asymmetric due to PPM decoder characteristics
DIR_RAW_MIN = -0.075  # Full deflection in negative direction
DIR_RAW_MAX = +0.463  # Full deflection in positive direction
DIR_RAW_CTR = 0.000   # Stick centered (confirmed from measurements)

# MAVLink RC channel range (microseconds, standard RC PWM convention)
RC_MIN    = 1000
RC_CENTER = 1500
RC_MAX    = 2000


class JoyToRcNode(Node):
    """
    ROS 2 node that bridges joystick input to MAVLink RC_CHANNELS_OVERRIDE.

    The node maintains a MAVLink UDP connection to a single PX4 instance,
    identified by 'target_system' parameter. To control multiple drones,
    launch multiple instances of this node with different parameters.
    """

    def __init__(self):
        super().__init__('node_joy_to_rc')

        # --- Parameters -------------------------------------------------------
        # target_system: MAVLink system ID (1 = first drone, 2 = second, etc.)
        self.declare_parameter('target_system', 1)
        # udp_port: PX4 SITL MAVLink port (14540 for id=1, 14541 for id=2, ...)
        self.declare_parameter('udp_port', 14540)

        self._target_system = self.get_parameter('target_system').value
        self._udp_port      = self.get_parameter('udp_port').value

        # --- MAVLink Connection -----------------------------------------------
        # 'udpout' mode: this node SENDS to PX4, PX4 does not need to connect first.
        # source_system=255 identifies us as a Ground Control Station (GCS).
        connection_str = f'udpout:127.0.0.1:{self._udp_port}'
        self.get_logger().info(
            f'Connecting to PX4 | system_id={self._target_system} | {connection_str}'
        )
        self._mav = mavutil.mavlink_connection(
            connection_str,
            source_system=255
        )

        # --- State ------------------------------------------------------------
        self._latest_axes = None  # Holds the most recent Joy axes array
        self._heartbeat_counter = 0  # Used to throttle heartbeat to ~1 Hz

        # --- ROS 2 Subscriptions & Timers ------------------------------------
        self.create_subscription(Joy, '/joy', self._joy_callback, 10)

        # Send RC override at 20 Hz (50ms period) - matches PX4 RC input rate
        self.create_timer(0.05, self._send_rc_override)

        self.get_logger().info(
            f'[node_joy_to_rc] Ready. '
            f'Target: system_id={self._target_system}, port={self._udp_port}'
        )

    # --- Callbacks ------------------------------------------------------------

    def _joy_callback(self, msg: Joy):
        """Stores the latest joystick axes for use in the send timer."""
        self._latest_axes = msg.axes

    def _send_rc_override(self):
        """
        Timer callback at 20 Hz.
        Sends MAVLink HEARTBEAT (throttled to 1 Hz) and RC_CHANNELS_OVERRIDE.
        """
        # --- Heartbeat (1 Hz) -------------------------------------------------
        # A GCS heartbeat is required to keep PX4 from triggering RC failsafe.
        # We throttle it inside the 20 Hz timer: send every 20th tick = 1 Hz.
        self._heartbeat_counter += 1
        if self._heartbeat_counter >= 20:
            self._heartbeat_counter = 0
            # type=6 (GCS), autopilot=8 (INVALID/generic), state=0
            self._mav.mav.heartbeat_send(6, 8, 0, 0, 0)

        # --- RC Override ------------------------------------------------------
        # Do not send RC if no joystick data has been received yet.
        if self._latest_axes is None:
            return

        axes = self._latest_axes

        # Map physical axes to MAVLink channels.
        # MAVLink MANUAL_CONTROL uses: x=pitch, y=roll, z=throttle, r=yaw
        # But RC_CHANNELS_OVERRIDE maps directly to RC channels 1-8:
        #   CH1=Roll, CH2=Pitch, CH3=Throttle, CH4=Yaw (standard Mode 2)
        ch_roll     = self._scale_symmetric(axes[2])  # Right stick horizontal
        ch_pitch    = self._scale_symmetric(axes[1])  # Right stick vertical
        ch_throttle = self._scale_throttle(axes[4])   # Left stick vertical
        ch_yaw      = self._scale_symmetric(axes[0])  # Left stick horizontal

        # RC_CHANNELS_OVERRIDE: channels not used are set to 0 (ignored by PX4)
        self._mav.mav.rc_channels_override_send(
            self._target_system,  # target_system
            1,                    # target_component (1 = autopilot)
            ch_roll,              # chan1_raw  (Roll)
            ch_pitch,             # chan2_raw  (Pitch)
            ch_throttle,          # chan3_raw  (Throttle)
            ch_yaw,               # chan4_raw  (Yaw)
            0, 0, 0, 0            # chan5..8 unused
        )

    # --- Calibration Methods --------------------------------------------------

    def _scale_throttle(self, raw: float) -> int:
        """
        Maps throttle axis to RC PWM range [1000, 2000].

        The Futaba T8J throttle is physically inverted via PPM decoder:
          raw = THR_RAW_MIN (0.474) => stick at bottom => RC = 1000 (zero thrust)
          raw = THR_RAW_MAX (0.000) => stick at top    => RC = 2000 (full thrust)

        Linear interpolation with clamping for safety.
        """
        # Normalize to [0.0, 1.0]: 0.0 = no thrust, 1.0 = full thrust
        span = THR_RAW_MIN - THR_RAW_MAX  # = 0.474 (positive span, inverted axis)
        normalized = (THR_RAW_MIN - raw) / span

        # Scale to RC range and clamp
        rc_value = RC_MIN + normalized * (RC_MAX - RC_MIN)
        return int(max(RC_MIN, min(RC_MAX, rc_value)))

    def _scale_symmetric(self, raw: float) -> int:
        """
        Maps a directional axis (yaw/pitch/roll) to RC PWM range [1000, 2000].

        The Futaba T8J directional axes are asymmetric via PPM decoder:
          raw = DIR_RAW_MIN (-0.075) => full negative => RC = 1000
          raw = DIR_RAW_CTR ( 0.000) => centered      => RC = 1500
          raw = DIR_RAW_MAX (+0.463) => full positive  => RC = 2000

        Uses separate scaling for negative and positive halves to handle
        the asymmetric physical range correctly.
        """
        if raw >= DIR_RAW_CTR:
            # Positive half: 0.0 → 0.463 maps to 1500 → 2000
            span = DIR_RAW_MAX - DIR_RAW_CTR  # = 0.463
            if span == 0:
                return RC_CENTER
            normalized = (raw - DIR_RAW_CTR) / span  # [0.0, 1.0]
            rc_value = RC_CENTER + normalized * (RC_MAX - RC_CENTER)
        else:
            # Negative half: -0.075 → 0.0 maps to 1000 → 1500
            span = DIR_RAW_CTR - DIR_RAW_MIN  # = 0.075
            if span == 0:
                return RC_CENTER
            normalized = (raw - DIR_RAW_CTR) / span  # [0.0, 1.0] (negative raw)
            rc_value = RC_CENTER + normalized * (RC_CENTER - RC_MIN)

        return int(max(RC_MIN, min(RC_MAX, rc_value)))


def main(args=None):
    rclpy.init(args=args)
    node = JoyToRcNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.get_logger().info('[node_joy_to_rc] Shutting down.')
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()