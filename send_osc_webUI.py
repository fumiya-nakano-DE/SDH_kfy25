from flask import Flask, render_template, request, redirect, url_for, jsonify
from threading import Thread, Event
import sys, time, socket, os

from osc_params import params, save_params
from osc_sender import (
    send_all_setTargetPositionList,
    get_clients,
    osc_sender,
    filter_vals,
    get_prev_vals,
    set_prev_vals,
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

from pythonosc.udp_client import SimpleUDPClient

app = Flask(__name__, static_folder="static", template_folder="templates")

osc_thread = None
stop_event = Event()


# --- Helpers ---
def get_motor_client_and_local_id(motor_id):
    # motor_id: 1 -> NUM_SERVOS
    from osc_params import VALS_PER_HOST

    hosts = params["HOSTS"]
    host_idx = (motor_id - 1) // VALS_PER_HOST
    if host_idx < 0 or host_idx >= len(hosts):
        return None, None
    client = SimpleUDPClient(hosts[host_idx], int(params["PORT"]))
    local_id = ((motor_id - 1) % VALS_PER_HOST) + 1
    return client, local_id


def enable_servo(client, enable=True, local_id=None, broadcast=True):
    flag = 1 if enable else 0
    if broadcast or local_id is None:
        client.send_message("/enableServoMode", [255, flag])
    else:
        client.send_message("/enableServoMode", [local_id, flag])


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
            print(f">>Boot detected on port(s): {sorted(booted_ports)}, proceeding.")
            return True
        time.sleep(wait_time / steps)
        elapsed += wait_time / steps
        sys.stdout.write(f"\rWaiting for boot... {elapsed:.1f}s ")
    print(
        f"\nERROR: /booted was not received from all {expected_ports} devices. Received from: {sorted(booted_ports)}"
    )
    return False


@app.route("/", methods=["GET", "POST"])
def index():
    global osc_thread, stop_event, params
    running = osc_thread is not None and osc_thread.is_alive()
    mode_id = str(params.get("MODE", "1"))
    mode_params = params["MODES"][mode_id]
    render_params = dict(params)
    render_params.update(mode_params)
    render_params["MODE"] = mode_id
    render_params["MODES"] = params["MODES"]
    if request.method == "POST":
        if not running:
            for key in ["PORT", "NUM_SERVOS", "RATE_fps", "ALPHA"]:
                if key in request.form:
                    params[key] = type(params[key])(request.form.get(key, params[key]))
            save_params()
            stop_event.clear()
            osc_thread = Thread(
                target=osc_sender, args=(params, stop_event), daemon=True
            )
            osc_thread.start()
            running = True
        else:
            stop()
    return render_template("index.html", **render_params, running=running)


def stop():
    global stop_event, osc_thread
    stop_event.set()
    if osc_thread is not None:
        osc_thread.join(timeout=2)
        osc_thread = None


@app.route("/stop", methods=["POST"])
def stop_endpoint():
    stop()
    return redirect(url_for("index"))


@app.route("/setNeutral", methods=["POST", "GET"])
def setNeutral():
    target_vals = [int(params.get("STROKE_OFFSET", 50000))] * params["NUM_SERVOS"]
    alpha = float(params.get("ALPHA", 0.2)) * 0.2
    interval = 1.0 / float(params["RATE_fps"])
    while True:
        filt_vals = filter_vals(target_vals, alpha)
        if get_prev_vals() is not None and filt_vals == get_prev_vals():
            break
        send_all_setTargetPositionList(filt_vals)
        set_prev_vals(filt_vals)
        time.sleep(interval)
    send_all_setTargetPositionList(filt_vals)
    return jsonify(result="OK")


def homing(motor_id):
    client, local_id = get_motor_client_and_local_id(motor_id)
    if client is None:
        return -1

    enable_servo(client, enable=False, broadcast=True)
    reset_latest_homing_status(motor_id)
    client.send_message("/homing", [local_id])

    status = wait_for_homing_complete(
        motor_id, timeout=float(params.get("HOMING_TIMEOUT", 12.0))
    )
    enable_servo(client, enable=True, broadcast=True)

    if status == 3:
        vals = get_prev_vals() or [0] * params["NUM_SERVOS"]
        vals[motor_id - 1] = 0
        set_prev_vals(vals)
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


@app.route("/home_all", methods=["POST", "GET"])
def home_all():
    motorIDs = range(1, params["NUM_SERVOS"] + 1)
    # motorIDs = range(1, 2)

    setNeutral()
    for i in motorIDs:
        time.sleep(1)
        status = homing(i)
        if status is None or int(status) != 3:
            return (
                jsonify(
                    result="NG",
                    motorID=i,
                    homing_status=int(status) if status is not None else None,
                ),
                500,
            )
        setNeutral()

    print("All motors homed successfully.")
    return jsonify(result="OK")


@app.route("/set_param", methods=["POST"])
def set_param():
    global params
    updated_pid = False
    mode_id = str(params.get("MODE", "1"))
    for key in request.form:
        val = request.form[key]
        if key in ("SEND_CLIENTS", "SEND_CLIENT_GH"):
            params[key] = val.lower() == "true"
        elif key in params["MODES"][mode_id]:
            try:
                params["MODES"][mode_id][key] = type(params["MODES"][mode_id][key])(val)
            except Exception as e:
                return jsonify(result="NG", error=str(e)), 400
        elif key in params:
            try:
                params[key] = type(params[key])(val)
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
    global params
    mode = request.form.get("MODE")
    if mode is not None and mode in params["MODES"]:
        params["MODE"] = mode
        save_params()
        return jsonify(result="OK")
    return jsonify(result="NG", error="No mode"), 400


def set_PID():
    kp = float(params.get("Kp", 0.06))
    ki = float(params.get("Ki", 0.0))
    kd = float(params.get("Kd", 0.0))
    clients = get_clients()
    for client in clients:
        client.send_message("/setServoParam", [255, kp, ki, kd])
    print(f"Set servo PID: Kp={kp}, Ki={ki}, Kd={kd}")


def init(enable=True):
    clients = get_clients()
    booted_ports = set()

    def on_booted(port, *args):
        booted_ports.add(port)

    register_booted_callback(on_booted)
    start_osc_receiver_thread()

    expected_ports = 1

    if enable:
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
                #[255, 25, 75, 75, 75],  # SS2421 12V
                [255, 10, 25, 25, 25],  # SS2421 24V-Low
            )  # (int)motorID (int)holdKVAL (int)runKVAL (int)accKVAL (int)setDecKVAL
            # client.send_message("/setGoUntilTimeout", [255, 10000])
            # client.send_message("/setHomingDirection", [255, 0])
            # client.send_message("/setHomingSpeed", [255, 100])
            client.send_message(
                "/setPosition", [255, int(params.get("STROKE_OFFSET", 50000))]
            )

        set_prev_vals([int(params.get("STROKE_OFFSET", 50000))] * params["NUM_SERVOS"])
    for client in clients:
        client.send_message("/enableServoMode", [255, enable])
        if not enable:
            client.send_message("/hardHiZ", 255)
    set_PID()


@app.route("/init", methods=["POST"])
def init_endpoint():
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
def step_func():
    amp = int(request.form.get("amp", request.args.get("amp", 30000)))
    ch = request.form.get("ch", request.args.get("ch", "all"))
    num_servos = int(params["NUM_SERVOS"])
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
    print(f"Debug: motor_id={motor_id}, local_id={local_id}, position={position}")
    if client is None:
        return jsonify(result="NG", error="motorID out of range"), 400

    client.send_message("/setTargetPosition", [local_id, position])
    print(f"Set {client._address} motor {local_id} to position {position}")
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
        motor_id, timeout=float(params.get("GETPOS_TIMEOUT", 2.0))
    )

    if position is None:
        return jsonify(result="NG", error="No new position data for motorID"), 404

    return jsonify(result="OK", motorID=motor_id, position=position)


if __name__ == "__main__":
    print("Starting OSC demo...")

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

    if lan_ip:
        print(f"Web UI URL: http://{lan_ip}:{web_port}")
    else:
        print(f"Web UI listening on http://{web_host}:{web_port}")

    app.run(host=web_host, port=web_port, use_reloader=False)
    # Disable reloader to avoid double-starting threads
