#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from rclpy.qos import QoSProfile, ReliabilityPolicy
import cv2
from cv_bridge import CvBridge

class ImageToQGC(Node):
    def __init__(self):
        super().__init__('image_to_qgc')
        # Ustawiamy Best Effort, aby dopasować się do mostka
        qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.BEST_EFFORT)
        self.subscription = self.create_subscription(Image, '/image_raw', self.listener_callback, qos)
        self.bridge = CvBridge()
        self.frame_count = 0
        
        # PANCERNY RUROCIĄG H.264 DLA QGC
        # Dodajemy videoconvert do I420 (YUV) - bez tego QGC często nie widzi obrazu
        gst_pipeline = (
            'appsrc ! videoconvert ! video/x-raw,format=I420 ! '
            'x264enc tune=zerolatency bitrate=800 speed-preset=ultrafast ! '
            'rtph264pay config-interval=1 pt=96 ! udpsink host=127.0.0.1 port=5600'
        )
        
        self.video_writer = cv2.VideoWriter(gst_pipeline, cv2.CAP_GSTREAMER, 0, 20, (640, 480), True)
        self.get_logger().info("Mostek wideo H.264 (I420) wystartował na porcie 5600")

    def listener_callback(self, data):
        try:
            # Konwersja i zmiana rozmiaru
            cv_image = self.bridge.imgmsg_to_cv2(data, "bgr8")
            cv_image = cv2.resize(cv_image, (640, 480))
            
            # Wysyłamy klatkę
            self.video_writer.write(cv_image)
            
            # Logujemy co 50 klatek, żeby wiedzieć, że skrypt żyje
            self.frame_count += 1
            if self.frame_count % 50 == 0:
                self.get_logger().info(f"Wysłano {self.frame_count} klatek do QGC...")
        except Exception as e:
            self.get_logger().error(f"Błąd: {e}")

def main(args=None):
    rclpy.init(args=args)
    node = ImageToQGC()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()