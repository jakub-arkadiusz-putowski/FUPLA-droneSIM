# FUPLA-droneSIM

Integrated multi-drone simulation environment for swarm research and
vision algorithms. Built on native Ubuntu 22.04 with ROS 2 Humble,
PX4 SITL, and Gazebo.

## Stack

| Component        | Version              |
|------------------|----------------------|
| OS               | Ubuntu 22.04 LTS     |
| Middleware        | ROS 2 Humble         |
| Autopilot        | PX4 v1.14 (SITL)    |
| Simulator        | Gazebo Garden        |
| GCS              | QGroundControl v4.3  |
| RC Transmitter   | Futaba T8J (USB/PPM) |

---

## Installation

```bash
cd ~
git clone --recursive https://github.com/jakub-arkadiusz-putowski/FUPLA-droneSIM.git
cd FUPLA-droneSIM
bash tools/install.sh
source /opt/ros/humble/setup.bash
colcon build --symlink-install
source install/setup.bash
```

Open a **new terminal** after installation completes.

```bash
ros2 launch fupla_bringup sim.launch.py
```
> **Note:** If you use a USB joystick (Futaba T8J), log out and back in
> after installation for the `dialout` group change to take effect.

---

## Quick Start

```bash
ros2 launch fupla_bringup sim.launch.py
```

This single command starts the complete simulation pipeline:

| # | Component | Delay |
|---|-----------|-------|
| 1 | Micro-XRCE-DDS Agent | immediate |
| 2 | QGroundControl | immediate |
| 3 | Gazebo server | immediate |
| 4 | PX4 SITL (drone 1) | 10s |
| 5 | joy_node (joystick driver) | 5s |
| 6 | node_joy_to_rc (RC bridge) | 15s |
| 7 | node_px4_configurator (auto param upload) | 20s |

After ~25 seconds:
- Gazebo opens with drone spawned
- QGroundControl connects automatically
- Joystick (Futaba T8J) is active
- PX4 parameters are configured automatically

### First flight

1. Wait for QGroundControl to show **Ready To Fly**
2. Switch flight mode to **Stabilized** or **Manual** in QGC
3. Arm via QGC (red circle → Arm) or PX4 shell:
   ```
   pxh> commander arm -f
   ```
4. Push left stick up to take off

---

## Launch Options

```bash
# Standard quadrotor (default)
ros2 launch fupla_bringup sim.launch.py

# Quadrotor with depth camera
ros2 launch fupla_bringup sim.launch.py model:=gz_x500_depth

# Custom spawn position
ros2 launch fupla_bringup sim.launch.py pose:='2,0,0.2,0,0,0'

# Custom joystick device (default: 0 = /dev/input/js0)
ros2 launch fupla_bringup sim.launch.py joy_device_id:=1
```

---

## Multi-Drone Setup

Add drones to a running simulation (each in a separate terminal):

```bash
# Drone 2
ros2 launch fupla_bringup add_drone.launch.py \
    id:=2 model:=gz_x500 pose:='2,0,0.2,0,0,0'

# Drone 3
ros2 launch fupla_bringup add_drone.launch.py \
    id:=3 model:=gz_x500_depth pose:='4,0,0.2,0,0,0'
```

---

## ROS 2 Topics

Telemetry topics available for other teams (drone 1):

```bash
# List all available topics
ros2 topic list | grep px4_1

# Key topics
ros2 topic echo /px4_1/fmu/out/vehicle_local_position
ros2 topic echo /px4_1/fmu/out/vehicle_attitude
ros2 topic echo /px4_1/fmu/out/vehicle_status
ros2 topic echo /px4_1/fmu/out/vehicle_gps_position
ros2 topic echo /px4_1/fmu/out/sensor_combined
```

Topic namespace pattern: `/px4_<id>/fmu/out/<topic_name>`

---

## Joystick Diagnostics

If the joystick is not responding, identify axis mapping:

```bash
ros2 run fupla_joy node_joy_diag
```

Move each stick one at a time and observe which `axes[N]` index changes.

