import json
from logger_config import logger

PARAMS_FILE = "params.json"
HOSTS = [f"10.0.0.10{i}" for i in range(0, 4)]
OSC_RECV_PORTS = [range(50100, 50104)]
VALS_PER_HOST = 8
NUM_SERVOS = 32

# Default parameters hard-coded in this file are used
# only when _params.json is not existent or incomplete.

DEFAULT_MODES = {}


_params = {
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
        json.dump(_params, f, ensure_ascii=False, indent=2)


def load_params():
    global _params
    try:
        with open(PARAMS_FILE, "r", encoding="utf-8") as f:
            loaded = json.load(f)
            if "MODES" in loaded:
                for k, v in loaded["MODES"].items():
                    _params["MODES"][k] = v
                del loaded["MODES"]
            for k, v in loaded.items():
                if k == "HOSTS" and not v:
                    continue
                _params[k] = v
            if "HOSTS" not in _params:
                _params["HOSTS"] = HOSTS
    except Exception:
        logger.debug("No existing params.json found. Using default parameters.")
        pass


def get_params_full() -> dict:
    return _params


def get_params_mode() -> dict:
    return _params.get("MODES", {}).get(str(_params.get("MODE", "1")), {})


def set_param_full(key, value):
    global _params
    _params[key] = value
    save_params()
    return


def set_param_mode(key, value):
    global _params
    mode_id = str(_params.get("MODE", "1"))
    if "MODES" not in _params:
        _params["MODES"] = {}
    if mode_id not in _params["MODES"]:
        _params["MODES"][mode_id] = {}
    _params["MODES"][mode_id][key] = value
    save_params()
    return


def set_params(**kwargs):
    global _params

    for key, value in kwargs.items():
        if key in _params and key == "MODE":
            logger.debug("Setting param '%s' to: %s", key, value)
            _params[key] = value

    for key, value in kwargs.items():
        if key in _params and key != "MODE":
            logger.debug("Setting param '%s' to: %s", key, value)
            _params[key] = value
        elif key in _params.get("MODES", {}).get(str(_params.get("MODE", "1")), {}):
            mode_id = str(_params.get("MODE", "1"))
            if "MODES" not in _params:
                _params["MODES"] = {}
            if mode_id not in _params["MODES"]:
                _params["MODES"][mode_id] = {}
            _params["MODES"][mode_id][key] = value
    save_params()
    return


load_params()
