from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import BlockingOSCUDPServer
import threading
import time

from osc_params import params

osc_receiver_started = False
osc_receiver_lock = threading.Lock()

OSC_RECV_PORTS = params.get("OSC_RECV_PORTS", [50100, 50101, 50102, 50103])

_booted_callbacks = []
_position_callbacks = []

latest_positions = {}  # motor_id: position
latest_position_times = {}  # motor_id: timestamp

# homing status 保持
latest_homing_status = {}  # motor_id: status(int)
latest_homing_status_times = {}  # motor_id: timestamp


def register_booted_callback(cb):
    _booted_callbacks.append(cb)


def register_position_callback(cb):
    _position_callbacks.append(cb)


def get_latest_position(motor_id):
    return latest_positions.get(motor_id)


def get_latest_position_time(motor_id):
    return latest_position_times.get(motor_id)


def register_homing_callback(cb):
    _position_callbacks.append(
        cb
    )  # 既存のコールバックリストを流用するか専用リストを作る場合は変更してください


def get_latest_homing_status(motor_id):
    return latest_homing_status.get(motor_id)


def get_latest_homing_status_time(motor_id):
    return latest_homing_status_times.get(motor_id)


def reset_latest_homing_status(motor_id):
    latest_homing_status.pop(motor_id, None)
    latest_homing_status_times.pop(motor_id, None)


def osc_receive_handler_factory(port):
    def handler(address, *args):
        print(f"Received OSC on port {port}: {address} {args}")
        if address == "/booted":
            for cb in _booted_callbacks:
                cb(port, *args)
        elif address == "/position":
            if len(args) >= 2:
                port_idx = OSC_RECV_PORTS.index(port)
                motor_id = int(args[0]) + port_idx * params.get("VALS_PER_HOST", 8)
                position = int(args[1])
                latest_positions[motor_id] = position
                latest_position_times[motor_id] = time.time()
                for cb in _position_callbacks:
                    cb(port, motor_id, position)
        elif address == "/homingStatus":
            # args: (local_id, status)
            if len(args) >= 2:
                port_idx = OSC_RECV_PORTS.index(port)
                motor_id = int(args[0]) + port_idx * params.get("VALS_PER_HOST", 8)
                status = int(args[1])
                latest_homing_status[motor_id] = status
                latest_homing_status_times[motor_id] = time.time()
                # notify callbacks (reuse position callbacks list or create separate list)
                for cb in _position_callbacks:
                    try:
                        cb(port, motor_id, ("homingStatus", status))
                    except Exception:
                        pass

    return handler


def start_osc_receiver(port):
    dispatcher = Dispatcher()
    dispatcher.set_default_handler(osc_receive_handler_factory(port))
    server = BlockingOSCUDPServer(("0.0.0.0", port), dispatcher)
    print(f"OSC Receiver started on port {port}")
    server.serve_forever()


def start_osc_receiver_thread():
    global osc_receiver_started
    with osc_receiver_lock:
        if osc_receiver_started:
            print("OSC Receiver already running. Skipping duplicate start.")
            return
        osc_receiver_started = True
    for port in OSC_RECV_PORTS:
        recv_thread = threading.Thread(
            target=start_osc_receiver, args=(port,), daemon=True
        )
        recv_thread.start()


def get_motor_client_and_local_id(motor_id):
    from osc_params import VALS_PER_HOST

    hosts = params["HOSTS"]
    host_idx = (motor_id - 1) // VALS_PER_HOST
    if host_idx < 0 or host_idx >= len(hosts):
        return None, None
    from pythonosc.udp_client import SimpleUDPClient

    client = SimpleUDPClient(hosts[host_idx], int(params["PORT"]))
    local_id = ((motor_id - 1) % VALS_PER_HOST) + 1
    return client, local_id
