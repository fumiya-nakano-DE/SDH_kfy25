import json

PARAMS_FILE = "params.json"
HOSTS = [f"10.0.0.10{i}" for i in range(0, 4)]
OSC_RECV_PORTS = [range(50100, 50104)]
VALS_PER_HOST = 8
NUM_SERVOS = 32

# Default parameters hard-coded in this file are used
# only when params.json is not existent or incomplete.

DEFAULT_MODES = {}

params = {
    "MODE": "1",
    "MODES": DEFAULT_MODES.copy(),
    "PORT": 50000,
    "NUM_SERVOS": NUM_SERVOS,
    "RATE_fps": 24,
    "ALPHA": 0.2,
    "HOSTS": HOSTS,
    "HOST": "127.0.0.1",
    "Kp": 0.06,
    "Ki": 0.0,
    "Kd": 0.0,
    "STROKE_OFFSET": 0,
    "SEND_CLIENTS": True,
    "SEND_CLIENT_GH": False,
    "OSC_RECV_PORTS": OSC_RECV_PORTS,
}


def save_params():
    with open(PARAMS_FILE, "w", encoding="utf-8") as f:
        json.dump(params, f, ensure_ascii=False, indent=2)


def load_params():
    global params
    try:
        with open(PARAMS_FILE, "r", encoding="utf-8") as f:
            loaded = json.load(f)
            if "MODES" in loaded:
                for k, v in loaded["MODES"].items():
                    params["MODES"][k] = v
                del loaded["MODES"]
            for k, v in loaded.items():
                if k == "HOSTS" and not v:
                    continue
                params[k] = v
            if "HOSTS" not in params:
                params["HOSTS"] = HOSTS
    except Exception:
        pass


load_params()
