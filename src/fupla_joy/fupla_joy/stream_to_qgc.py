#!/usr/bin/env python3
"""
FUPLA-droneSIM: Camera Stream to QGroundControl Bridge
=======================================================
Subscribes to a ROS 2 camera image topic and streams video to QGroundControl
via UDP using H.264 encoding over RTP/GStreamer pipeline.

QGroundControl listens on UDP port 5600 by default for video streams.
The GStreamer pipeline encodes frames as H.264 and wraps them in RTP packets.

Prerequisites:
    - GStreamer with x264enc plugin: sudo apt install gstreamer1.0-plugins-bad
    - OpenCV with GStreamer backend: installed via ros-humble-desktop

Usage:
    ros2 run fupla_joy stream_to_qgc
    ros2 run fupla_joy stream_to_qgc --ros-args -p image_topic:=/drone2/image_raw
    ros2 run fupla_joy stream_to_qgc --ros-args -p qgc_port:=5601 -p width:=1280 -p height:=720

Parameters:
    image_topic (str): ROS 2 image topic to subscribe to. Default: '/image_raw'
    qgc_host    (str): QGC UDP destination host. Default: '127.0.0.1'
    qgc_port    (int): QGC UDP destination port. Default: 5600
    width       (int): Output stream width in pixels.  Default: 640
    height      (int): Output stream height in pixels. Default: 480
    fps         (int): Output stream framerate. Default: 20
    bitrate     (int): H.264 encoder bitrate in kbps. Default: 800
"""

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from sensor_msgs.msg import Image
from cv_bridge import CvBridge
import cv2


class StreamToQgcNode(Node):
    """
    ROS 2 node that re-encodes camera frames and streams them to QGroundControl.

    Uses OpenCV's GStreamer backend to create an H.264/RTP pipeline.
    The 'videoconvert ! video/x-raw,format=I420' step is mandatory because
    x264enc requires YUV I420 input, but OpenCV provides BGR frames.
    """

    def __init__(self):
        super().__init__('stream_to_qgc')

        # --- Parameters -------------------------------------------------------
        self.declare_parameter('image_topic', '/image_raw')
        self.declare_parameter('qgc_host',    '127.0.0.1')
        self.declare_parameter('qgc_port',    5600)
        self.declare_parameter('width',       640)
        self.declare_parameter('height',      480)
        self.declare_parameter('fps',         20)
        self.declare_parameter('bitrate',     800)

        image_topic = self.get_parameter('image_topic').value
        qgc_host    = self.get_parameter('qgc_host').value
        qgc_port    = self.get_parameter('qgc_port').value
        self._width  = self.get_parameter('width').value
        self._height = self.get_parameter('height').value
        fps          = self.get_parameter('fps').value
        bitrate      = self.get_parameter('bitrate').value

        # --- GStreamer Pipeline -----------------------------------------------
        # Pipeline stages:
        #   appsrc        : OpenCV feeds raw BGR frames here
        #   videoconvert  : BGR -> I420 (YUV planar, required by x264enc)
        #   x264enc       : H.264 encoding with zero-latency tuning for live stream
        #   rtph264pay    : Packetize H.264 into RTP packets (pt=96 is standard)
        #   udpsink       : Send RTP packets to QGroundControl UDP port
        gst_pipeline = (
            f'appsrc ! '
            f'videoconvert ! '
            f'video/x-raw,format=I420 ! '
            f'x264enc tune=zerolatency bitrate={bitrate} speed-preset=ultrafast ! '
            f'rtph264pay config-interval=1 pt=96 ! '
            f'udpsink host={qgc_host} port={qgc_port}'
        )

        self.get_logger().info(f'GStreamer pipeline: {gst_pipeline}')

        # --- OpenCV VideoWriter -----------------------------------------------
        self._writer = cv2.VideoWriter(
            gst_pipeline,
            cv2.CAP_GSTREAMER,
            0,           # fourcc (unused with GStreamer backend)
            fps,
            (self._width, self._height),
            True         # isColor = True (BGR input)
        )

        if not self._writer.isOpened():
            self.get_logger().error(
                'Failed to open GStreamer VideoWriter pipeline! '
                'Check that gstreamer1.0-plugins-bad and x264 are installed: '
                'sudo apt install gstreamer1.0-plugins-bad gstreamer1.0-libav'
            )
            raise RuntimeError('GStreamer VideoWriter failed to open')

        self.get_logger().info(
            f'Video stream started: {self._width}x{self._height}@{fps}fps '
            f'-> {qgc_host}:{qgc_port} (H.264/RTP)'
        )

        # --- ROS 2 Setup ------------------------------------------------------
        self._bridge = CvBridge()
        self._frame_count = 0

        # Use BEST_EFFORT QoS to match the ros_gz_bridge camera topic profile.
        # RELIABLE would cause backpressure and frame accumulation.
        qos = QoSProfile(
            depth=10,
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST,
        )

        self.create_subscription(Image, image_topic, self._image_callback, qos)
        self.get_logger().info(f'Subscribed to: {image_topic}')

    # --- Callbacks ------------------------------------------------------------

    def _image_callback(self, msg: Image):
        """
        Converts a ROS 2 Image message to OpenCV BGR, resizes if needed,
        and writes the frame into the GStreamer pipeline.
        """
        try:
            # Convert ROS Image to OpenCV BGR (handles encoding differences)
            frame = self._bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')

            # Resize to configured output resolution if source differs
            if frame.shape[1] != self._width or frame.shape[0] != self._height:
                frame = cv2.resize(frame, (self._width, self._height))

            # Write frame into GStreamer pipeline (non-blocking)
            self._writer.write(frame)

            # Log throughput every 100 frames (~5 seconds at 20fps)
            self._frame_count += 1
            if self._frame_count % 100 == 0:
                self.get_logger().info(
                    f'Stream alive: {self._frame_count} frames sent to QGC'
                )

        except Exception as exc:
            self.get_logger().error(f'Frame processing error: {exc}')

    def destroy_node(self):
        """Ensure GStreamer pipeline is flushed and closed on shutdown."""
        self.get_logger().info('Releasing GStreamer pipeline...')
        if self._writer.isOpened():
            self._writer.release()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = StreamToQgcNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()