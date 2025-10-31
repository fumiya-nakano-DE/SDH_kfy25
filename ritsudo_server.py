from flask import Flask, render_template, request, redirect, url_for, jsonify
from threading import Thread, Event
import sys, time, socket, os
from flask_socketio import SocketIO
from logger_config import logger

from osc_params import (
    get_params_full,
    get_params_mode,
    set_param_full,
    set_param_mode,
    set_params,
    MOTOR_POSITION_MAPPING,
    LOCKED_KEYS,
)

import osc_sender
from osc_sender import (
    send_all_setTargetPositionList,
    get_clients,
    osc_sender,
    filter_vals,
    get_prev_vals,
    set_prev_vals,
    get_current_speed,
    gh_reset,
    set_repeat_mode,
)
from osc_receiver import (
    start_osc_receiver_thread,
    register_booted_callback,
    get_latest_position,
    get_latest_position_time,
    get_latest_homing_status,
    get_latest_homing_status_time,
    reset_latest_homing_status,
)

from osc_listener import (
    register_bundle_callback,
    start_osc_listener_thread,
    register_message_callback,
)
from osc_speaker import osc_speaker

from pythonosc.udp_client import SimpleUDPClient

app = Flask(__name__, static_folder="static", template_folder="templates")
socketio = SocketIO(app)

osc_thread = None
stop_event = Event()
position_broadcast_thread = None
position_broadcast_stop = Event()
home_all_thread = None
home_all_stop = Event()
home_all_result = None


# --- Helpers ---
def get_motor_client_and_local_id(motor_id):
    # motor_id: 1 -> NUM_SERVOS
    from osc_params import VALS_PER_HOST

    params_full = get_params_full()

    hosts = params_full["HOSTS"]
    host_idx = (motor_id - 1) // VALS_PER_HOST
    if host_idx < 0 or host_idx >= len(hosts):
        return None, None
    client = SimpleUDPClient(hosts[host_idx], int(params_full["PORT"]))
    local_id = ((motor_id - 1) % VALS_PER_HOST) + 1
    return client, local_id


def enable_servo(client, enable=True, local_id=None, broadcast=True):
    flag = 1 if enable else 0
    if broadcast or local_id is None:
        client.send_message("/enableServoMode", [255, flag])
    else:
        client.send_message("/enableServoMode", [local_id, flag])


def disable_motor(motor_id):
    client, local_id = get_motor_client_and_local_id(motor_id)
    if client is None:
        logger.error("disable_motor: motor_id %d out of range", motor_id)
        return
    client.send_message("/hardHiZ", [local_id])
    logger.debug(
        f"Disabled motor {motor_id} (client: {client._address}, local_id: {local_id})"
    )
    return


def wait_for_latest_position(motor_id, timeout=1.0, poll_interval=0.05):
    prev_time = get_latest_position_time(motor_id) or 0
    end_time = time.time() + timeout
    while time.time() < end_time:
        pos = get_latest_position(motor_id)
        pos_time = get_latest_position_time(motor_id) or 0
        if pos is not None and pos_time > prev_time:
            return pos
        time.sleep(poll_interval)
    return None


def wait_for_homing_complete(motor_id, timeout=12.0, poll_interval=0.05):
    end_time = time.time() + float(timeout)
    while time.time() < end_time:
        st = get_latest_homing_status(motor_id)
        if st is not None and int(st) >= 3:
            return int(st)
        time.sleep(poll_interval)
    return None


def wait_for_booted(booted_ports, expected_ports, wait_time=10.0, steps=50):

    elapsed = 0
    for _ in range(steps + 1):
        if len(booted_ports) >= expected_ports:
            logger.debug(
                f">>Boot detected on port(s): {sorted(booted_ports)}, proceeding."
            )
            return True
        time.sleep(wait_time / steps)
        elapsed += wait_time / steps
        sys.stdout.write(f"\rWaiting for boot... {elapsed:.1f}s ")
    logger.warning(
        f"\nERROR: /booted was not received from all {expected_ports} devices. Received from: {sorted(booted_ports)}"
    )
    return False


