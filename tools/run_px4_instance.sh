#!/bin/bash
# $1 - PX4 Binary path
# $2 - ROMFS path
# $3 - Instance number
# $4 - Model name
# $5 - Drone ID (MODEL_NAME suffix)

cd "$2" # Wchodzimy do ROMFS/px4fmu_common
export PX4_SIM_MODEL="$4"
export PX4_GZ_MODEL_NAME="x500_$5"
export PX4_GZ_WORLD="default"
export PX4_GZ_HEADLESS="1"
export GZ_PARTITION="fupla_sim"
export PX4_ROMFS_DIR="$2"

# Odpalamy binarkę
"$1" -i "$3" -s etc/init.d-posix/rcS -d