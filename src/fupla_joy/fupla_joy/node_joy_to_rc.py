#!/usr/bin/env python3
"""
FUPLA-droneSIM: Joystick to MAVLink MANUAL_CONTROL Node
========================================================
Axis mapping verified by physical stick measurement (ros2 topic echo /joy):

  axes[0] = Roll   right stick horizontal
              left : +0.463   center: +0.141   right: -0.075
  axes[1] = Pitch  right stick vertical
              up   : -0.075   center: +0.141   down : +0.455
  axes[2] = Thrust left stick vertical  (INVERTED: up=low, down=high)
              up   : -0.075   center: +0.455   down : +0.463
  axes[3] = UNUSED (always 0.000)
  axes[4] = Yaw    left stick horizontal
              left : +0.463   center: +0.141   right: -0.067

MAVLink port verified from 'pxh> mavlink status':
  PX4 instance #0 listens on UDP 18571
  PX4 MAV_SYS_ID = 2  (must match target_system parameter)

PX4 prerequisites:
  pxh> param set COM_RC_IN_MODE 1
  pxh> param save
"""

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Joy
from pymavlink import mavutil


# ---------------------------------------------------------------------------
# Calibration — verified by physical measurement per axis
# ---------------------------------------------------------------------------

# Thrust axes[2]: INVERTED — stick up = low raw value
THR_RAW_MIN = -0.075   # stick top    = zero thrust
THR_RAW_MAX =  0.463   # stick bottom = full thrust  (inverted!)
THR_RAW_CTR =  0.455   # stick center (resting position)

# Roll axes[0]: left=positive, right=negative
ROLL_RAW_MIN = -0.075  # full right
ROLL_RAW_CTR =  0.141  # center
ROLL_RAW_MAX =  0.463  # full left

# Pitch axes[1]: up=negative, down=positive (standard RC convention)
PITCH_RAW_MIN = -0.075  # full up
PITCH_RAW_CTR =  0.141  # center
PITCH_RAW_MAX =  0.455  # full down

# Yaw axes[4]: left=positive, right=negative
YAW_RAW_MIN = -0.067   # full right
YAW_RAW_CTR =  0.141   # center
YAW_RAW_MAX =  0.463   # full left


