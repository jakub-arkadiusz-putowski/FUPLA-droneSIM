 # FUPLA-droneSIM

 Integrated simulation environment for drone swarm research and vision algorithms.
 Built on native Ubuntu 22.04 with ROS 2 Humble, PX4 SITL, and Gazebo.

 ## Stack
```text
 | Component | Version |
 |---|---|
 | OS | Ubuntu 22.04 LTS (native) |
 | Middleware | ROS 2 Humble |
 | Autopilot | PX4 v1.14.0 (SITL) |
 | Simulator | Gazebo Garden/Harmonic |
 | GCS | QGroundControl v4.3.0 |
 | RC Transmitter | Futaba T8J (USB/PPM) |
```
 ## Installation

 ```bash
 git clone --recursive https://github.com/jakub-arkadiusz-putowski/FUPLA-droneSIM.git
 cd FUPLA-droneSIM
 chmod +x tools/install.sh
 ```
 ```bash tools/install.sh
 > Note: Open a new terminal after installation to reload the environment.
 ```
 
 ## Usage

 ### 1. Launch simulation (Master drone + Gazebo server + QGC + DDS Agent)

 ```bash
 # Standard quadrotor
 ros2 launch fupla_bringup sim.launch.py

 # Quadrotor with depth camera
 ros2 launch fupla_bringup sim.launch.py model:=gz_x500_depth
 ```

 ### 2. Add more drones (each in a separate terminal)

 ```bash
 # Drone 2 - standard quadrotor
 ros2 launch fupla_bringup add_drone.launch.py id:=2 model:=gz_x500 pose:='2,0,0.2,0,0,0'

 # Drone 3 - quadrotor with depth camera
 ros2 launch fupla_bringup add_drone.launch.py id:=3 model:=gz_x500_depth pose:='4,0,0.2,0,0,0'
 ```

 ### 3. RC control via Futaba T8J

 ```bash
 # Terminal 1: start joystick driver
 ros2 run joy joy_node --ros-args -p device_id:=0

 # Terminal 2: MAVLink bridge for drone 1
 ros2 run fupla_joy node_joy_to_rc

 # Terminal 2: MAVLink bridge for drone 2
 ros2 run fupla_joy node_joy_to_rc --ros-args -p target_system:=2 -p udp_port:=14541
 ```

 ### 4. Video stream to QGroundControl

 ```bash
 # Drone 1 camera (default topic and port)
 ros2 run fupla_joy stream_to_qgc

 # Drone 2 camera (custom topic and port)
 ros2 run fupla_joy stream_to_qgc --ros-args \
 -p image_topic:=/drone2/image_raw \
 -p qgc_port:=5601
 ```

 ## Architecture

```text
 +-------------------------------------------------------------+
 | FUPLA-droneSIM |
 +----------------+---------------+----------------------------+
 | PX4 SITL | Gazebo Sim | ROS 2 Humble |
 | Instance 1 | (Garden) | +---------------------+ |
 | port: 14540 | GZ Server | | MicroXRCEAgent | |
 | | | | node_joy_to_rc | |
 | Instance 2 | GZ Client | | stream_to_qgc | |
 | port: 14541 | (standalone) | +---------------------+ |
 | Instance N | GZ Client | |
 | port: 1454N | (standalone) | |
 +----------------+---------------+----------------------------+
 |
 +----------+---------+
 | QGroundControl |
 | Futaba T8J (USB) |
 +--------------------+
```

 ## Port Reference
```text
 | Service | Port | Protocol |
 |---|---|---|
 | Micro-XRCE-DDS Agent | 8888 | UDP |
 | PX4 MAVLink drone 1 | 14540 | UDP |
 | PX4 MAVLink drone N | 14540 + (N-1) | UDP |
 | QGC Video stream | 5600 | UDP/RTP |
```

 ## Supported Models
```text
 | Model | PX4 Autostart | Description |
 |---|---|---|
 | gz_x500 | 4001 | Standard quadrotor |
 | gz_x500_depth | 4002 | Quadrotor with Intel RealSense depth camera |
```

 ## Repository Structure
```text
 FUPLA-droneSIM/
 +-- external/PX4-Autopilot/ # PX4 firmware (git submodule)
 +-- src/
 | +-- fupla_bringup/ # Launch files orchestration
 | | +-- launch/
 | | +-- sim.launch.py # Main launcher (drone 1 + infrastructure)
 | | +-- add_drone.launch.py # Add drone N to running simulation
 | +-- fupla_joy/ # RC control and video streaming
 | +-- fupla_joy/
 | +-- node_joy_to_rc.py # Futaba T8J -> MAVLink RC override
 | +-- stream_to_qgc.py # ROS 2 camera -> H.264/RTP -> QGC
 +-- tools/
 +-- install.sh # One-command environment installer
 +-- run_px4_instance.sh # PX4 SITL instance launcher
```