# --- Position Broadcasting ---
def position_broadcast_worker(stop_event):
    """Broadcast current servo positions via WebSocket"""
    while not stop_event.is_set():
        try:
            positions = get_prev_vals()
            if positions is not None:
                params_full = get_params_full()
                stroke_offset = params_full.get("STROKE_OFFSET", 50000)
                # Calculate relative positions from offset
                relative_positions = [int(pos - stroke_offset) for pos in positions]

                socketio.emit(
                    "servo_positions",
                    {"positions": relative_positions, "offset": stroke_offset},
                )

            time.sleep(0.1)  # 10Hz update rate
        except Exception as e:
            logger.error(f"Position broadcast error: {e}")
            time.sleep(0.5)


def start_position_broadcast():
    global position_broadcast_thread, position_broadcast_stop
    if position_broadcast_thread is None or not position_broadcast_thread.is_alive():
        position_broadcast_stop.clear()
        position_broadcast_thread = Thread(
            target=position_broadcast_worker,
            args=(position_broadcast_stop,),
            daemon=True,
        )
        position_broadcast_thread.start()
        logger.info("Position broadcast thread started.")


def stop_position_broadcast():
    global position_broadcast_stop, position_broadcast_thread
    position_broadcast_stop.set()
    if position_broadcast_thread is not None:
        position_broadcast_thread.join(timeout=1)
        position_broadcast_thread = None
    logger.info("Position broadcast thread stopped.")


# --- HTML Endpoints ---
def start():
    global osc_thread, stop_event
    if osc_thread is None or not osc_thread.is_alive():
        stop_event.clear()
        osc_thread = Thread(target=osc_sender, args=(stop_event,), daemon=True)
        osc_thread.start()
        logger.info("OSC Sender thread started.")
        start_position_broadcast()
        return True
    return False


def stop():
    global stop_event, osc_thread
    stop_event.set()
    if osc_thread is not None:
        osc_thread.join(timeout=2)
        osc_thread = None
    logger.info("OSC Sender thread stopped.")
    stop_position_broadcast()


@app.route("/", methods=["GET", "POST"])
def index():
    global osc_thread, stop_event
    running = osc_thread is not None and osc_thread.is_alive()

    params_full = get_params_full()
    mode_id = str(params_full.get("MODE", "1"))
    params_mode = get_params_mode()
    render_params = params_full.copy()
    render_params.update(params_mode)
    render_params["MODE"] = mode_id
    render_params["MODES"] = params_full.get("MODES", {})
    if request.method == "POST":
        if not running:
            for key in ["PORT", "NUM_SERVOS", "RATE_fps", "ALPHA"]:
                if key in request.form:
                    set_param_full(
                        key,
                        type(params_full[key])(request.form.get(key, params_full[key])),
                    )
            running = start()
        else:
            stop()
    return render_template("index.html", **render_params, running=running)


@app.route("/stop", methods=["POST"])
def stop_endpoint():
    stop()
    return redirect(url_for("index"))


def halt():
    clients = get_clients()
    for client in clients:
        client.send_message("/hardHiZ", [255])
    stop()
    logger.info(">>Emergency Stop<<<")
    return


@app.route("/halt", methods=["POST", "GET"])
def halt_endpoint():
    halt()
    return jsonify(result="OK")


