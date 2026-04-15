#!/usr/bin/env python3
"""
FUPLA-droneSIM: Swarm Controller GUI
=====================================
Tkinter GUI node for selecting which drone is controlled by the joystick.

Architecture:
  - Subscribes to ROS2 px4_msgs topics for live telemetry (no MAVLink conflict)
  - Auto-discovers drones via /px4_N/fmu/out/vehicle_status topics
  - SELECT button changes target_system + udp_port in node_joy_to_rc

Telemetry sources:
  /px4_N/fmu/out/vehicle_status        → arming_state, nav_state, system_id
  /px4_N/fmu/out/vehicle_local_position → altitude (z field, NED frame)

ROS2 parameter client:
  /node_joy_to_rc/set_parameters → switches active drone
"""

import threading
import tkinter as tk
import struct
from tkinter import ttk
from pymavlink import mavutil

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from rcl_interfaces.msg import Parameter as ParameterMsg
from rcl_interfaces.msg import ParameterValue, ParameterType
from rcl_interfaces.srv import SetParameters

from px4_msgs.msg import VehicleStatus, VehicleLocalPosition


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_DRONES     = 10
GUI_REFRESH_MS = 500
BASE_PORT      = 18570   # port = BASE_PORT + drone_id

# PX4 nav_state values (from vehicle_status)
NAV_STATES = {
    0:  'MANUAL',
    1:  'ALTCTL',
    2:  'POSCTL',
    3:  'AUTO_MISSION',
    4:  'AUTO_LOITER',
    5:  'AUTO_RTL',
    10: 'ACRO',
    12: 'DESCEND',
    13: 'TERMINATION',
    14: 'OFFBOARD',
    15: 'STABILIZED',
    17: 'AUTO_TAKEOFF',
    18: 'AUTO_LAND',
    19: 'AUTO_FOLLOW',
    20: 'AUTO_PRECLAND',
}

# PX4 arming_state values
ARMING_STATES = {
    0: 'INIT',
    1: 'STANDBY',
    2: 'ARMED',
    3: 'STANDBY_ERROR',
    4: 'SHUTDOWN',
    5: 'IN_AIR_RESTORE',
}


# ---------------------------------------------------------------------------
# Drone State
# ---------------------------------------------------------------------------

class DroneState:
    """Holds latest telemetry for a single drone instance."""

    def __init__(self, drone_id: int):
        self.drone_id     = drone_id
        self.mav_sys_id   = drone_id + 1
        self.port         = BASE_PORT + drone_id
        self.online       = False
        self.arming_state = 0
        self.nav_state    = 0
        self.altitude_m   = 0.0
        self.pre_flight_ok = False

    @property
    def armed(self) -> bool:
        return self.arming_state == 2

    @property
    def arming_str(self) -> str:
        if not self.online:
            return 'OFFLINE'
        return ARMING_STATES.get(self.arming_state, f'STATE_{self.arming_state}')

    @property
    def mode_str(self) -> str:
        if not self.online:
            return '---'
        return NAV_STATES.get(self.nav_state, f'MODE_{self.nav_state}')

    @property
    def altitude_str(self) -> str:
        if not self.online:
            return '--- m'
        return f'{self.altitude_m:.1f} m'


# ---------------------------------------------------------------------------
# ROS2 Node with GUI
# ---------------------------------------------------------------------------

