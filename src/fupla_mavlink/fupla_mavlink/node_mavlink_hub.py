#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
import subprocess
import os

class MavlinkHubNode(Node):
    def __init__(self):
        super().__init__('node_mavlink_hub')
        
        # Centralny hub będzie odbierał dane z drona (14550) 
        # i rozsyłał je do QGC, Joysticka i innych aplikacji.
        
        self.get_logger().info("Uruchamiam MAVLink Hub (Router)...")
        
        # Używamy systemowego narzędzia mavproxy jako routera
        # --master: skąd przychodzi dron (UDP 14550)
        # --out: gdzie wysyłać (QGC: 14550, Joy: 14580, Extra: 14590)
        cmd = [
            "mavproxy.py",
            "--master=udpin:0.0.0.0:14550",
            "--out=udpout:127.0.0.1:14551", # Dla QGC
            "--out=udpout:127.0.0.1:14580", # Dla naszego Joysticka
            "--nodefault",
            "--nowait"
        ]
        
        self.process = subprocess.Popen(cmd)
        self.get_logger().info("Hub aktywny. Porty: In(14550) -> Out(14551, 14580)")

    def __del__(self):
        if hasattr(self, 'process'):
            self.process.terminate()

def main(args=None):
    rclpy.init(args=args)
    node = MavlinkHubNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()