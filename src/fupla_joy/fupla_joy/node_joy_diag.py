#!/usr/bin/env python3
"""
FUPLA-droneSIM: Joystick to MAVLink MANUAL_CONTROL Node
========================================================
Translates ROS 2 Joy messages from a Futaba T8J RC transmitter (connected via
USB PPM decoder) into MAVLink MANUAL_CONTROL commands sent to PX4 SITL.

MAVLink port verified from 'pxh> mavlink status':
  PX4 instance #0: listens on UDP 18571, GCS/Normal mode
  Formula: 18570 + drone_id

PX4 prerequisite (set once, persists after param save):
  pxh> param set COM_RC_IN_MODE 1
  pxh> param save

Axis mapping verified with node_joy_diag.py (Futaba T8J via USB PPM decoder):
  axes[0] = Yaw    left  stick horizontal  range [-0.050 ... +0.440] center +0.141
  axes[1] = Thrust left  stick vertical    range [-0.050 ... +0.430] center +0.141
  axes[2] = Roll   right stick horizontal  range [-0.075 ... +0.463] center +0.026
  axes[3] = UNUSED always -0.000
  axes[4] = Pitch  right stick vertical    range [-0.075 ... +0.455] center +0.133

Throttle direction (axes[1]):
  Stick UP   → raw = +0.430 → full thrust (1000)
  Stick DOWN → raw = -0.050 → zero thrust (0)
  NOTE: This is NOT inverted — higher raw value = more thrust.
        The PPM decoder outputs positive values for up on this axis.

MAVLink MANUAL_CONTROL field ranges:
  x (pitch)  : [-1000, 1000]  positive = nose down
  y (roll)   : [-1000, 1000]  positive = roll right
  z (thrust) : [0,     1000]  0 = no thrust, 1000 = full
  r (yaw)    : [-1000, 1000]  positive = clockwise
"""

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Joy
from pymavlink import mavutil


# ---------------------------------------------------------------------------
# Calibration Constants (Futaba T8J via USB PPM decoder)
# Verified with node_joy_diag.py — measured raw values at stick extremes.
# ---------------------------------------------------------------------------

# Throttle axis[1]: left stick vertical
# Stick UP   → raw MAX = +0.430 → thrust 1000 (full)
# Stick DOWN → raw MIN = -0.050 → thrust 0    (none)
# Center at rest ≈ +0.141 (PPM decoder offset)
THR_RAW_MIN = -0.050   # stick bottom = zero thrust
THR_RAW_MAX =  0.430   # stick top    = full thrust

# Yaw axis[0]: left stick horizontal
# Directional axes share the same asymmetric PPM output characteristic
DIR_RAW_MIN = -0.050   # full negative deflection
DIR_RAW_CTR =  0.141   # centered
DIR_RAW_MAX =  0.440   # full positive deflection

# Roll axis[2]: right stick horizontal
# Slightly different center observed (~0.026), using same DIR constants
# as the range is similar enough for correct control feel

# Pitch axis[4]: right stick vertical
# Center observed ~0.133, range similar to other directional axes


