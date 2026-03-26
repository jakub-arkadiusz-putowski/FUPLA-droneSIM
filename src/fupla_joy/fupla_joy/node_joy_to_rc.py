#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Joy
from pymavlink import mavutil

class JoyToRCNode(Node):
    def __init__(self):
        super().__init__('node_joy_to_rc')
        self.mav = mavutil.mavlink_connection('udpout:127.0.0.1:14580', source_system=255)
        self.latest_axes = [0.0] * 8
        self.subscription = self.create_subscription(Joy, '/joy', self.joy_callback, 10)
        self.timer = self.create_timer(0.02, self.timer_callback)
        self.hb_timer = self.create_timer(1.0, self.heartbeat_callback)
        self.get_logger().info("KALIBRACJA ZAKOŃCZONA. Dół lewej gałki = GAZ 0.")

    def heartbeat_callback(self):
        self.mav.mav.heartbeat_send(mavutil.mavlink.MAV_TYPE_GCS, 0, 0, 0, 0)

    def joy_callback(self, msg):
        self.latest_axes = msg.axes

    def timer_callback(self):
        try:
            def get_axis(idx):
                return self.latest_axes[idx] if idx < len(self.latest_axes) else 0.0

            # --- MAPOWANIE POD TWÓJ KONKRETNY PAD ---
            
            # 1. LEWA GAŁKA (Góra/Dół) -> GAZ
            # Skoro u Ciebie dół dawał 1000, to teraz dół będzie dawać 0:
            throttle = int((get_axis(1) + 1.0) * 500)
            
            # 2. LEWA GAŁKA (Lewo/Prawo) -> YAW (Obrót)
            yaw = int(get_axis(0) * 1000)
            
            # 3. PRAWA GAŁKA (Góra/Dół) -> PITCH (Przód/Tył)
            # Skoro góra dawała -1000, teraz góra będzie dawać +1000 (leć do przodu):
            pitch = int(get_axis(3) * -1000)
            
            # 4. PRAWA GAŁKA (Lewo/Prawo) -> ROLL (Boki)
            # Skoro prawo dawało -1000, teraz prawo będzie dawać +1000 (leć w prawo):
            roll = int(get_axis(2) * -1000)

            # Bezpieczniki
            throttle = max(0, min(1000, throttle))
            
            # LOG TYLKO GDY MOŻNA STARTOWAĆ
            if throttle < 50:
                self.get_logger().info("GAZ NA ZERO - MOŻESZ UZBRAJAĆ (ARM)!", once=True)

            self.mav.mav.manual_control_send(1, pitch, roll, throttle, yaw, 0)
        except Exception:
            pass

def main(args=None):
    rclpy.init(args=args)
    node = JoyToRCNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()