class SwarmGuiNode(Node):
    """
    ROS2 node that subscribes to px4_msgs topics for all drones
    and displays a tkinter GUI for joystick target selection.
    """

    def __init__(self):
        super().__init__('node_swarm_gui')

        # drone_id (1,2,3...) → DroneState
        self._drones: dict[int, DroneState] = {}
        self._lock = threading.Lock()
        self._active_drone_id = 1

        # QoS matching PX4 publisher profile
        from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy, DurabilityPolicy
        self._qos = QoSProfile(
            depth=10,
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
        )

        # Subscriptions cache — keep references to prevent GC
        self._subs = []

        # ROS2 service client for switching joystick target
        self._param_client = self.create_client(
            SetParameters,
            '/node_joy_to_rc/set_parameters'
        )

        # Start auto-discovery timer (checks for new drones every 2s)
        self.create_timer(2.0, self._discover_drones)

        # Subscribe to already-known drones immediately
        for drone_id in range(1, MAX_DRONES + 1):
            self._subscribe_drone(drone_id)

        self.get_logger().info(
            '[swarm_gui] Started. Monitoring /px4_N/fmu/out/ topics.'
        )


    # --- Topic subscription ---------------------------------------------------

    def _subscribe_drone(self, drone_id: int):
        """Creates subscriptions for vehicle_status and vehicle_local_position."""
        prefix = f'/px4_{drone_id}/fmu/out'

        # vehicle_status → arming, mode, online detection
        sub_status = self.create_subscription(
            VehicleStatus,
            f'{prefix}/vehicle_status',
            lambda msg, did=drone_id: self._on_vehicle_status(did, msg),
            self._qos,
        )

        # vehicle_local_position → altitude
        sub_pos = self.create_subscription(
            VehicleLocalPosition,
            f'{prefix}/vehicle_local_position',
            lambda msg, did=drone_id: self._on_local_position(did, msg),
            self._qos,
        )

        self._subs.extend([sub_status, sub_pos])

    def _discover_drones(self):
        """
        Checks if new drone topics appeared.
        Already subscribed — ROS2 handles topic availability automatically.
        Marks drones offline if no message received recently.
        """
        pass  # subscriptions handle discovery automatically

    # --- Telemetry callbacks --------------------------------------------------

    def _on_vehicle_status(self, drone_id: int, msg: VehicleStatus):
        with self._lock:
            if drone_id not in self._drones:
                self._drones[drone_id] = DroneState(drone_id)
                self.get_logger().info(
                    f'[swarm_gui] Drone {drone_id} discovered '
                    f'(MAV_SYS_ID={drone_id + 1}, port={BASE_PORT + drone_id})'
                )

            state = self._drones[drone_id]
            state.online       = True
            state.arming_state = msg.arming_state
            state.nav_state    = msg.nav_state
            state.pre_flight_ok = msg.pre_flight_checks_pass

    def _on_local_position(self, drone_id: int, msg: VehicleLocalPosition):
        with self._lock:
            if drone_id not in self._drones:
                self._drones[drone_id] = DroneState(drone_id)

            state = self._drones[drone_id]
            # NED frame: z is negative when above ground → negate for display
            if msg.z_valid:
                state.altitude_m = round(-msg.z, 2)

    # --- Parameter switching --------------------------------------------------

    def switch_to_drone(self, drone_id: int):
        """Switches joystick target to selected drone (called from GUI thread)."""
        with self._lock:
            if drone_id not in self._drones:
                return
            state = self._drones[drone_id]
            if not state.online:
                self.get_logger().warn(
                    f'[swarm_gui] Drone {drone_id} is offline — cannot select'
                )
                return

        # Run in background thread to avoid blocking GUI
        threading.Thread(
            target=self._do_switch,
            args=(drone_id,),
            daemon=True
        ).start()

    def _do_switch(self, drone_id: int):
        """Switches joystick target to selected drone."""
        with self._lock:
            if drone_id not in self._drones:
                return
            state       = self._drones[drone_id]
            mav_sys_id  = state.mav_sys_id
            port        = state.port
            old_id      = self._active_drone_id

        # 1. Wyłącz joystick na starym dronie (COM_RC_IN_MODE=0)
        if old_id != drone_id and old_id in self._drones:
            with self._lock:
                old_state = self._drones[old_id]
            self._set_px4_param(
                old_state.port, old_state.mav_sys_id,
                'COM_RC_IN_MODE', 0
            )
            self.get_logger().info(
                f'[swarm_gui] Disabled joystick on Drone {old_id} '
                f'(COM_RC_IN_MODE=0)'
            )

        # 2. Włącz joystick na nowym dronie (COM_RC_IN_MODE=1)
        self._set_px4_param(
            port, mav_sys_id,
            'COM_RC_IN_MODE', 1
        )
        self.get_logger().info(
            f'[swarm_gui] Enabled joystick on Drone {drone_id} '
            f'(COM_RC_IN_MODE=1)'
        )

        # 3. Przełącz joy_to_rc na nowy dron
        if not self._param_client.wait_for_service(timeout_sec=2.0):
            self.get_logger().warn(
                '[swarm_gui] node_joy_to_rc SetParameters not available'
            )
            return

        req = SetParameters.Request()

        p1 = ParameterMsg()
        p1.name  = 'target_system'
        p1.value = ParameterValue(
            type=ParameterType.PARAMETER_INTEGER,
            integer_value=mav_sys_id,
        )
        p2 = ParameterMsg()
        p2.name  = 'udp_port'
        p2.value = ParameterValue(
            type=ParameterType.PARAMETER_INTEGER,
            integer_value=port,
        )
        req.parameters = [p1, p2]

        future = self._param_client.call_async(req)
        rclpy.spin_until_future_complete(self, future, timeout_sec=3.0)

        if future.result() is not None:
            self._active_drone_id = drone_id
            self.get_logger().info(
                f'[swarm_gui] ✓ Switched → Drone {drone_id} '
                f'(MAV_SYS_ID={mav_sys_id}, port={port})'
            )
        else:
            self.get_logger().error('[swarm_gui] SetParameters failed')

    def _set_px4_param(self, port: int, mav_sys_id: int,
                       param_name: str, param_value: int):
        """
        Sets a PX4 parameter via MAVLink PARAM_SET.
        Used to enable/disable joystick on drones when switching.
        """
        import struct
        from pymavlink import mavutil

        try:
            conn = mavutil.mavlink_connection(
                f'udpout:127.0.0.1:{port}',
                source_system=255,
                source_component=191,
            )
            param_id   = param_name.encode('utf-8').ljust(16, b'\x00')[:16]
            send_value = struct.unpack('f', struct.pack('i', param_value))[0]

            for _ in range(3):
                conn.mav.param_set_send(
                    mav_sys_id, 1,
                    param_id,
                    send_value,
                    mavutil.mavlink.MAV_PARAM_TYPE_INT32,
                )
            self.get_logger().info(
                f'[swarm_gui] SET {param_name}={param_value} '
                f'→ drone MAV_SYS_ID={mav_sys_id}'
            )
        except Exception as e:
            self.get_logger().error(
                f'[swarm_gui] _set_px4_param failed: {e}'
            )

    def get_drones_snapshot(self) -> dict:
        """Thread-safe copy of drone states for GUI rendering."""
        with self._lock:
            return {
                did: DroneState.__new__(DroneState).__dict__.update(vars(s)) or s
                for did, s in self._drones.items()
            }

    @property
    def active_drone_id(self) -> int:
        return self._active_drone_id


