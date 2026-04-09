#!/bin/bash
# ==============================================================================
# FUPLA-droneSIM: Environment Installer
# ==============================================================================
# Description:
#   One-command installer for the complete FUPLA-droneSIM simulation environment
#   on Ubuntu 22.04. Installs and configures:
#     - ROS 2 Humble (with all required packages)
#     - PX4 Autopilot SITL (with Gazebo Garden/Harmonic)
#     - Micro-XRCE-DDS-Agent (PX4 <-> ROS 2 bridge)
#     - QGroundControl v4.3.0
#     - FUPLA-droneSIM ROS 2 workspace
#
# Usage:
#   bash tools/install.sh
#
# Requirements:
#   - Ubuntu 22.04 LTS (native)
#   - Internet connection
#   - Git submodules initialized:
#       git submodule update --init --recursive
#
# ==============================================================================

set -e  # Exit immediately on any error

# --- Terminal Colors ----------------------------------------------------------
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# --- Path Resolution ----------------------------------------------------------
# Resolve absolute path to repo root regardless of where the script is called from
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
REPO_ROOT="$( cd "$SCRIPT_DIR/.." >/dev/null 2>&1 && pwd )"

# --- Helper Functions ---------------------------------------------------------

print_step() {
    echo -e "\n${BLUE}================================================================${NC}"
    echo -e "${BLUE}  $1${NC}"
    echo -e "${BLUE}================================================================${NC}"
}

print_ok() {
    echo -e "${GREEN}[OK] $1${NC}"
}

print_warn() {
    echo -e "${YELLOW}[WARN] $1${NC}"
}

print_error() {
    echo -e "${RED}[ERROR] $1${NC}"
}

# ==============================================================================
# PRE-FLIGHT CHECKS
# ==============================================================================

echo -e "${BLUE}"
echo "================================================================"
echo "   FUPLA-droneSIM Environment Installer"
echo "================================================================"
echo -e "${NC}"
echo "  Repository root : $REPO_ROOT"
echo "  Script location : $SCRIPT_DIR"
echo ""

# --- Check: Ubuntu 22.04 ------------------------------------------------------
if ! grep -q "Ubuntu 22.04" /etc/os-release; then
    print_error "This script requires Ubuntu 22.04 LTS."
    print_error "Current OS: $(grep PRETTY_NAME /etc/os-release | cut -d= -f2)"
    exit 1
fi
print_ok "OS verified: Ubuntu 22.04 LTS"

# --- Check: Git submodules ----------------------------------------------------
#verify that all required submodules are initialized before proceeding.
#required submodules are:
# - external/PX4-Autopilot:     px4 firmware and gazebo models
# - src/px4_msgs:               ros2 message definitions for px4 uORB topics
if [ ! -f "$REPO_ROOT/external/PX4-Autopilot/CMakeLists.txt" ]; then
    print_error "PX4-Autopilot submodule is not initialized."
    print_error "Please run: git submodule update --init --recursive"
    exit 1
fi

if [! -f "$REPO_ROOT/src/px4_msgs/package.xml" ]; then
    print_error "px4_msgs submodule is not initialized."
    print_errot "please run: git submodule update --init --recursive"
    exit 1

fi

print_ok "Git submodules verified (PX4-Autopilot, px4_msgs)"

# --- Check: Not running as root -----------------------------------------------
if [ "$EUID" -eq 0 ]; then
    print_error "Do not run this script as root. Use a regular user with sudo privileges."
    exit 1
fi
print_ok "User privileges verified (running as: $USER)"

# ==============================================================================
# STEP 1/7 - System Update & Base Tools
# ==============================================================================
print_step "[1/7] System update and base tools"

sudo apt-get update && sudo apt-get upgrade -y
sudo apt-get install -y \
    software-properties-common \
    curl \
    gnupg2 \
    lsb-release \
    git \
    wget \
    fuse \
    libfuse2 \
    python3-pip \
    build-essential

print_ok "Base tools installed"

# ==============================================================================
# STEP 2/7 - ROS 2 Humble
# ==============================================================================
print_step "[2/7] ROS 2 Humble installation"

# Add ROS 2 apt repository if not already present
if [ ! -f "/etc/apt/sources.list.d/ros2.list" ]; then
    sudo add-apt-repository -y universe
    sudo curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key \
        -o /usr/share/keyrings/ros-archive-keyring.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] \
        http://packages.ros.org/ros2/ubuntu $(. /etc/os-release && echo $UBUNTU_CODENAME) main" \
        | sudo tee /etc/apt/sources.list.d/ros2.list > /dev/null
    sudo apt-get update
    print_ok "ROS 2 repository added"
else
    print_warn "ROS 2 repository already configured, skipping"
fi

sudo apt-get install -y \
    ros-humble-desktop \
    ros-humble-joy \
    ros-humble-ros-gz \
    ros-humble-rmw-cyclonedds-cpp \
    python3-colcon-common-extensions \
    python3-cv-bridge

# Add ROS 2 source to .bashrc (idempotent)
if ! grep -q "source /opt/ros/humble/setup.bash" ~/.bashrc; then
    echo "" >> ~/.bashrc
    echo "# ROS 2 Humble - added by FUPLA-droneSIM installer" >> ~/.bashrc
    echo "source /opt/ros/humble/setup.bash" >> ~/.bashrc
    print_ok "ROS 2 environment added to ~/.bashrc"
else
    print_warn "ROS 2 already sourced in ~/.bashrc, skipping"
fi

print_ok "ROS 2 Humble installed"

