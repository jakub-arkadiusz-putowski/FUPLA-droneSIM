#!/bin/bash

# Zatrzymuje skrypt, jeśli jakakolwiek komenda zwróci błąd
set -e

# Kolory do ładnego wyświetlania komunikatów (logów instalatora, nie logów aplikacji)
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== Rozpoczynam instalację środowiska FUPLA-droneSIM ===${NC}"

# 1. Sprawdzenie wersji systemu (Wymagane natywne Ubuntu 22.04 lub nasz Docker)
if ! grep -q "Ubuntu 22.04" /etc/os-release; then
    echo -e "${RED}BŁĄD: Ten skrypt musi być uruchomiony na systemie Ubuntu 22.04!${NC}"
    exit 1
fi

echo -e "${GREEN}System operacyjny zweryfikowany: Ubuntu 22.04${NC}"

# 2. Aktualizacja systemu i instalacja podstawowych narzędzi
echo -e "${BLUE}[1/4] Aktualizacja systemu i pobieranie narzędzi bazowych...${NC}"
sudo apt-get update && sudo apt-get upgrade -y
sudo apt-get install -y software-properties-common curl gnupg2 lsb-release git wget

# 3. Instalacja ROS 2 Humble
echo -e "${BLUE}[2/4] Instalacja ROS 2 Humble...${NC}"

# Włączamy repozytoria Universe
sudo apt-get install -y software-properties-common
sudo add-apt-repository -y universe

# Dodajemy klucze GPG dla ROS 2
sudo curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key -o /usr/share/keyrings/ros-archive-keyring.gpg

# Dodajemy repozytorium do źródeł APT
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros2/ubuntu $(. /etc/os-release && echo $UBUNTU_CODENAME) main" | sudo tee /etc/apt/sources.list.d/ros2.list > /dev/null

# Aktualizujemy i instalujemy ROS 2 Desktop (zawiera Rviz, narzędzia rqt, itp.)
sudo apt-get update
sudo apt-get install -y ros-humble-desktop

# Dodanie ROS 2 do ~/.bashrc, by ładował się automatycznie przy otwarciu terminala
if ! grep -q "source /opt/ros/humble/setup.bash" ~/.bashrc; then
    echo "source /opt/ros/humble/setup.bash" >> ~/.bashrc
    echo -e "${GREEN}Dodano ROS 2 do ~/.bashrc${NC}"
fi

# Instalacja colcon (narzędzia do budowania naszego workspace'u)
sudo apt-get install -y python3-colcon-common-extensions

echo -e "${GREEN}=== Część 1 (ROS 2 Humble) zakończona sukcesem! ===${NC}"