def setNeutral():
    params_full = get_params_full()
    target_vals = [params_full.get("STROKE_OFFSET", 50000)] * params_full["NUM_SERVOS"]
    interval = 0.05
    step_per_second = params_full.get("NEUTRAL_SPEED", 20000) # Adjust for neutraling speed
    step_per_cycle = step_per_second * interval
    stop()
    current_vals = get_prev_vals() or target_vals
    step_time = time.time()
    while current_vals != target_vals:
        for i in range(params_full["NUM_SERVOS"]):
            if abs(target_vals[i] - current_vals[i]) < step_per_cycle:
                current_vals[i] = target_vals[i]
            elif target_vals[i] > current_vals[i]:
                current_vals[i] += step_per_cycle
            else:
                current_vals[i] -= step_per_cycle
            send_all_setTargetPositionList(current_vals)
        step_time = max(step_time + interval, time.time())
        sleep_time = max(step_time - time.time(), 0)
        if sleep_time > 0:
            time.sleep(sleep_time)
    set_prev_vals(target_vals)
    gh_reset()
    logger.info("Set all motors to neutral position.")
    return


@app.route("/setNeutral", methods=["POST", "GET"])
def setNeutral_endpoint():
    setNeutral()
    return jsonify(result="OK")


def homing(motor_id):
    params_full = get_params_full()
    client, local_id = get_motor_client_and_local_id(motor_id)
    if client is None:
        logger.error("homing: motor_id %d out of range", motor_id)
        return -1
    logger.debug(f"Starting homing for motor {motor_id}")
    enable_servo(client, enable=False, local_id=local_id, broadcast=False)
    client.send_message("/setKval", [local_id, 10, 25, 25, 25])
    time.sleep(0.05)
    reset_latest_homing_status(motor_id)
    client.send_message("/homing", [local_id])
    status = wait_for_homing_complete(
        motor_id, timeout=float(params_full.get("HOMING_TIMEOUT", 21.0))
    )
    Kval_normal = int(params_full.get("KVal_normal", 18))
    Kval_hold = int(params_full.get("KVal_hold", 8))
    client.send_message("/setKval", [local_id, Kval_hold, Kval_normal, Kval_normal, Kval_normal])
    time.sleep(0.05)
    enable_servo(client, enable=True, local_id=local_id, broadcast=False)
    time.sleep(0.05)

    if status == 3:
        vals = get_prev_vals() or [0] * params_full["NUM_SERVOS"]
        vals[motor_id - 1] = 0
        set_prev_vals(vals)
        logger.debug(
            "Homing completed for motor %d, status: %s",
            motor_id,
            "None" if status is None else status,
        )
    else:
        logger.warning(
            "Homing failed for motor %d, status: %s",
            motor_id,
            "None" if status is None else status,
        )
    return status


@app.route("/homing", methods=["POST", "GET"])
def homing_endpoint():
    try:
        motor_id = int(request.form.get("motorID", request.args.get("motorID", 1)))
    except Exception:
        return jsonify(result="NG", error="Invalid or missing motorID"), 400

    status = homing(motor_id)
    

    if status is None:
        osc_speaker.send_message("/Homed", motor_id, -1)
        return jsonify(result="NG", error="No status received"), 504

    if int(status) == 3:
        osc_speaker.send_message("/Homed", motor_id, 1)
        return jsonify(result="OK", motorID=motor_id, homing_status=int(status))

    elif int(status) == -1:
        osc_speaker.send_message("/Homed", motor_id, -1)
        return jsonify(result="NG", error="motorID out of range"), 400

    elif int(status) == 4:
        osc_speaker.send_message("/Homed", motor_id, -1)
        return (
            jsonify(
                result="NG",
                error="board timeout",
                motorID=motor_id,
                homing_status=int(status),
            ),
            500,
        )
    else:
        return jsonify(result="NG", motorID=motor_id, homing_status=int(status))


