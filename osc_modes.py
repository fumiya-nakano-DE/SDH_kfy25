import math
import numpy as np
from osc_params import params


# -------------------------
# Amplitude modulation
# -------------------------
def solid(t, num_servos, mode_params):
    return np.ones(num_servos)


def cone(t, num_servos, mode_params):
    idx = np.arange(num_servos, dtype=float)
    return (num_servos - idx) / num_servos


def amp_sin(t, num_servos, mode_params):
    freq = mode_params.get("AMP_FREQ", 0.2)
    phase_shift = (
        (2 * math.pi) / num_servos / max(mode_params.get("AMP_PARAM_A", 0.2), 1e-6) / 2
    )
    return np.array(
        [
            0.5 * (1 + math.sin(2 * math.pi * freq * t + i * phase_shift))
            for i in range(num_servos)
        ],
        dtype=float,
    )


def amplitude_modulation(t, num_servos, mode_params):
    amp_func = globals().get(str(mode_params.get("AMP_MODE")), solid)
    return amp_func(t, num_servos, mode_params) * float(
        mode_params.get("STROKE_LENGTH", 50000)
    )


# -------------------------
# Helpers
# -------------------------
def base_freq(mode_params):
    return float(mode_params.get("BASE_FREQ", 1.0))


def cycle_from_params(mode_params):
    return 1.0 / max(base_freq(mode_params), 1e-6)


def duty_from_param_a(mode_params, cycle):
    return float(mode_params.get("PARAM_A", 0.15)) * cycle


def rate_from_param_b(mode_params, duty):
    return duty / max(float(mode_params.get("PARAM_B", 1e-6)), 1e-6)


# -------------------------
# Phase
# -------------------------
def phase(i, num_servos, mode_params):
    return (i / num_servos) * math.pi * float(mode_params.get("PHASE_RATE", 0.0)) * -1.0


def azimuth_phase(i):
    return (i % 3) / 3 * math.pi * 2


def locational_phase(i, num_servos, mode_params):
    r = float(mode_params.get("HELIX_RADIUS", 1.0))
    p = float(mode_params.get("HELIX_PITCH", 1.0))
    num_turns = num_servos / 3.0
    coords = []
    for idx in range(num_servos):
        theta = (idx / num_servos) * num_turns * 2 * math.pi
        z = (idx / num_servos) * num_turns * p
        x = r * math.cos(theta)
        y = r * math.sin(theta)
        coords.append([x, y, z])
    origin = np.array([1.1, 0.0, 7.0])
    distances = [np.linalg.norm(np.array(coord) - origin) for coord in coords]
    origin_vec = origin / np.linalg.norm(origin)
    dot_products = [
        np.dot(np.array(coord) / np.linalg.norm(coord), origin_vec) for coord in coords
    ]
    return np.array(distances, dtype=float), np.array(dot_products, dtype=float)


# -------------------------
# Window functions
# -------------------------
def window_gaussian(t_rel, duty):
    center = duty / 2.0
    sigma = max(duty / 4.0, 1e-6)
    return math.exp(-((t_rel - center) ** 2) / (2.0 * sigma**2))


def window_rectangular(t_rel, duty):
    return 1.0 if 0.0 <= t_rel <= duty else 0.0


# -------------------------
# Core wave
# -------------------------
def azimuth_core(i, num_servos, mode_params, t, rate):
    return math.sin(
        2 * math.pi * rate * t + azimuth_phase(i) + phase(i, num_servos, mode_params)
    )


def azimuth_base(t, num_servos, mode_params, window_func=None):
    cycle = cycle_from_params(mode_params)
    t_mod = t % cycle
    window = 1.0
    if window_func is not None:
        duty = duty_from_param_a(mode_params, cycle)
        window = window_func(t_mod, duty) if t_mod <= duty else 0.0
        rate = rate_from_param_b(mode_params, duty)
    else:
        rate = base_freq(mode_params)

    vals = [
        azimuth_core(i, num_servos, mode_params, t_mod, rate) * window
        for i in range(num_servos)
    ]
    return np.array(vals, dtype=float)