# ==============================================================================
# STEP 3/7 - Python Dependencies
# ==============================================================================
print_step "[3/7] Python dependencies"

# Pin numpy below 2.0 to avoid breaking changes with MAVLink and CV packages
pip3 install pymavlink "numpy<2"

print_ok "Python dependencies installed"

# ==============================================================================
# STEP 4/7 - PX4 Dependencies & Gazebo
# ==============================================================================
print_step "[4/7] PX4 dependencies and Gazebo simulation engine"

cd "$REPO_ROOT/external/PX4-Autopilot"

# The official PX4 setup script installs Gazebo and all required dependencies.
# --no-nuttx skips the embedded firmware toolchain (not needed for SITL).
bash ./Tools/setup/ubuntu.sh --no-nuttx

print_ok "PX4 dependencies and Gazebo installed"

# ==============================================================================
# STEP 5/7 - Micro-XRCE-DDS-Agent
# ==============================================================================
print_step "[5/7] Micro-XRCE-DDS-Agent (PX4 <-> ROS 2 bridge)"

# Build from source for maximum compatibility with PX4 v1.14
XRCE_BUILD_DIR="/tmp/Micro-XRCE-DDS-Agent-build"
rm -rf "$XRCE_BUILD_DIR"
git clone https://github.com/eProsima/Micro-XRCE-DDS-Agent.git "$XRCE_BUILD_DIR"

cd "$XRCE_BUILD_DIR"
mkdir build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release
make -j"$(nproc)"
sudo make install
sudo ldconfig /usr/local/lib/

print_ok "Micro-XRCE-DDS-Agent installed"

# ==============================================================================
# STEP 6/7 - QGroundControl v4.3.0
# ==============================================================================
print_step "[6/7] QGroundControl v4.3.0"

# Remove modemmanager - it interferes with serial/USB connections (e.g., Futaba T8J)
sudo apt-get remove -y modemmanager 2>/dev/null || true

# Install GStreamer plugins required for QGC video streaming
sudo apt-get install -y \
    gstreamer1.0-plugins-bad \
    gstreamer1.0-libav \
    gstreamer1.0-gl

QGC_DIR="$HOME/QGroundControl"
QGC_APPIMAGE="$QGC_DIR/QGroundControl.AppImage"

mkdir -p "$QGC_DIR"

if [ ! -f "$QGC_APPIMAGE" ]; then
    wget \
        "https://github.com/mavlink/qgroundcontrol/releases/download/v4.3.0/QGroundControl.AppImage" \
        -O "$QGC_APPIMAGE"
    chmod +x "$QGC_APPIMAGE"
    print_ok "QGroundControl downloaded to: $QGC_APPIMAGE"
else
    print_warn "QGroundControl already exists at: $QGC_APPIMAGE, skipping download"
fi

# Add user to dialout group for USB device access (Futaba T8J, serial ports)
# NOTE: Group change takes effect on next login
sudo usermod -a -G dialout "$USER"
print_ok "User '$USER' added to dialout group (re-login required)"

# ==============================================================================
# STEP 7/7 - Build PX4 SITL & ROS 2 Workspace
# ==============================================================================
print_step "[7/7] Building PX4 SITL and FUPLA ROS 2 workspace"

# --- PX4 SITL Build ---
# DONT_RUN=1 tells PX4 to build only, without launching the simulation.
# We build all supported models to ensure binaries are ready.
cd "$REPO_ROOT/external/PX4-Autopilot"

echo "Building PX4 SITL for model: gz_x500 ..."
DONT_RUN=1 make px4_sitl gz_x500

echo "Building PX4 SITL for model: gz_x500_depth ..."
DONT_RUN=1 make px4_sitl gz_x500_depth

print_ok "PX4 SITL built for: gz_x500, gz_x500_depth"

# --- ROS 2 Workspace Build ---
cd "$REPO_ROOT"
source /opt/ros/humble/setup.bash
colcon build --symlink-install

# Add workspace overlay to .bashrc (idempotent)
SETUP_LINE="source $REPO_ROOT/install/setup.bash"
if ! grep -q "$SETUP_LINE" ~/.bashrc; then
    echo "" >> ~/.bashrc
    echo "# FUPLA-droneSIM workspace overlay - added by installer" >> ~/.bashrc
    echo "$SETUP_LINE" >> ~/.bashrc
    print_ok "Workspace overlay added to ~/.bashrc"
else
    print_warn "Workspace overlay already in ~/.bashrc, skipping"
fi

print_ok "FUPLA ROS 2 workspace built"

# ==============================================================================
# INSTALLATION COMPLETE
# ==============================================================================

echo -e "\n${GREEN}"
echo "================================================================"
echo "   FUPLA-droneSIM Installation Complete!"
echo "================================================================"
echo -e "${NC}"
echo "  Next steps:"
echo ""
echo "  1. Open a NEW terminal (to reload .bashrc with ROS 2 + workspace)"
echo ""
echo "  2. Launch the simulation:"
echo "       ros2 launch fupla_bringup sim.launch.py model:=gz_x500"
echo "       ros2 launch fupla_bringup sim.launch.py model:=gz_x500_depth"
echo ""
echo "  3. Add more drones (in a separate terminal):"
echo "       ros2 launch fupla_bringup add_drone.launch.py id:=2 model:=gz_x500 pose:='2,0,0.2'"
echo ""
echo "  NOTE: You may need to log out and back in for the"
echo "        'dialout' group change to take effect (USB/serial access)."
echo ""