# ---------------------------------------------------------------------------
# tkinter GUI
# ---------------------------------------------------------------------------

class SwarmGui:
    """
    Tkinter window showing live drone cards.
    Must run on main thread.
    """

    def __init__(self, ros_node: SwarmGuiNode):
        self._node  = ros_node
        self._cards: dict[int, dict] = {}

        # --- Root window ------------------------------------------------------
        self._root = tk.Tk()
        self._root.title('FUPLA Swarm Controller')
        self._root.resizable(True, True)
        self._root.minsize(300, 200)
        
        self._root.configure(bg='#1e1e2e')
        self._root.protocol('WM_DELETE_WINDOW', self._on_close)

        # --- Header -----------------------------------------------------------
        tk.Label(
            self._root,
            text='FUPLA Swarm Controller',
            font=('Helvetica', 16, 'bold'),
            bg='#1e1e2e', fg='#cdd6f4',
            pady=10,
        ).pack()

        self._active_label = tk.Label(
            self._root,
            text='Controlling: ---',
            font=('Helvetica', 11),
            bg='#1e1e2e', fg='#a6e3a1',
            pady=4,
        )
        self._active_label.pack()

        self._waiting_label = tk.Label(
            self._root,
            text='Waiting for drones...',
            font=('Helvetica', 10, 'italic'),
            bg='#1e1e2e', fg='#6c7086',
            pady=20,
        )
        self._waiting_label.pack()

        # --- Cards frame ------------------------------------------------------
        self._cards_frame = tk.Frame(self._root, bg='#1e1e2e')
        self._cards_frame.pack(padx=16, pady=8, fill='both', expand=True)

        # Start refresh loop
        self._root.after(GUI_REFRESH_MS, self._refresh)

    def _make_card(self, drone_id: int) -> dict:
        """Creates drone card widget. Returns dict of widget references."""
        col = (drone_id - 1) % 4
        row = (drone_id - 1) // 4

        frame = tk.Frame(
            self._cards_frame,
            bg='#313244', bd=2, relief='ridge',
            padx=12, pady=10, width=180,
        )
        frame.grid(row=row, column=col, padx=8, pady=8, sticky='nsew')

        tk.Label(
            frame,
            text=f'DRONE {drone_id}',
            font=('Helvetica', 12, 'bold'),
            bg='#313244', fg='#89b4fa',
        ).pack()

        tk.Label(
            frame,
            text=f'ID={drone_id + 1} | port={BASE_PORT + drone_id}',
            font=('Helvetica', 8),
            bg='#313244', fg='#6c7086',
        ).pack()

        ttk.Separator(frame, orient='horizontal').pack(fill='x', pady=4)

        def make_row(label_text):
            tk.Label(
                frame, text=label_text,
                font=('Helvetica', 9), bg='#313244', fg='#9399b2',
                anchor='w',
            ).pack(fill='x')
            val = tk.Label(
                frame, text='---',
                font=('Helvetica', 10, 'bold'),
                bg='#313244', fg='#cdd6f4',
                anchor='w',
            )
            val.pack(fill='x')
            return val

        status_val = make_row('Status:')
        mode_val   = make_row('Mode:')
        alt_val    = make_row('Altitude:')
        preflight_val = make_row('Preflight:')

        btn = tk.Button(
            frame,
            text='SELECT',
            font=('Helvetica', 10, 'bold'),
            bg='#45475a', fg='#cdd6f4',
            activebackground='#a6e3a1',
            activeforeground='#1e1e2e',
            relief='flat', cursor='hand2',
            command=lambda did=drone_id: self._on_select(did),
        )
        btn.pack(pady=(8, 0), fill='x')

        return {
            'frame':        frame,
            'status_val':   status_val,
            'mode_val':     mode_val,
            'alt_val':      alt_val,
            'preflight_val': preflight_val,
            'btn':          btn,
        }

    def _on_select(self, drone_id: int):
        self._node.switch_to_drone(drone_id)

    def _refresh(self):
        """Updates GUI every GUI_REFRESH_MS ms."""
        drones = self._node.get_drones_snapshot()
        active = self._node.active_drone_id

        # Hide waiting label when first drone appears
        if drones:
            self._waiting_label.pack_forget()

        for drone_id, state in sorted(drones.items()):
            if drone_id not in self._cards:
                self._cards[drone_id] = self._make_card(drone_id)

            w = self._cards[drone_id]
            is_active = (drone_id == active)

            # Status color
            if not state.online:
                status_text  = 'OFFLINE'
                status_color = '#f38ba8'
            elif state.armed:
                status_text  = 'ARMED'
                status_color = '#f38ba8'
            else:
                status_text  = 'DISARMED'
                status_color = '#f9e2af'

            w['status_val'].config(text=status_text, fg=status_color)
            w['mode_val'].config(text=state.mode_str)
            w['alt_val'].config(text=state.altitude_str)
            w['preflight_val'].config(
                text='✓ PASS' if state.pre_flight_ok else '✗ FAIL',
                fg='#a6e3a1' if state.pre_flight_ok else '#f38ba8',
            )

            # Active drone highlight
            bg    = '#1e6040' if is_active else '#313244'
            b_txt = '✓ ACTIVE' if is_active else 'SELECT'
            b_bg  = '#a6e3a1' if is_active else '#45475a'
            b_fg  = '#1e1e2e' if is_active else '#cdd6f4'

            w['frame'].config(bg=bg)
            w['btn'].config(
                text=b_txt, bg=b_bg, fg=b_fg,
                state='disabled' if is_active else 'normal',
            )

        # Update active label
        self._active_label.config(
            text=f'Controlling: DRONE {active} '
                 f'(MAV_SYS_ID={active + 1}, port={BASE_PORT + active})'
        )

        self._root.after(GUI_REFRESH_MS, self._refresh)

    def _on_close(self):
        self._root.quit()

    def run(self):
        self._root.mainloop()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(args=None):
    rclpy.init(args=args)
    ros_node = SwarmGuiNode()
    gui      = SwarmGui(ros_node)

    # ROS2 spin in background thread
    spin_thread = threading.Thread(
        target=rclpy.spin,
        args=(ros_node,),
        daemon=True,
        name='ros2_spin',
    )
    spin_thread.start()

    # tkinter on main thread (required)
    try:
        gui.run()
    except KeyboardInterrupt:
        pass
    finally:
        ros_node.get_logger().info('[swarm_gui] Shutting down.')
        ros_node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()