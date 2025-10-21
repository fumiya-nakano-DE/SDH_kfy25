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
    save_params,
    MOTOR_POSITION_MAPPING,
)

import osc_sender
from osc_sender import (
    send_all_setTargetPositionList,
    get_clients,
    osc_sender,
    filter_vals,
    get_prev_vals,
    set_prev_vals,
    gh_reset,
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

from pythonosc.udp_client import SimpleUDPClient

app = Flask(__name__, static_folder="static", template_folder="templates")
socketio = SocketIO(app)

osc_thread = None
stop_event = Event()


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
        print("\rHoming status for motor %d: %s", motor_id, st, end="")
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


# --- HTML Endpoints ---
def start():
    global osc_thread, stop_event
    if osc_thread is None or not osc_thread.is_alive():
        stop_event.clear()
        osc_thread = Thread(target=osc_sender, args=(stop_event,), daemon=True)
        osc_thread.start()
        logger.info("OSC Sender thread started.")
        return True
    return False


def stop():
    global stop_event, osc_thread
    stop_event.set()
    if osc_thread is not None:
        osc_thread.join(timeout=2)
        osc_thread = None
    logger.info("OSC Sender thread stopped.")


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
    alpha = float(params_full.get("ALPHA", 0.2)) * 0.5
    interval = 1.0 / float(params_full["RATE_fps"])
    stop()
    while True and stop_event.is_set():
        filt_vals = filter_vals(target_vals, alpha)
        if get_prev_vals() is not None and filt_vals == get_prev_vals():
            break
        send_all_setTargetPositionList(filt_vals)
        set_prev_vals(filt_vals)
        time.sleep(interval)
    send_all_setTargetPositionList(filt_vals)
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
        return -1

    enable_servo(client, enable=False, broadcast=True)
    reset_latest_homing_status(motor_id)
    client.send_message("/homing", [local_id])

    status = wait_for_homing_complete(
        motor_id, timeout=float(params_full.get("HOMING_TIMEOUT", 12.0))
    )
    enable_servo(client, enable=True, broadcast=True)

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
        return jsonify(result="NG", error="No status received"), 504

    if int(status) == 3:
        return jsonify(result="OK", motorID=motor_id, homing_status=int(status))

    elif int(status) == -1:
        return jsonify(result="NG", error="motorID out of range"), 400

    elif int(status) == 4:
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
    params_full = get_params_full()

    setNeutral()
    for i in range(params_full["NUM_SERVOS"]):
        motorID = MOTOR_POSITION_MAPPING[i] + 1
        status = homing(motorID)
        if status is None or int(status) != 3:
            disable_motor(motorID)
        setNeutral()

    logger.info("homing-all finished.")
    return {"result": "OK"}


@app.route("/home_all", methods=["POST", "GET"])
def home_all_endpoint():
    result = home_all()
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
            params_full[key] = val.lower() == "true"
        elif key in params_full["MODES"][mode_id]:
            try:
                params_full["MODES"][mode_id][key] = type(
                    params_full["MODES"][mode_id][key]
                )(val)
            except Exception as e:
                return jsonify(result="NG", error=str(e)), 400
        elif key in params_full:
            try:
                params_full[key] = type(params_full[key])(val)
                if key in ("Kp", "Ki", "Kd"):
                    updated_pid = True
            except Exception as e:
                return jsonify(result="NG", error=str(e)), 400
    if updated_pid:
        set_PID()
    save_params()
    return jsonify(result="OK")


@app.route("/set_mode", methods=["POST"])
def set_mode():
    mode = request.form.get("MODE")
    params_full = get_params_full()
    if mode is not None and mode in params_full["MODES"]:
        params_full["MODE"] = mode
        save_params()
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
    clients = get_clients()
    booted_ports = set()

    def on_booted(port, *args):
        booted_ports.add(port)

    if enable:
        register_booted_callback(on_booted)
        start_osc_receiver_thread()

        expected_ports = 1

        params_full = get_params_full()

        for client in clients:
            client.send_message("/resetDevice", [])
        if not wait_for_booted(booted_ports, expected_ports):
            raise RuntimeError(
                f"/booted not received from all devices. Only from: {sorted(booted_ports)}"
            )
        for client in clients:
            client.send_message("/setDestIp", [])
            time.sleep(0.1)
            client.send_message(
                # "/setKval", [255, 60, 119, 119, 119] #SM42BYG011
                # "/setKval", [255, 60, 85, 85, 85] #42HSC1409
                "/setKval",
                # [255, 25, 75, 75, 75],  # SS2421 12V
                [255, 10, 25, 25, 25],  # SS2421 24V-Low
            )  # (int)motorID (int)holdKVAL (int)runKVAL (int)accKVAL (int)setDecKVAL
            # client.send_message("/setGoUntilTimeout", [255, 10000])
            # client.send_message("/setHomingDirection", [255, 0])
            # client.send_message("/setHomingSpeed", [255, 100])
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
        if not enable:
            client.send_message("/softHiZ", 255)
    set_PID()


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
def listener_message_callback(address, *args):
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
            return home_all()
        elif candidate == "Neutral":
            return setNeutral()
        elif candidate == "Release":
            return init(enable=False)
        elif candidate == "Halt":
            return halt()
        elif candidate == "RaiseError":
            return 1 / 0
        logger.warning(f"not matching no-arg command for candidate '/{candidate}'")
        return

    if candidate in params_mode:
        key = candidate
        val = args[0]
        try:
            set_param_mode(key, type(params_mode[key])(val))
        except Exception:
            params_mode[key] = val
        try:
            save_params()
        except Exception:
            pass
        logger.debug(f"Param '{key}' updated to: {val}")
        socketio.emit("param_update", {"key": key, "value": val})
    elif candidate in params_full:
        for key in ["MODE", "PORT", "NUM_SERVOS", "RATE_fps", "ALPHA"]:
            if candidate == key:
                val = args[0]
                try:
                    set_param_full(key, type(params_full[key])(val))
                except Exception:
                    params_full[key] = val
                try:
                    save_params()
                except Exception:
                    pass
                logger.debug(f"Param '{key}' updated to: {val}")
                socketio.emit("param_update", {"key": key, "value": val})
    else:
        logger.warning(f"No matching param key for candidate '{candidate}'")


def handle_bundle(bundle_contents):
    params_to_update = {}
    for addr, args in bundle_contents:
        if addr.startswith("/"):
            key = addr.lstrip("/")
            if len(args) > 0:
                params_to_update[key] = args[0]
    logger.debug(f"Updating params from bundle: {params_to_update}")
    set_params(**params_to_update)
    for key in params_to_update:
        socketio.emit("param_update", {"key": key, "value": params_to_update[key]})


# --- MAIN ---
if __name__ == "__main__":
    try:
        print("Starting Ritsudo Server...")
        logger.info("Ritsudo Server is starting.")

        register_message_callback(listener_message_callback)
        register_bundle_callback(handle_bundle)
        start_osc_listener_thread()

        web_host = os.getenv("WEB_HOST", "0.0.0.0")
        web_port = int(os.getenv("WEB_PORT", "5000"))

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
