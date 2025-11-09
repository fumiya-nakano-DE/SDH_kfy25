import json
from logger_config import logger

# LOCKED_KEYS = ["STROKE_OFFSET", "STROKE_LENGTH"]
LOCKED_KEYS = []

PARAMS_FILE = "params.json"

HOSTS = ["10.0.0.100", "10.0.0.101", "10.0.0.102", "10.0.0.103"]
OSC_RECV_PORTS = [50100, 50101, 50102, 50103]

VALS_PER_HOST = 8
NUM_SERVOS = 31
# MOTOR_POSITION_MAPPING = [i for i in range(NUM_SERVOS - 1, -1, -1)]
MOTOR_POSITION_MAPPING = [i for i in range(NUM_SERVOS)]

DEFAULT_MODES = {
    "101": {
        "NAME": "Simple sin",
        "EASING_DURATION": 5.0,
        "BASE_FREQ": 0.20000000298023224,
        "U_AVERAGE": 1.0,
        "U_WIDTH": 0.0,
        "U_FREQUENTNESS": 0.0,
        "DIRECTION": 1,
        "PHASE_RATE": 0.0,
        "STROKE_LENGTH": 5000,
        "FUNC": "sin",
        "AMP_MODE": "solid",
    },
    "102": {
        "NAME": "Azimuth slide",
        "EASING_DURATION": 1.0,
        "BASE_FREQ": 0.2,
        "U_AVERAGE": 0.5,
        "U_WIDTH": 0,
        "U_FREQUENTNESS": 0.0,
        "DIRECTION": 1,
        "PHASE_RATE": 0.5,
        "STROKE_LENGTH": 1000,
        "FUNC": "azimuth",
        "AMP_MODE": "solid",
    },
    "103": {
        "NAME": "Azimuth slide(Variable)",
        "EASING_DURATION": 1.0,
        "BASE_FREQ": 0.2,
        "U_AVERAGE": 1.0,
        "U_WIDTH": 0,
        "U_FREQUENTNESS": 0.0,
        "DIRECTION": 1,
        "PHASE_RATE": 0.84,
        "PARAM_B": 0.0,
        "STROKE_LENGTH": 13000,
        "FUNC": "azimuth_variable",
        "AMP_MODE": "solid",
    },
    "111": {
        "NAME": "Coned Sin",
        "EASING_DURATION": 1.0,
        "BASE_FREQ": 0.2,
        "U_AVERAGE": 1.0,
        "U_WIDTH": 0,
        "U_FREQUENTNESS": 0.0,
        "DIRECTION": 1,
        "PHASE_RATE": 0.84,
        "STROKE_LENGTH": 18000,
        "FUNC": "sin",
        "AMP_MODE": "cone",
        "AMP_PARAM_A": 0.42,
    },
    "112": {
        "NAME": "Coned Azimuth slide",
        "EASING_DURATION": 1.0,
        "BASE_FREQ": 0.20000000298023224,
        "U_AVERAGE": 1.0,
        "U_WIDTH": 0,
        "U_FREQUENTNESS": 0.0,
        "DIRECTION": 1,
        "PHASE_RATE": 0.0,
        "STROKE_LENGTH": 20000,
        "FUNC": "azimuth",
        "AMP_MODE": "cone",
        "AMP_PARAM_A": 0.25,
    },
    "113": {
        "NAME": "Coned Azimuth slide (Variable)",
        "EASING_DURATION": 1.0,
        "BASE_FREQ": 0.2,
        "U_AVERAGE": 1.0,
        "U_WIDTH": 0,
        "U_FREQUENTNESS": 0.0,
        "DIRECTION": 1,
        "PHASE_RATE": 0.0,
        "PARAM_B": 0.0,
        "STROKE_LENGTH": 3000,
        "FUNC": "azimuth_variable",
        "AMP_MODE": "cone",
        "AMP_PARAM_A": 0.0,
    },
    "121": {
        "NAME": "Sined Sin",
        "EASING_DURATION": 1.0,
        "BASE_FREQ": 0.3,
        "U_AVERAGE": 1.0,
        "U_WIDTH": 0,
        "U_FREQUENTNESS": 0.0,
        "DIRECTION": 1,
        "PHASE_RATE": 0.0,
        "STROKE_LENGTH": 20000,
        "FUNC": "sin",
        "AMP_MODE": "amp_sin",
        "AMP_FREQ": 0.2,
        "AMP_PARAM_A": 0.8,
        "AMP_PARAM_B": 0.05,
    },
    "122": {
        "NAME": "Sined Azimuth slide",
        "EASING_DURATION": 1.0,
        "BASE_FREQ": 0.3,
        "U_AVERAGE": 1.0,
        "U_WIDTH": 0,
        "U_FREQUENTNESS": 0.0,
        "DIRECTION": 1,
        "PHASE_RATE": 0.0,
        "STROKE_LENGTH": 20000,
        "FUNC": "azimuth",
        "AMP_MODE": "amp_sin",
        "AMP_FREQ": -0.71,
        "AMP_PARAM_A": 0.11,
        "AMP_PARAM_B": 0.1,
    },
    "151": {
        "NAME": "Gauss Windowed Sin",
        "EASING_DURATION": 1.0,
        "BASE_FREQ": 0.41,
        "U_AVERAGE": 1.0,
        "U_WIDTH": 0,
        "U_FREQUENTNESS": 0.0,
        "DIRECTION": 1,
        "PHASE_RATE": 0.0,
        "STROKE_LENGTH": 20000,
        "FUNC": "sin",
        "AMP_MODE": "amp_gaussian_window",
        "AMP_FREQ": 0.1,
        "AMP_PARAM_A": 0.97,
    },
    "152": {
        "NAME": "Gauss Windowed Azimuth",
        "EASING_DURATION": 1.0,
        "BASE_FREQ": 0.2,
        "U_AVERAGE": 1.0,
        "U_WIDTH": 0,
        "U_FREQUENTNESS": 0.0,
        "DIRECTION": 1,
        "PHASE_RATE": 0.0,
        "STROKE_LENGTH": 20000,
        "FUNC": "azimuth",
        "AMP_MODE": "amp_gaussian_window",
        "AMP_FREQ": 0.12,
        "AMP_PARAM_A": 0.7,
    },
    "301": {
        "NAME": "Soliton wave",
        "EASING_DURATION": 0.0,
        "BASE_FREQ": 0.2,
        "U_AVERAGE": 0.5,
        "U_WIDTH": 0,
        "U_FREQUENTNESS": 0.0,
        "DIRECTION": -1,
        "PHASE_RATE": 0.45,
        "PARAM_A": 0.11,
        "PARAM_B": 0.27,
        "STROKE_LENGTH": 11200,
        "FUNC": "soliton",
    },
    "401": {
        "NAME": "damped oscillation inflate(sin)",
        "EASING_DURATION": 1.0,
        "BASE_FREQ": 0.3499999940395355,
        "U_AVERAGE": 1.0,
        "U_WIDTH": 0,
        "U_FREQUENTNESS": 0.0,
        "DIRECTION": 1,
        "PHASE_RATE": 0.0,
        "PARAM_A": 0.30000001192092896,
        "STROKE_LENGTH": 30000,
        "FUNC": "sin",
        "AMP_MODE": "damped_oscillation",
        "AMP_FREQ": 0.20000000298023224,
        "AMP_PARAM_A": 0.019999999552965164,
    },
    "402": {
        "NAME": "damped oscillation Azimuth Slide",
        "EASING_DURATION": 1.0,
        "BASE_FREQ": 0.15,
        "U_AVERAGE": 1.0,
        "U_WIDTH": 0,
        "U_FREQUENTNESS": 0.0,
        "DIRECTION": 1,
        "PHASE_RATE": 0.0,
        "PARAM_A": 0.31,
        "STROKE_LENGTH": 30000,
        "FUNC": "azimuth",
        "AMP_MODE": "damped_oscillation",
        "AMP_FREQ": 0.2,
        "AMP_PARAM_A": 0.02,
    },
    "421": {
        "NAME": "damped oscillation locational inflate(sin)",
        "EASING_DURATION": 1.0,
        "BASE_FREQ": 0.5,
        "U_AVERAGE": 1.0,
        "U_WIDTH": 0,
        "U_FREQUENTNESS": 0.0,
        "DIRECTION": 1,
        "PHASE_RATE": 0.0,
        "PARAM_A": 1.0,
        "STROKE_LENGTH": 50000,
        "FUNC": "azimuth",
        "AMP_MODE": "damped_oscillation_locational",
        "AMP_FREQ": 0.5,
        "AMP_PARAM_A": 0.07,
        "AMP_PARAM_B": 0.05,
        "LOCATION_DEGREE": 0.0,
        "LOCATION_HEIGHT": 0.7,
    },
    "422": {
        "NAME": "damped oscillation locational Azimuth Slide",
        "EASING_DURATION": 1.0,
        "BASE_FREQ": 0.5,
        "U_AVERAGE": 1.0,
        "U_WIDTH": 0,
        "U_FREQUENTNESS": 0.0,
        "DIRECTION": 1,
        "PHASE_RATE": 0.0,
        "PARAM_A": 1.0,
        "STROKE_LENGTH": 40000,
        "FUNC": "azimuth",
        "AMP_MODE": "damped_oscillation_locational",
        "AMP_FREQ": 0.3,
        "AMP_PARAM_A": 0.07,
        "AMP_PARAM_B": 0.03,
        "LOCATION_DEGREE": 0.0,
        "LOCATION_HEIGHT": 0.7,
    },
    "431": {
        "NAME": "damped oscillation displace inflate(sin)",
        "EASING_DURATION": 1.0,
        "BASE_FREQ": 1.0,
        "U_AVERAGE": 1.0,
        "U_WIDTH": 0,
        "U_FREQUENTNESS": 0.0,
        "DIRECTION": 1,
        "PHASE_RATE": 0.0,
        "PARAM_A": 0.0,
        "STROKE_LENGTH": 50000,
        "FUNC": "sin",
        "AMP_MODE": "damped_oscillation_displace",
        "AMP_FREQ": 0.0,
        "AMP_PARAM_A": 0.0,
        "LOCATION_DEGREE": 0.0,
        "LOCATION_HEIGHT": 0.699999988079071,
    },
    "432": {
        "NAME": "damped oscillation displace Azimuth Slide",
        "EASING_DURATION": 1.0,
        "BASE_FREQ": 1.0,
        "U_AVERAGE": 1.0,
        "U_WIDTH": 0,
        "U_FREQUENTNESS": 0.0,
        "DIRECTION": 1,
        "PHASE_RATE": 0.0,
        "PARAM_A": 0.15000000596046448,
        "STROKE_LENGTH": 50000,
        "FUNC": "azimuth",
        "AMP_MODE": "damped_oscillation_displace",
        "AMP_FREQ": 1.0,
        "AMP_PARAM_A": 0.05000000074505806,
        "LOCATION_DEGREE": 0.0,
        "LOCATION_HEIGHT": 0.699999988079071,
    },
    "601": {
        "NAME": "locational amped sin",
        "EASING_DURATION": 1.0,
        "BASE_FREQ": 0.53,
        "U_AVERAGE": 0.44,
        "U_WIDTH": 0,
        "U_FREQUENTNESS": 0.0,
        "DIRECTION": 1,
        "PHASE_RATE": 0,
        "PARAM_A": 0.0,
        "STROKE_LENGTH": 20000,
        "FUNC": "sin",
        "AMP_MODE": "amp_locational",
        "AMP_PARAM_A": 0.0,
        "LOCATION_DEGREE": 0.0,
        "LOCATION_HEIGHT": 0.699999988079071,
    },
    "602": {
        "NAME": "locational amped Azimuth Slide",
        "EASING_DURATION": 1.0,
        "BASE_FREQ": 0.47,
        "U_AVERAGE": 1.0,
        "U_WIDTH": 0,
        "U_FREQUENTNESS": 0.0,
        "DIRECTION": 1,
        "PHASE_RATE": 1,
        "PARAM_A": 0.5,
        "STROKE_LENGTH": 20000,
        "FUNC": "azimuth",
        "AMP_MODE": "amp_locational",
        "AMP_PARAM_A": 1.0,
        "LOCATION_DEGREE": 0.0,
        "LOCATION_HEIGHT": 0.7,
    },
    "700": {
        "NAME": "[depricated] random",
        "EASING_DURATION": 1.0,
        "BASE_FREQ": 1.98,
        "STROKE_LENGTH": 20000,
        "FUNC": "random",
    },
    "701": {
        "NAME": "random sin",
        "EASING_DURATION": 1.0,
        "BASE_FREQ": 0.4000000059604645,
        "STROKE_LENGTH": 20000,
        "FUNC": "random_sin",
    },
    "702": {
        "NAME": "random sin freq",
        "EASING_DURATION": 1.0,
        "BASE_FREQ": 0.6,
        "STROKE_LENGTH": 20000,
        "FUNC": "random_sin_freq",
    },
}