def home_all():

    def _handle_homing_result(motor_id, status, list_success, list_index):
        try:
            ok = status is not None and int(status) == 3
        except Exception:
            ok = False
        if ok:
            list_success[list_index] = "o"
            return True
        disable_motor(motor_id)
        list_success[list_index] = "x"
        return False

    # Check if stop was requested
    if home_all_stop.is_set():
        logger.info("home_all cancelled before starting")
        return {"result": "CANCELLED", "error": "home_all was cancelled by init"}

    setNeutral()

    n = len(MOTOR_POSITION_MAPPING)
    half = n // 2
    boolSuccess = False
    listSuccess = ["_"] * n

    for i in range(half):
        # Check if stop was requested
        if home_all_stop.is_set():
            logger.info("home_all cancelled during execution")
            return {"result": "CANCELLED", "error": "home_all was cancelled by init"}

        motorID_1 = MOTOR_POSITION_MAPPING[i] + 1
        motorID_2 = MOTOR_POSITION_MAPPING[n - 1 - i] + 1

        if n % 2 == 0 and i == half - 1:
            status_1 = homing(motorID_1)
            boolSuccess = (
                _handle_homing_result(motorID_1, status_1, listSuccess, i)
                or boolSuccess
            )
            setNeutral()

            status_2 = homing(motorID_2)
            boolSuccess = (
                _handle_homing_result(motorID_2, status_2, listSuccess, n - 1 - i)
                or boolSuccess
            )

        else:
            t1 = Thread(target=homing, args=(motorID_1,))
            t2 = Thread(target=homing, args=(motorID_2,))
            t1.start()
            t2.start()
            t1.join()
            t2.join()

            status_1 = get_latest_homing_status(motorID_1)
            status_2 = get_latest_homing_status(motorID_2)

            boolSuccess = (
                _handle_homing_result(motorID_1, status_1, listSuccess, i)
                or boolSuccess
            )
            boolSuccess = (
                _handle_homing_result(motorID_2, status_2, listSuccess, n - 1 - i)
                or boolSuccess
            )

        setNeutral()
        logger.info("homing-all progress: [%s]", " ".join(listSuccess))

    # Check if stop was requested before final motor
    if home_all_stop.is_set():
        logger.info("home_all cancelled during execution")
        return {"result": "CANCELLED", "error": "home_all was cancelled by init"}

    if n % 2 == 1:
        mid_id = MOTOR_POSITION_MAPPING[half] + 1
        status = homing(mid_id)
        boolSuccess = (
            _handle_homing_result(mid_id, status, listSuccess, half) or boolSuccess
        )
        setNeutral()

    if not boolSuccess:
        logger.error("homing-all failed for all motors.")
        osc_speaker.send_message("/Homed", -1)
        return {"result": "NG", "error": "Homing failed for all motors"}

    logger.info("homing-all completed: [%s]", " ".join(listSuccess))
    osc_speaker.send_message("/Homed", 1)
    return {"result": "OK"}


def _home_all_wrapper():
    """Wrapper to execute home_all and store result"""
    global home_all_result
    home_all_result = home_all()


@app.route("/home_all", methods=["POST", "GET"])
def home_all_endpoint():
    global home_all_thread, home_all_stop, home_all_result
    
    # Clear the stop event and result before starting
    home_all_stop.clear()
    home_all_result = None
    
    # Start home_all in a separate thread
    home_all_thread = Thread(target=_home_all_wrapper, daemon=True)
    home_all_thread.start()
    
    # Wait for completion (with timeout to handle edge cases)
    home_all_thread.join(timeout=350)  # 5 minutes max
    
    # Return the result
    result = home_all_result
    if result is None:
        result = {"result": "TIMEOUT", "error": "home_all execution timeout"}
    
    if isinstance(result, tuple):
        body, code = result
        return jsonify(body), code
    return jsonify(result)


