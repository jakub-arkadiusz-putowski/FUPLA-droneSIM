### INSTALACJA
```bash
git clone --recursive https://github.com/jakub-arkadiusz-putowski/FUPLA-droneSIM.git
cd FUPLA-droneSIM
chmod +x tools/install.sh
./tools/install.sh
```

### PRZYGOTOWANIE HOSTA
```bash
cd ~/FUPLA-droneSIM/docker
docker compose up -d
xhost +local:docker
```

### SYMULACJA
```bash
docker exec -it fupla_dev bash
cd /workspace
source install/setup.bash
ros2 launch fupla_bringup sim.launch.py model:=gz_x500_depth
```

### JOYSTICK
```bash
docker exec -it fupla_dev bash
source /workspace/install/setup.bash
ros2 run joy joy_node &
ros2 run fupla_joy node_joy_to_rc
```

### STREAM WIDEO?
```bash
docker exec -it fupla_dev bash
source /workspace/install/setup.bash
ros2 run fupla_joy stream_to_qgc
```