DEFAULT_PARAMS = {
    "MODE": "301",
    "MODES": DEFAULT_MODES,
    "HOST": "localhost",
    "PORT": 50000,
    "HOSTS": HOSTS,
    "OSC_RECV_PORTS": OSC_RECV_PORTS,
    "NUM_SERVOS": NUM_SERVOS,
    "RATE_fps": 100,
    "ALPHA": 0.49,
    "Kp": 0.06,
    "Ki": 0.0,
    "Kd": 0.01,
    "STROKE_OFFSET": 62000,
    "SEND_CLIENTS": True,
    "SEND_CLIENT_GH": True,
    "KVal_normal": 54,
    "KVal_hold": 35,
    "LIMIT_ABSOLUTE": 120600,
    "LIMIT_RELATIONAL": 123900,
    "LIMIT_SPEED": 80000,
}

_params = DEFAULT_PARAMS.copy()


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
    return _params.copy()


def get_params_mode() -> dict:
    return _params.get("MODES", {}).get(str(_params.get("MODE", "1")), {}).copy()


def key_locked(key):
    return key in LOCKED_KEYS


def set_param_full(key, value):
    global _params
    if key_locked(key):
        logger.warning("Attempted to set locked param '%s'", key)
        return
    _params[key] = value
    save_params()


def set_param_mode(key, value):
    if key_locked(key):
        logger.warning("Attempted to set locked mode param '%s'", key)
        return
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
        if key_locked(key):
            logger.warning("Attempted to set locked one of params '%s'", key)
            return
        elif key in _params and key != "MODE":
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
