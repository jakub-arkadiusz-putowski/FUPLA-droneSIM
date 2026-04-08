#!/bin/bash

#launches a single px4 sitl instance with corrent environment variables
#instance 1 acts as the gazebo server (master)
#instance 2+ run in standalone mode, attaching to the existing gz server

#usage:
#   run_px4_instance.sh <drone_id> <model> [pose]

#arguments:
#   drone_id:   is integer (1=master/gz server, 2+ = client/standalone)
#   model:      px4 gz model name (gz_x500, gz_x500_depth)
#   pose:       spawn pose as "x,y,z,roll,pithc,yaw"

#examples:
#   run_px4_insatnce.sh 1 gz_x500
#   run px4_instance.sh 2 gz_x500_depth "2,0,0.2,0,0,0"

set -e
if [ "$#" -lt 2 ]; then
    echo "[ERROR] Usage: $0 <drone_id> <model> [pose]"
    echo "[ERROR] Example: $0 1 gz_x500"
    exit 1
fi

DRONE_ID="$1"
MODEL="$2"
POSE="${3:-0,0,0.2,0,0,0}"  # Default spawn position if not provided

# --- Path Resolution ----------------------------------------------------------
# Resolve the absolute path to the repository root (two levels up from tools/)
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
REPO_ROOT="$( cd "$SCRIPT_DIR/.." >/dev/null 2>&1 && pwd )"
PX4_PATH="$REPO_ROOT/external/PX4-Autopilot"
PX4_BIN="$PX4_PATH/build/px4_sitl_default/bin/px4"

# --- Pre-flight Checks --------------------------------------------------------

if [ ! -d "$PX4_PATH" ]; then
    echo "[ERROR] PX4-Autopilot not found at: $PX4_PATH"
    echo "[ERROR] Did you run 'git submodule update --init --recursive'?"
    exit 1
fi

if [ ! -f "$PX4_BIN" ]; then
    echo "[ERROR] PX4 binary not found at: $PX4_BIN"
    echo "[ERROR] Did you run 'tools/install.sh'?"
    exit 1
fi

# --- Autostart ID Mapping -----------------------------------------------------
# PX4 SYS_AUTOSTART codes define the vehicle type and default parameters.
# 4001 = Generic Quadrotor (x500)
# 4002 = Generic Quadrotor with Depth Camera (x500_depth)

case "$MODEL" in
    gz_x500)
        AUTOSTART=4001
        ;;
    gz_x500_depth)
        AUTOSTART=4002
        ;;
    *)
        echo "[ERROR] Unknown model: '$MODEL'"
        echo "[ERROR] Supported models: gz_x500, gz_x500_depth"
        exit 1
        ;;
esac

# --- Instance Configuration ---------------------------------------------------
# PX4 uses the instance ID (-i flag) to offset network ports:
#   MAVLink UDP: 14540 + (id - 1)  →  id=1: 14540, id=2: 14541, ...
#   Gazebo:      Instance 1 starts the server; others attach via PX4_GZ_STANDALONE=1

echo "============================================================"
echo " FUPLA-droneSIM: Starting PX4 SITL Instance"
echo "============================================================"
echo "  Drone ID  : $DRONE_ID"
echo "  Model     : $MODEL"
echo "  Autostart : $AUTOSTART"
echo "  Pose      : $POSE"
echo "  PX4 Path  : $PX4_PATH"
echo "============================================================"

# Build the environment variable string based on instance role
if [ "$DRONE_ID" -eq 1 ]; then
    # --- MASTER DRONE (Instance 1) ---
    # This instance is responsible for starting the Gazebo simulation server.
    echo "[INFO] Role: MASTER (Gazebo Server)"
    export PX4_SYS_AUTOSTART="$AUTOSTART"
    export PX4_SIM_MODEL="$MODEL"
    export PX4_GZ_MODEL_POSE="$POSE"
else
    # --- CLIENT DRONE (Instance 2+) ---
    # PX4_GZ_STANDALONE=1 tells PX4 NOT to start a new Gazebo server,
    # but to connect to the already running one from Instance 1.
    echo "[INFO] Role: CLIENT (Attaching to existing Gazebo server)"
    export PX4_SYS_AUTOSTART="$AUTOSTART"
    export PX4_SIM_MODEL="$MODEL"
    export PX4_GZ_MODEL_POSE="$POSE"
    export PX4_GZ_STANDALONE=1
fi

# --- Launch PX4 ---------------------------------------------------------------
# Must cd into PX4_PATH because PX4 uses relative paths internally
cd "$PX4_PATH"
exec "$PX4_BIN" -i "$DRONE_ID"