Verified axis mapping for **Futaba T8J via USB PPM decoder**:

| axes[] | Function | Stick |
|--------|----------|-------|
| axes[0] | Roll | right horizontal |
| axes[1] | Pitch | right vertical |
| axes[2] | Thrust | left vertical (inverted) |
| axes[3] | Unused | — |
| axes[4] | Yaw | left horizontal |

---

## PX4 Parameters

PX4 parameters are uploaded automatically from
`config/px4/sitl_params.yaml` on every simulation start.

No manual `param set` commands are required.

To modify parameters, edit the YAML file:

```yaml
# config/px4/sitl_params.yaml

# Use integer literals for INT32 parameters
COM_RC_IN_MODE: 1

# Use float literals (with decimal point) for REAL32 parameters
COM_RC_LOSS_T: 3.0
```

To verify parameters after launch:

```bash
pxh> param show COM_RC_IN_MODE
pxh> param show COM_RC_LOSS_T
```

---

## Port Reference

| Service | Port | Protocol |
|---------|------|----------|
| Micro-XRCE-DDS Agent | 8888 | UDP |
| PX4 MAVLink GCS (drone 1) | 18571 | UDP |
| PX4 MAVLink onboard (drone 1) | 14581 | UDP |
| QGroundControl | 14550 | UDP |
| QGC video stream | 5600 | UDP/RTP |

---

## Supported Models

| Model | Autostart | Description |
|-------|-----------|-------------|
| `gz_x500` | 4001 | Standard quadrotor |
| `gz_x500_depth` | 4002 | Quadrotor with depth camera |

---

## Repository Structure

```
FUPLA-droneSIM/
├── config/
│   └── px4/
│       └── sitl_params.yaml       # PX4 SITL parameters (auto-uploaded)
├── external/
│   └── PX4-Autopilot/             # PX4 firmware (git submodule)
├── src/
│   ├── fupla_bringup/
│   │   └── launch/
│   │       ├── sim.launch.py          # Main launcher
│   │       ├── add_drone.launch.py    # Add drone to running sim
│   │       └── swarm.launch.py        # Launch drone swarm
│   └── fupla_joy/
│       └── fupla_joy/
│           ├── node_joy_to_rc.py      # Joystick → MAVLink MANUAL_CONTROL
│           ├── node_joy_diag.py       # Axis identification tool
│           ├── node_px4_configurator.py # Auto PX4 parameter upload
│           └── stream_to_qgc.py       # Camera → H.264/RTP → QGC
└── tools/
    ├── install.sh                 # One-command environment installer
    ├── run_px4_instance.sh        # PX4 SITL instance launcher
    └── open_terminal.sh           # Named terminal launcher
```

---

## Troubleshooting

### QGC shows "Not Ready" on startup
Switch flight mode to **Stabilized** or **Manual** in QGC.
Position mode requires GPS which is not available in SITL by default.

### Joystick not detected
```bash
ls /dev/input/js*          # verify device exists
jstest /dev/input/js0      # test raw joystick input
ros2 topic hz /joy         # verify ROS 2 publishing
```

### Drone does not respond to sticks
```bash
# In PX4 shell — verify parameters were uploaded:
pxh> param show COM_RC_IN_MODE    # must be 1
pxh> param show MAV_SYS_ID        # note this value

# Verify joystick data reaches PX4:
pxh> listener manual_control_input
```

### Failsafe triggers immediately on arm
```bash
pxh> param show COM_RC_LOSS_T     # must be 3.0
pxh> param show COM_RCL_EXCEPT    # must be 4
```

### node_joy_to_rc sends to wrong drone
`target_system` must match `MAV_SYS_ID` in PX4.
Check: `pxh> param show MAV_SYS_ID`
Default in this repo: `MAV_SYS_ID = 2`

---

## Requirements

- Ubuntu 22.04 LTS (native, not VM or WSL)
- 8 GB RAM minimum (16 GB recommended)
- GPU recommended for Gazebo rendering
- Internet connection for installation
- Futaba T8J RC transmitter with USB PPM decoder (optional)