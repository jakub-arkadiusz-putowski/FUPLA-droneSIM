#!/bin/bash

# Zatrzymuje skrypt, jeśli jakakolwiek komenda zwróci błąd
set -e

# Kolory
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Zapisujemy absolutną ścieżkę do głównego folderu repozytorium
REPO_ROOT="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." >/dev/null 2>&1 && pwd )"

echo -e "${BLUE}=== Rozpoczynam instalację środowiska FUPLA-droneSIM ===${NC}"

# 1. Sprawdzenie wersji systemu
if ! grep -q "Ubuntu 22.04" /etc/os-release; then
    echo -e "${RED}BŁĄD: Ten skrypt musi być uruchomiony na systemie Ubuntu 22.04!${NC}"
    exit 1
fi
echo -e "${GREEN}System operacyjny zweryfikowany: Ubuntu 22.04${NC}"

# 2. Aktualizacja systemu i narzędzia bazowe
echo -e "${BLUE}[1/8] Aktualizacja systemu i pobieranie narzędzi bazowych...${NC}"
sudo apt-get update && sudo apt-get upgrade -y
sudo apt-get install -y software-properties-common curl gnupg2 lsb-release git wget fuse libfuse2 python3-pip

# 3. Instalacja ROS 2 Humble
echo -e "${BLUE}[2/8] Instalacja ROS 2 Humble i dodatków...${NC}"
sudo add-apt-repository -y universe
sudo curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key -o /usr/share/keyrings/ros-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros2/ubuntu $(. /etc/os-release && echo $UBUNTU_CODENAME) main" | sudo tee /etc/apt/sources.list.d/ros2.list > /dev/null
sudo apt-get update
# Dodano ros-humble-joy oraz rmw-cyclonedds dla stabilności wizji
sudo apt-get install -y ros-humble-desktop python3-colcon-common-extensions ros-humble-joy ros-humble-rmw-cyclonedds-cpp python3-cv-bridge

if ! grep -q "source /opt/ros/humble/setup.bash" ~/.bashrc; then
    echo "source /opt/ros/humble/setup.bash" >> ~/.bashrc
fi

# 4. Instalacja mostu ROS 2 <-> Gazebo i Python MAVLink
echo -e "${BLUE}[3/8] Instalacja bibliotek Python i mostów...${NC}"
sudo apt-get install -y ros-humble-ros-gz
# Naprawa błędu NumPy 2.0 i instalacja MAVLinka
pip3 install pymavlink "numpy<2"

# 5. Instalacja zależności PX4 i silnika Gazebo
echo -e "${BLUE}[4/8] Instalacja zależności PX4 oraz silnika Gazebo...${NC}"
cd "$REPO_ROOT/external/PX4-Autopilot"
# Używamy oficjalnego skryptu PX4
bash ./Tools/setup/ubuntu.sh --no-nuttx

# 6. Instalacja Micro-XRCE-DDS-Agent (Most komunikacyjny)
echo -e "${BLUE}[5/8] Instalacja Micro-XRCE-DDS-Agent...${NC}"
cd /tmp
rm -rf Micro-XRCE-DDS-Agent
git clone https://github.com/eProsima/Micro-XRCE-DDS-Agent.git
cd Micro-XRCE-DDS-Agent
mkdir build && cd build
cmake ..
make -j$(nproc)
sudo make install
sudo ldconfig /usr/local/lib/

# 7. Instalacja QGroundControl
echo -e "${BLUE}[6/8] Instalacja QGroundControl v4.3.0...${NC}"
sudo apt-get remove -y modemmanager || true
sudo apt-get install -y gstreamer1.0-plugins-bad gstreamer1.0-libav gstreamer1.0-gl

QGC_DIR="$HOME/QGroundControl"
mkdir -p "$QGC_DIR"
if [ ! -f "$QGC_DIR/QGroundControl.AppImage" ]; then
    wget https://github.com/mavlink/qgroundcontrol/releases/download/v4.3.0/QGroundControl.AppImage -O "$QGC_DIR/QGroundControl.AppImage"
    chmod +x "$QGC_DIR/QGroundControl.AppImage"
fi
sudo usermod -a -G dialout $(whoami)

# 8. Kompilacja Workspace FUPLA i PX4
echo -e "${BLUE}[7/8] Budowanie całego projektu (to potrwa kilka minut!)...${NC}"
# Budujemy PX4 (model depth z kamerą)
cd "$REPO_ROOT/external/PX4-Autopilot"
DONT_RUN=1 make px4_sitl gz_x500_depth

# Budujemy paczki ROS 2
cd "$REPO_ROOT"
source /opt/ros/humble/setup.bash
colcon build

echo -e "${GREEN}========================================================================${NC}"
echo -e "${GREEN}  ŚRODOWISKO FUPLA-droneSIM ZAINSTALOWANE POMYŚLNIE!                    ${NC}"
echo -e "${GREEN}========================================================================${NC}"
echo -e "${BLUE}1. Otwórz nowy terminal.${NC}"
echo -e "${BLUE}2. Wpisz: source install/setup.bash${NC}"
echo -e "${BLUE}3. Uruchom: ros2 launch fupla_bringup sim.launch.py model:=gz_x500_depth${NC}"