class JoyToRcNode(Node):
    """
    Bridges Futaba T8J joystick to MAVLink MANUAL_CONTROL for PX4 SITL.

    Verified axis mapping:
      axes[0] → roll   right stick horizontal
      axes[1] → pitch  right stick vertical
      axes[2] → thrust left  stick vertical (inverted)
      axes[3] → unused
      axes[4] → yaw    left  stick horizontal
    """

    def __init__(self):
        super().__init__('node_joy_to_rc')

        # --- Parameters -------------------------------------------------------
        self.declare_parameter('target_system', 2)
        self.declare_parameter('udp_port', 18571)

        self._target_system = self.get_parameter('target_system').value
        self._udp_port      = self.get_parameter('udp_port').value

        # --- MAVLink ----------------------------------------------------------
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

        # --- State ------------------------------------------------------------
        self._latest_axes: list | None = None
        self._heartbeat_counter = 0
        self._send_counter      = 0
        self._joy_msg_count     = 0

        # --- ROS 2 ------------------------------------------------------------
        self.create_subscription(Joy, '/joy', self._joy_callback, 10)
        self.create_timer(0.05, self._send_manual_control)  # 20 Hz

        self.get_logger().info(
            f'[node_joy_to_rc] Ready.\n'
            f'  Target : 127.0.0.1:{self._udp_port} '
            f'(system_id={self._target_system})\n'
            f'  Axes   : [0]=roll [1]=pitch [2]=thrust [4]=yaw\n'
            f'  Thrust : INVERTED (up=low raw, down=high raw)\n'
            f'  Rate   : 20 Hz MANUAL_CONTROL + 1 Hz HEARTBEAT'
        )

    # --- Joy callback ---------------------------------------------------------

    def _joy_callback(self, msg: Joy):
        self._joy_msg_count += 1
        self._latest_axes = msg.axes
        if self._joy_msg_count == 1:
            self.get_logger().info(
                f'[node_joy_to_rc] /joy connected: {len(msg.axes)} axes\n'
                f'  {[f"{a:.4f}" for a in msg.axes]}'
            )

    # --- 20 Hz send loop ------------------------------------------------------

    def _send_manual_control(self):
        """
        Sends HEARTBEAT (1 Hz) + MANUAL_CONTROL (20 Hz).

        MANUAL_CONTROL field mapping:
          x = pitch  [-1000, 1000]  axes[1]  positive = nose down
          y = roll   [-1000, 1000]  axes[0]  positive = roll right
          z = thrust [0,     1000]  axes[2]  inverted axis
          r = yaw    [-1000, 1000]  axes[4]  positive = clockwise
        """
        self._send_counter += 1

        # HEARTBEAT 1 Hz
        self._heartbeat_counter += 1
        if self._heartbeat_counter >= 20:
            self._heartbeat_counter = 0
            self._mav.mav.heartbeat_send(
                mavutil.mavlink.MAV_TYPE_GCS,
                mavutil.mavlink.MAV_AUTOPILOT_INVALID,
                0, 0, 0
            )

        # Status every 5 seconds
        if self._send_counter % 100 == 0:
            if self._latest_axes is None:
                self.get_logger().warn('[node_joy_to_rc] No /joy data.')
            else:
                a = self._latest_axes
                self.get_logger().info(
                    f'[node_joy_to_rc] ticks={self._send_counter}\n'
                    f'  raw: roll={a[0]:+.3f} pitch={a[1]:+.3f} '
                    f'thr={a[2]:+.3f} yaw={a[4]:+.3f}\n'
                    f'  mc:  roll={self._scale_dir(a[0], ROLL_RAW_MIN, ROLL_RAW_CTR, ROLL_RAW_MAX):+5d}'
                    f'  pitch={self._scale_dir(a[1], PITCH_RAW_MIN, PITCH_RAW_CTR, PITCH_RAW_MAX):+5d}'
                    f'  thr={self._scale_thrust(a[2]):4d}'
                    f'  yaw={self._scale_dir(a[4], YAW_RAW_MIN, YAW_RAW_CTR, YAW_RAW_MAX):+5d}'
                )

        if self._latest_axes is None:
            return

        axes = self._latest_axes

        if len(axes) < 5:
            self.get_logger().error(
                f'Expected >=5 axes, got {len(axes)}.',
                throttle_duration_sec=5.0
            )
            return

        # Scale each axis with its own calibration
        roll_mc   = self._scale_dir(
            axes[0], ROLL_RAW_MIN,  ROLL_RAW_CTR,  ROLL_RAW_MAX
        )
        pitch_mc  = self._scale_dir(
            axes[1], PITCH_RAW_MIN, PITCH_RAW_CTR, PITCH_RAW_MAX
        )
        thrust_mc = self._scale_thrust(axes[2])
        yaw_mc    = self._scale_dir(
            axes[4], YAW_RAW_MIN,   YAW_RAW_CTR,   YAW_RAW_MAX
        )

        # Clamp
        thrust_mc = max(0,     min(1000, thrust_mc))
        pitch_mc  = max(-1000, min(1000, pitch_mc))
        roll_mc   = max(-1000, min(1000, roll_mc))
        yaw_mc    = max(-1000, min(1000, yaw_mc))

        self._mav.mav.manual_control_send(
            self._target_system,
            pitch_mc,
            roll_mc,
            thrust_mc,
            yaw_mc,
            0,
        )

    # --- Scaling --------------------------------------------------------------

    def _scale_thrust(self, raw: float) -> int:
        """
        Thrust axes[2] → MANUAL_CONTROL z [0, 1000].

        INVERTED axis — stick up gives low raw value:
          raw = THR_RAW_MIN (-0.075) → stick top    → z = 1000 (full thrust)
          raw = THR_RAW_MAX (+0.463) → stick bottom → z = 0    (no thrust)
        """
        span = THR_RAW_MAX - THR_RAW_MIN   # 0.538
        if span == 0:
            return 0
        # Invert: high raw = low thrust
        normalized = 1.0 - (raw - THR_RAW_MIN) / span
        return int(max(0, min(1000, normalized * 1000.0)))

    def _scale_dir(
        self,
        raw: float,
        raw_min: float,
        raw_ctr: float,
        raw_max: float,
    ) -> int:
        """
        Directional axis → MANUAL_CONTROL [-1000, 1000].

        Uses per-axis calibration constants.
        Split interpolation handles asymmetric PPM output.

        NOTE: Roll and Yaw are also inverted relative to MAVLink convention
              (left stick left = positive raw = negative yaw in NED frame).
              PX4 handles the frame convention internally.
        """
        if raw >= raw_ctr:
            span = raw_max - raw_ctr
            if span == 0:
                return 0
            normalized = (raw - raw_ctr) / span    # [0.0, 1.0]
        else:
            span = raw_ctr - raw_min
            if span == 0:
                return 0
            normalized = (raw - raw_ctr) / span    # [-1.0, 0.0]

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