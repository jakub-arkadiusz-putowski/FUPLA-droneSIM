#!/bin/bash
# ==============================================================================
# FUPLA-droneSIM: Named Terminal Launcher
# ==============================================================================
# Opens a new gnome-terminal window with a given title and command.
#
# Usage:
#   open_terminal.sh <title> <command>
#
# Examples:
#   open_terminal.sh "Joy Node" "ros2 run joy joy_node"
#   open_terminal.sh "RC Bridge" "ros2 run fupla_joy node_joy_to_rc"
# ==============================================================================

TITLE="${1:-Terminal}"
CMD="${2:-bash}"

gnome-terminal --title="$TITLE" -- bash -c "
    source /opt/ros/humble/setup.bash
    source $HOME/FUPLA-droneSIM/install/setup.bash
    echo '=== $TITLE ==='
    $CMD
    exec bash
"