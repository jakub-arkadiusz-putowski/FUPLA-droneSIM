import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Joy
from pymavlink import mavutil
import time

class DynamicJoyToRC(Node):
    def __init__(self):
        super().__init__('node_joy_to_rc')
        
        # 1. Declaration of parameters for dynamic targeting
        # Usage: ros2 run fupla_joy node_joy_to_rc --ros-args -p target_system:=2
        self.declare_parameter('target_system', 1)
        self.target_id = self.get_parameter('target_system').get_parameter_value().integer_value
        
        # 2. Dynamic Port Calculation
        # PX4 SITL Offset Logic: Base port 14580 + (ID - 1)
        mav_port = 14580 + (self.target_id - 1)
        connection_string = f'udpout:127.0.0.1:{mav_port}'
        
        self.get_logger().info(f"INIT: Controlling Vehicle ID {self.target_id} on port {mav_port}")
        
        # 3. MAVLink Initialization (Source system 255 represents the Ground Station/Joystick)
        self.mav = mavutil.mavlink_connection(connection_string, source_system=255)
        
        self.latest_axes = [0.0] * 8
        self.frame_count = 0
        
        # ROS 2 Subscriptions and Timers
        self.subscription = self.create_subscription(Joy, '/joy', self.joy_callback, 10)
        self.timer = self.create_timer(0.02, self.timer_callback) # 50Hz control loop
        self.hb_timer = self.create_timer(1.0, self.heartbeat_callback) # 1Hz Heartbeat

    def heartbeat_callback(self):
        # Notify PX4 that an external controller is present
        self.mav.mav.heartbeat_send(mavutil.mavlink.MAV_TYPE_GCS, 0, 0, 0, 0)

    def joy_callback(self, msg):
        self.latest_axes = msg.axes

    def timer_callback(self):
        try:
            def get_axis(idx):
                return self.latest_axes[idx] if idx < len(self.latest_axes) else 0.0

            # --- FUTABA T8J CALIBRATED MAPPING ---
            # Throttle (Left vertical): 0.46 (Down) -> 0.14 (Up)
            t_raw = get_axis(2)
            throttle = int((t_raw - 0.46) / (0.14 - 0.46) * 1000)
            
            # Helper for standard axes centered at ~0.30 with +/- 0.16 range
            def map_rc_axis(val):
                if val == 0.0: return 0
                return int((val - 0.30) / 0.16 * 1000)

            yaw   = map_rc_axis(get_axis(0))
            roll  = map_rc_axis(get_axis(1))
            pitch = map_rc_axis(get_axis(3))

            # Safety clamps for MAVLink protocol limits
            throttle = max(0, min(1000, throttle))
            pitch = max(-1000, min(1000, pitch))
            roll = max(-1000, min(1000, roll))
            yaw = max(-1000, min(1000, yaw))

            # Send command to the SPECIFIC target system ID
            self.mav.mav.manual_control_send(
                self.target_id, 
                pitch, roll, throttle, yaw, 
                0 # buttons
            )
            
            if self.frame_count % 100 == 0:
                 self.get_logger().info(f"Target V{self.target_id} | throttle: {throttle} | pitch: {pitch}")
            self.frame_count += 1
            
        except Exception as e:
            self.get_logger().error(f"Mapping Error: {e}")

def main(args=None):
    rclpy.init(args=args)
    node = DynamicJoyToRC()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()