@app.route("/set_param", methods=["POST"])
def set_param():
    updated_pid = False
    params_full = get_params_full()
    mode_id = str(params_full.get("MODE", "1"))
    for key in request.form:
        val = request.form[key]
        if key in ("SEND_CLIENTS", "SEND_CLIENT_GH"):
            set_param_full(key, val.lower() == "true")
        elif key in params_full["MODES"][mode_id]:
            try:
                set_param_mode(key, type(params_full["MODES"][mode_id][key])(val))
            except Exception as e:
                return jsonify(result="NG", error=str(e)), 400
        elif key in params_full:
            try:
                set_param_full(key, type(params_full[key])(val))
                if key in ("Kp", "Ki", "Kd"):
                    updated_pid = True
            except Exception as e:
                return jsonify(result="NG", error=str(e)), 400
    if updated_pid:
        set_PID()
    return jsonify(result="OK")


@app.route("/set_mode", methods=["POST"])
def set_mode():
    mode = request.form.get("MODE")
    params_full = get_params_full()
    if mode is not None and mode in params_full["MODES"]:
        set_param_full("MODE", mode)
        return jsonify(result="OK")
    return jsonify(result="NG", error="No mode"), 400


def set_PID():
    params_full = get_params_full()
    kp = float(params_full.get("Kp", 0.06))
    ki = float(params_full.get("Ki", 0.0))
    kd = float(params_full.get("Kd", 0.0))
    clients = get_clients()
    for client in clients:
        client.send_message("/setServoParam", [255, kp, ki, kd])
    logger.debug(f"Set servo PID: Kp={kp}, Ki={ki}, Kd={kd}")


def init(enable=True):
    global home_all_stop, home_all_thread
    
    # Stop any running home_all process
    if home_all_thread is not None and home_all_thread.is_alive():
        logger.info("Stopping running home_all process...")
        home_all_stop.set()
        home_all_thread.join(timeout=2)
        logger.info("home_all process stopped")
    
    clients = get_clients()
    booted_ports = set()

    def on_booted(port, *args):
        booted_ports.add(port)

    if enable:
        register_booted_callback(on_booted)

        expected_ports = 1

        params_full = get_params_full()

        for client in clients:
            client.send_message("/resetDevice", [])
            time.sleep(0.05)
        if not wait_for_booted(booted_ports, expected_ports):
            logger.error(
                f"/booted not received from all devices. Only from: {sorted(booted_ports)}"
            )
        for client in clients:
            client.send_message("/setDestIp", [])
            time.sleep(0.05)
            Kval_normal = int(params_full.get("KVal_normal", 18))
            Kval_hold = int(params_full.get("KVal_hold", 8))
            client.send_message(
                # "/setKval", [255, 60, 119, 119, 119] #SM42BYG011
                # "/setKval", [255, 60, 85, 85, 85] #42HSC1409
                "/setKval",
                # [255, 25, 75, 75, 75],  # SS2421 12V
                # [255, 10, 25, 25, 25],  # SS2421 24V-Low
                # [255, 8, 18, 18, 18],  # SS2421 24V-Low-75%
                [255, Kval_hold, Kval_normal, Kval_normal, Kval_normal],
            )  # (int)motorID (int)holdKVAL (int)runKVAL (int)accKVAL (int)setDecKVAL
            time.sleep(0.05)
            client.send_message("/setGoUntilTimeout", [255, 20000])
            time.sleep(0.05)
            # client.send_message("/setHomingDirection", [255, 0])
            client.send_message("/setHomingSpeed", [255, 100])
            time.sleep(0.05)
            client.send_message(
                "/setPosition", [255, int(params_full.get("STROKE_OFFSET", 50000))]
            )

        set_prev_vals(
            [int(params_full.get("STROKE_OFFSET", 50000))] * params_full["NUM_SERVOS"]
        )
    else:
        stop()

    for client in clients:
        client.send_message("/enableServoMode", [255, enable])
        time.sleep(0.05)
        if not enable:
            client.send_message("/softHiZ", 255)

    set_PID()

    if enable:
        osc_speaker.send_message("/Initialized", 1)
        logger.info("Initialized and enabled servos.")