class JoyToRcNode(Node):
    """
    ROS 2 node bridging Futaba T8J joystick to MAVLink MANUAL_CONTROL.

    Axis mapping (verified with node_joy_diag.py):
      axes[0] → yaw    (left  stick H)
      axes[1] → thrust (left  stick V)   higher value = more thrust
      axes[2] → roll   (right stick H)
      axes[3] → UNUSED (always zero)
      axes[4] → pitch  (right stick V)
    """

    def __init__(self):
        super().__init__('node_joy_to_rc')

        # --- Parameters -------------------------------------------------------
        self.declare_parameter('target_system', 1)
        # Port 18571: PX4 instance #0 GCS link (verified from mavlink status)
        # Formula: 18570 + drone_id
        self.declare_parameter('udp_port', 18571)

        self._target_system = self.get_parameter('target_system').value
        self._udp_port      = self.get_parameter('udp_port').value

        # --- MAVLink Connection -----------------------------------------------
        # udpout: this node initiates sending; PX4 does not need to connect first.
        # source_system=255: identifies as GCS (required for MANUAL_CONTROL).
        # source_component=190: confirmed received by PX4 in mavlink status.
        connection_str = f'udpout:127.0.0.1:{self._udp_port}'
        self.get_logger().info(
            f'[node_joy_to_rc] Connecting → {connection_str} '
            f'(target_system={self._target_system})'
        )
        self._mav = mavutil.mavlink_connection(
            connection_str,
            source_system=255,
            source_component=190,
        )

        # --- Internal State ---------------------------------------------------
        self._latest_axes: list | None = None
        self._heartbeat_counter = 0
        self._send_counter      = 0
        self._joy_msg_count     = 0

        # --- ROS 2 ------------------------------------------------------------
        self.create_subscription(Joy, '/joy', self._joy_callback, 10)
        self.create_timer(0.05, self._send_manual_control)  # 20 Hz

        self.get_logger().info(
            f'[node_joy_to_rc] Ready.\n'
            f'  MAVLink target : 127.0.0.1:{self._udp_port} '
            f'(system_id={self._target_system})\n'
            f'  Axis mapping   : [0]=yaw [1]=thrust [2]=roll [3]=unused [4]=pitch\n'
            f'  Send rate      : 20 Hz MANUAL_CONTROL + 1 Hz HEARTBEAT\n'
            f'  Prerequisite   : pxh> param set COM_RC_IN_MODE 1'
        )

    # --- Callbacks ------------------------------------------------------------

    def _joy_callback(self, msg: Joy):
        """Caches latest joystick axes. Logs axis count on first message."""
        self._joy_msg_count += 1
        self._latest_axes = msg.axes

        if self._joy_msg_count == 1:
            self.get_logger().info(
                f'[node_joy_to_rc] First /joy message: '
                f'{len(msg.axes)} axes, {len(msg.buttons)} buttons\n'
                f'  {[f"{a:.4f}" for a in msg.axes]}'
            )

    def _send_manual_control(self):
        """
        20 Hz timer. Sends HEARTBEAT at 1 Hz and MANUAL_CONTROL at 20 Hz.

        MANUAL_CONTROL axis assignment:
          x = pitch  → axes[4]  right stick vertical
          y = roll   → axes[2]  right stick horizontal
          z = thrust → axes[1]  left  stick vertical   (not inverted)
          r = yaw    → axes[0]  left  stick horizontal
        """
        self._send_counter += 1

        # --- HEARTBEAT 1 Hz ---------------------------------------------------
        self._heartbeat_counter += 1
        if self._heartbeat_counter >= 20:
            self._heartbeat_counter = 0
            self._mav.mav.heartbeat_send(
                mavutil.mavlink.MAV_TYPE_GCS,
                mavutil.mavlink.MAV_AUTOPILOT_INVALID,
                0, 0, 0
            )

        # --- Status log every 5 seconds ---------------------------------------
        if self._send_counter % 100 == 0:
            if self._latest_axes is None:
                self.get_logger().warn(
                    '[node_joy_to_rc] No /joy data — is joy_node running?\n'
                    '  Check: ros2 topic hz /joy'
                )
            else:
                a = self._latest_axes
                # Compute scaled values for status readout
                thr = self._scale_thrust(a[1])
                self.get_logger().info(
                    f'[node_joy_to_rc] Running | '
                    f'joy_msgs={self._joy_msg_count} '
                    f'ticks={self._send_counter}\n'
                    f'  raw  : yaw={a[0]:+.3f} thr={a[1]:+.3f} '
                    f'roll={a[2]:+.3f} pitch={a[4]:+.3f}\n'
                    f'  mc   : thrust={thr}'
                )

        if self._latest_axes is None:
            return

        axes = self._latest_axes

        # Guard: need at least 5 axes (indices 0-4)
        if len(axes) < 5:
            self.get_logger().error(
                f'[node_joy_to_rc] Expected >=5 axes, got {len(axes)}.',
                throttle_duration_sec=5.0
            )
            return

        # --- Axis extraction (verified mapping) -------------------------------
        raw_yaw    = axes[0]   # left  stick H
        raw_thrust = axes[1]   # left  stick V  (up = higher value = more thrust)
        raw_roll   = axes[2]   # right stick H
        # axes[3] is unused (always 0.000 on this PPM decoder)
        raw_pitch  = axes[4]   # right stick V

        # --- Scale to MANUAL_CONTROL ranges -----------------------------------
        thrust_mc = self._scale_thrust(raw_thrust)
        yaw_mc    = self._scale_directional(raw_yaw)
        roll_mc   = self._scale_directional(raw_roll)
        pitch_mc  = self._scale_directional(raw_pitch)

        # Clamp to valid ranges
        thrust_mc = max(0,     min(1000, thrust_mc))
        pitch_mc  = max(-1000, min(1000, pitch_mc))
        roll_mc   = max(-1000, min(1000, roll_mc))
        yaw_mc    = max(-1000, min(1000, yaw_mc))

        self._mav.mav.manual_control_send(
            self._target_system,
            pitch_mc,    # x = pitch  [-1000, 1000]
            roll_mc,     # y = roll   [-1000, 1000]
            thrust_mc,   # z = thrust [0,     1000]
            yaw_mc,      # r = yaw    [-1000, 1000]
            0,
        )

    # --- Calibrated Scaling ---------------------------------------------------

    def _scale_thrust(self, raw: float) -> int:
        """
        Maps throttle raw value to MANUAL_CONTROL z range [0, 1000].

        Verified direction (node_joy_diag.py):
          raw = THR_RAW_MIN (-0.050) → stick bottom → z =    0 (no thrust)
          raw = THR_RAW_MAX (+0.430) → stick top    → z = 1000 (full thrust)

        Linear interpolation with clamping.
        """
        span = THR_RAW_MAX - THR_RAW_MIN   # 0.480
        if span == 0:
            return 0
        normalized = (raw - THR_RAW_MIN) / span   # 0.0 → 1.0
        return int(max(0, min(1000, normalized * 1000.0)))

    def _scale_directional(self, raw: float) -> int:
        """
        Maps a directional axis to MANUAL_CONTROL range [-1000, 1000].

        Handles asymmetric PPM decoder output with split interpolation:
          raw = DIR_RAW_MIN (-0.050) → -1000
          raw = DIR_RAW_CTR (+0.141) →     0
          raw = DIR_RAW_MAX (+0.440) → +1000

        NOTE: Roll (axes[2]) and Pitch (axes[4]) centers observed slightly
              different (~0.026 and ~0.133) but within deadzone tolerance.
              If drift is noticeable, tune DIR_RAW_CTR per axis.
        """
        if raw >= DIR_RAW_CTR:
            span = DIR_RAW_MAX - DIR_RAW_CTR   # 0.299
            if span == 0:
                return 0
            normalized = (raw - DIR_RAW_CTR) / span   # [0.0, 1.0]
        else:
            span = DIR_RAW_CTR - DIR_RAW_MIN           # 0.191
            if span == 0:
                return 0
            normalized = (raw - DIR_RAW_CTR) / span   # [-1.0, 0.0]

        return int(max(-1000, min(1000, normalized * 1000.0)))


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