# -------------------------
# Public mode functions
# -------------------------
def sin(t, num_servos, mode_params):
    freq = base_freq(mode_params)
    vals = [
        math.sin(2 * math.pi * freq * t + phase(i, num_servos, mode_params))
        for i in range(num_servos)
    ]
    return np.array(vals, dtype=float)


def azimuth(t, num_servos, mode_params):
    return azimuth_base(t, num_servos, mode_params, window_func=None)


def azimuth_window_gaussian(t, num_servos, mode_params):
    return azimuth_base(t, num_servos, mode_params, window_gaussian)


def azimuth_window_rectangular(t, num_servos, mode_params):
    return azimuth_base(t, num_servos, mode_params, window_rectangular)


def soliton(t, num_servos, mode_params):
    period = cycle_from_params(mode_params)
    width = max(float(mode_params.get("PARAM_A", 0.15)), 1e-6)  # 0..1 of cycle
    speed = float(mode_params.get("PARAM_B", 1.0))  # 伝播速度スケール
    vals = []
    for i in range(num_servos):
        phase_pos = ((t / period) - (i / num_servos) * speed) % 1.0
        sol = window_gaussian(phase_pos * period, width * period)
        vals.append(sol)
    return np.array(vals, dtype=float)


def azimuth_sine(t, num_servos, mode_params):
    return azimuth_base(t, num_servos, mode_params) * amp_sin(
        t, num_servos, mode_params
    )


def damped_oscillation(t, num_servos, mode_params):
    freq = base_freq(mode_params)
    damping = float(mode_params.get("PARAM_A", 0.1)) * 10  # 減衰係数
    vals = [
        math.exp(-damping * t)
        * math.sin(2 * math.pi * freq * t + phase(i, num_servos, mode_params))
        for i in range(num_servos)
    ]
    return np.array(vals, dtype=float)


def damped_oscillation_locational(t, num_servos, mode_params):
    freq = base_freq(mode_params)
    damping = float(mode_params.get("PARAM_A", 0.1)) * 10
    convey = float(mode_params.get("AMP_PARAM_A", 0.1)) * 10
    vals = [0] * num_servos
    distances, dot_products = locational_phase(0, num_servos, mode_params)
    for i in range(num_servos):
        t_i = t - distances[i] / (2 * math.pi * freq) * convey
        if t_i < 0:
            vals[i] = 0
            continue
        vals[i] = math.exp(-damping * t_i) * math.sin(2 * math.pi * freq * t_i)
    return np.array(vals, dtype=float)


def damped_oscillation_displace(t, num_servos, mode_params):
    freq = base_freq(mode_params)
    damping = float(mode_params.get("PARAM_A", 0.1)) * 10
    convey = float(mode_params.get("AMP_PARAM_A", 0.1)) * 10
    vals = [0] * num_servos
    distances, dot_products = locational_phase(0, num_servos, mode_params)
    for i in range(num_servos):
        t_i = t - distances[i] / (2 * math.pi * freq) * convey
        if t_i < 0:
            vals[i] = 0
            continue
        vals[i] = (
            math.exp(-damping * t_i)
            * math.sin(2 * math.pi * freq * t_i)
            * dot_products[i]
        )
    return np.array(vals, dtype=float)


# -------------------------
# Frame builder
# -------------------------
def make_frame(t, num_servos, params):
    mode_id = str(params.get("MODE", "1"))
    mode_params = params["MODES"][mode_id]
    func_name = mode_params.get("FUNC", "sin")
    func = globals().get(func_name, sin)
    direction = float(mode_params.get("DIRECTION", 1.0))
    offset = float(params.get("STROKE_OFFSET", 0.0))

    raw = func(t * direction, num_servos, mode_params)
    amp = amplitude_modulation(t, num_servos, mode_params)
    return raw * amp + offset