@app.route("/init", methods=["POST"])
def init_endpoint():

    params_full = get_params_full()
    if params_full.get("SEND_CLIENTS", True) is False:
        logger.debug("SEND_CLIENTS is False, skipping boards init.")
        return jsonify(result="OK", info="SEND_CLIENTS is False, skipping boards init.")
    try:
        start_osc_receiver_thread()
        init()
        return jsonify(result="OK")
    except Exception as e:
        return jsonify(result="NG", error=str(e)), 500


@app.route("/release", methods=["POST"])
def release_endpoint():
    try:
        init(enable=False)
        return jsonify(result="OK")
    except Exception as e:
        return jsonify(result="NG", error=str(e)), 500


@app.route("/step", methods=["POST", "GET"])
def step():
    params_full = get_params_full()
    amp = int(request.form.get("amp", request.args.get("amp", 30000)))
    ch = request.form.get("ch", request.args.get("ch", "all"))
    num_servos = int(params_full["NUM_SERVOS"])
    step_vals = [0] * num_servos
    if ch == "all":
        step_vals = [amp] * num_servos
    else:
        try:
            idx = int(ch)
            if 0 <= idx < num_servos:
                step_vals[idx] = amp
        except Exception:
            return jsonify(result="NG", error="Invalid ch"), 400
    send_all_setTargetPositionList(step_vals)
    return jsonify(result="OK")


@app.route("/reset_pos", methods=["POST"])
def reset_pos():
    try:
        motor_id = int(request.form.get("motorID"))
    except Exception:
        return jsonify(result="NG", error="Invalid or missing motorID"), 400

    client, local_id = get_motor_client_and_local_id(motor_id)
    if client is None:
        return jsonify(result="NG", error="motorID out of range"), 400

    client.send_message("/enableServoMode", [255, 0])
    client.send_message("/resetPos", [local_id])
    client.send_message("/enableServoMode", [255, 1])
    return jsonify(result="OK")


@app.route("/set_target_position", methods=["POST"])
def set_target_position():
    try:
        motor_id = int(request.form.get("motorID"))
        position = int(request.form.get("position"))
    except Exception:
        return jsonify(result="NG", error="Invalid or missing motorID/position"), 400

    client, local_id = get_motor_client_and_local_id(motor_id)
    logger.debug(
        f"Debug: motor_id={motor_id}, local_id={local_id}, position={position}"
    )
    if client is None:
        return jsonify(result="NG", error="motorID out of range"), 400

    client.send_message("/setTargetPosition", [local_id, position])
    logger.debug(f"Set {client._address} motor {local_id} to position {position}")
    return jsonify(result="OK")


@app.route("/get_target_position", methods=["GET"])
def get_target_position():
    try:
        motor_id = int(request.args.get("motorID"))
    except Exception:
        return jsonify(result="NG", error="Invalid or missing motorID"), 400

    client, local_id = get_motor_client_and_local_id(motor_id)
    if client is None:
        return jsonify(result="NG", error="motorID out of range"), 400

    client.send_message("/getPosition", [local_id])
    position = wait_for_latest_position(
        motor_id, timeout=float(get_params_full().get("GETPOS_TIMEOUT", 2.0))
    )

    if position is None:
        return jsonify(result="NG", error="No new position data for motorID"), 404

    return jsonify(result="OK", motorID=motor_id, position=position)


# --- OSC Endpoints ---
def socket_update_param(key, value):
    if key not in LOCKED_KEYS:
        socketio.emit("param_update", {"key": key, "value": value})


# --- SocketIO Events ---
@socketio.on("connect")
def handle_connect():
    """Handle client connection - notify if server just started"""
    logger.debug("Client connected to WebSocket")


@socketio.on("disconnect")
def handle_disconnect():
    """Handle client disconnection"""
    logger.debug("Client disconnected from WebSocket")


