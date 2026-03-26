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
echo -e "${BLUE}[1/7] Aktualizacja systemu i pobieranie narzędzi bazowych...${NC}"
sudo apt-get update && sudo apt-get upgrade -y
sudo apt-get install -y software-properties-common curl gnupg2 lsb-release git wget fuse libfuse2

# 3. Instalacja ROS 2 Humble
echo -e "${BLUE}[2/7] Instalacja ROS 2 Humble...${NC}"
sudo add-apt-repository -y universe
sudo curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key -o /usr/share/keyrings/ros-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros2/ubuntu $(. /etc/os-release && echo $UBUNTU_CODENAME) main" | sudo tee /etc/apt/sources.list.d/ros2.list > /dev/null
sudo apt-get update
sudo apt-get install -y ros-humble-desktop python3-colcon-common-extensions

if ! grep -q "source /opt/ros/humble/setup.bash" ~/.bashrc; then
    echo "source /opt/ros/humble/setup.bash" >> ~/.bashrc
fi

# 4. Instalacja mostu ROS 2 <-> Gazebo
echo -e "${BLUE}[3/7] Instalacja pakietów integrujących ROS 2 z Gazebo...${NC}"
sudo apt-get install -y ros-humble-ros-gz

# 5. Instalacja zależności PX4 i silnika Gazebo
echo -e "${BLUE}[4/7] Instalacja zależności PX4 oraz silnika Gazebo...${NC}"
cd "$REPO_ROOT/external/PX4-Autopilot"
# Używamy oficjalnego skryptu PX4. --no-nuttx wyłącza kompilatory sprzętowe (SITL only)
bash ./Tools/setup/ubuntu.sh --no-nuttx

# 6. Instalacja Micro-XRCE-DDS-Agent (Most komunikacyjny)
echo -e "${BLUE}[5/7] Instalacja Micro-XRCE-DDS-Agent (Kluczowy most ROS 2 <-> PX4)...${NC}"
# Używamy folderu /tmp aby nie generować śmieci w repozytorium!
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
echo -e "${BLUE}[6/7] Instalacja QGroundControl...${NC}"
sudo apt-get remove -y modemmanager || true
sudo apt-get install -y gstreamer1.0-plugins-bad gstreamer1.0-libav gstreamer1.0-gl

# Pobieramy aplikację bezpośrednio do folderu domowego użytkownika
QGC_DIR="$HOME/QGroundControl"
mkdir -p "$QGC_DIR"
if [ ! -f "$QGC_DIR/QGroundControl.AppImage" ]; then
    wget https://github.com/mavlink/qgroundcontrol/releases/download/v4.3.0/QGroundControl.AppImage -O "$QGC_DIR/QGroundControl.AppImage"
    chmod +x "$QGC_DIR/QGroundControl.AppImage"
    echo -e "${GREEN}Pobrano QGroundControl do $QGC_DIR${NC}"
else
    echo -e "${GREEN}QGroundControl już istnieje w systemie.${NC}"
fi
sudo usermod -a -G dialout $(whoami)

# 8. Wstępna kompilacja symulacji
echo -e "${BLUE}[7/7] Pierwsza kompilacja PX4 i drona (to może potrwać kilka minut!)...${NC}"
cd "$REPO_ROOT/external/PX4-Autopilot"
# Kompilujemy z flagą DONT_RUN=1, by symulacja się skompilowała, ale nie włączyła
DONT_RUN=1 make px4_sitl gz_x500

echo -e "${GREEN}========================================================================${NC}"
echo -e "${GREEN}  ŚRODOWISKO FUPLA-droneSIM ZAINSTALOWANE POMYŚLNIE!                    ${NC}"
echo -e "${GREEN}========================================================================${NC}"
echo -e "${BLUE}Zalecany jest restart terminala, aby odświeżyć uprawnienia i zmienne środowiskowe.${NC}"