def listener_message_callback(address, *args):
    global home_all_thread, home_all_stop, home_all_result
    
    params_full = get_params_full()
    params_mode = get_params_mode()

    candidate = address.lstrip("/")
    if not args:
        logger.debug(f"Received OSC message with no args: {address}")
        if candidate == "Start":
            return start()
        elif candidate == "Stop":
            return stop()
        elif candidate == "Init":
            return init()
        elif candidate == "Home":
            # Start home_all in a separate thread (non-blocking for OSC)
            if home_all_thread is None or not home_all_thread.is_alive():
                home_all_stop.clear()
                home_all_result = None
                home_all_thread = Thread(target=_home_all_wrapper, daemon=True)
                home_all_thread.start()
                logger.info("home_all started via OSC")
            else:
                logger.warning("home_all is already running")
            return
        elif candidate == "Neutral":
            return setNeutral()
        elif candidate == "Release":
            return init(enable=False)
        elif candidate == "Halt":
            return halt()
        elif candidate == "GetAverageSpeed":
            current_speed = get_current_speed()
            abs_avg_speed = sum(abs(s) for s in current_speed) / len(current_speed)
            return osc_speaker.send_message("/AverageSpeed", abs_avg_speed)
        elif candidate == "GetSpeed":
            return osc_speaker.send_message("/Speed", get_current_speed())
        elif candidate == "GetPosition":
            return osc_speaker.send_message("/Position", get_prev_vals())
        elif candidate == "RaiseError":
            return 1 / 0
        logger.warning(f"not matching no-arg command for candidate '/{candidate}'")
        return

    if candidate in params_mode:
        key = candidate
        val = args[0]
        try:
            set_param_mode(key, type(params_mode[key])(val))
        except Exception as e:
            logger.warning(f"Failed to update param_mode '{key}': {e}")
        logger.debug(f"Param '{key}' updated to: {val}")
        socket_update_param(key, val)
    elif candidate in params_full:
        for key in ["MODE", "PORT", "NUM_SERVOS", "RATE_fps", "ALPHA"]:
            if candidate == key:
                val = args[0]
                if key == "MODE":
                    set_repeat_mode()
                try:
                    set_param_full(key, type(params_full[key])(val))
                except Exception as e:
                    logger.warning(f"Failed to update param_full '{key}': {e}")
                logger.debug(f"Param '{key}' updated to: {val}")
                socket_update_param(key, val)
    else:
        logger.warning(f"No matching param key for candidate '{candidate}'")


def handle_bundle(bundle_contents):
    for addr, args in bundle_contents:
        if addr.startswith("/"):
            key = addr.lstrip("/")
            if len(args) > 0:
                value = args[0]
                try:
                    if key in get_params_full():
                        if key == "MODE":
                            set_repeat_mode()
                        set_param_full(key, value)
                    elif key in get_params_mode():
                        set_param_mode(key, value)
                    logger.debug(f"Updated param '{key}' to: {value}")
                    socket_update_param(key, value)
                except Exception as e:
                    logger.warning(f"Failed to update param '{key}': {e}")


def main():

    try:
        print("Starting Ritsudo Server...")
        logger.info("Ritsudo Server is starting.")

        register_message_callback(listener_message_callback)
        register_bundle_callback(handle_bundle)
        start_osc_listener_thread()

        start_osc_receiver_thread()

        web_host = os.getenv("WEB_HOST", "0.0.0.0")
        web_port = int(os.getenv("WEB_PORT", "5001"))

        lan_ip = None
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            lan_ip = s.getsockname()[0]
            s.close()
        except Exception:
            try:
                lan_ip = socket.gethostbyname(socket.gethostname())
            except Exception:
                lan_ip = None
                logger.warning("Could not determine LAN IP address.")

        socketio.run(app, host=web_host, port=web_port, use_reloader=False, debug=False)
        # Disable reloader to avoid double-starting threads

    except Exception:
        logger.info("Ritsudo Server is shutting down.")


# --- MAIN ---
if __name__ == "__main__":
    main()
