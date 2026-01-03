import math
import numpy as np
from osc_params import get_params_full, get_params_mode
from logger_config import logger

STROKE_LENGTH_LIMIT_HARDCODED = 50000


# -------------------------
# Amplitude modulation
# -------------------------
def solid(t, num_servos):
    return np.ones(num_servos)


def cone(t, num_servos):
    param_a = float(get_params_mode().get("AMP_PARAM_A", 0.25)) * 2 - 1
    idx = np.arange(num_servos, dtype=float)
    t_norm = idx / (num_servos - 1)
    if param_a >= 0:
        curve = np.power(t_norm, 4 * param_a)
    else:
        curve = np.power(1 - t_norm, 4 * abs(-param_a))
    return curve


def amp_sin(t, num_servos):
    freq = get_params_mode().get("AMP_FREQ", 0.2)
    amp_amplitude = float(get_params_mode().get("AMP_PARAM_A", 0.5))
    phase_shift = (
        (2 * math.pi)
        / num_servos
        / max(get_params_mode().get("AMP_PARAM_B", 0.2), 1e-6)
        / 2
    )
    return np.array(
        [
            (1 - amp_amplitude)
            + math.sin(2 * math.pi * freq * t + i * phase_shift) * amp_amplitude
            for i in range(num_servos)
        ],
        dtype=float,
    )


def amplitude_modulation(t, num_servos):
    amp_func = globals().get(str(get_params_mode().get("AMP_MODE")), solid)
    return amp_func(t, num_servos)


def amp_gaussian_window(t, num_servos):
    raw_amp_freq = get_params_mode().get("AMP_FREQ", 0.1)
    amp_freq = abs(raw_amp_freq) / 5

    cycle = math.floor(t / (1 / max(raw_amp_freq, 1e-6)))
    t = t - cycle / max(raw_amp_freq, 1e-6)

    amp_param_a = float(get_params_mode().get("AMP_PARAM_A", 0.1))

    duty = duty_from_param_a(1 / amp_freq * amp_param_a)

    center = duty * 0.65
    sigma = max(duty / 4.0, 1e-6)

    a = math.exp(-((t - center) ** 2) / (2.0 * sigma**2))

    return np.array([a] * num_servos, dtype=float)


def amp_emerging(t, num_servos):
    damping = float(get_params_mode().get("AMP_PARAM_A", 0.1))
    rate = max(damping, 1e-6)
    vals = [1.0 - math.exp(-rate * t)] * num_servos
    return np.array(vals, dtype=float)


def amp_locational(t, num_servos):
    amp_param_a = float(get_params_mode().get("AMP_PARAM_A", 0.1))
    # amp_param_b = float(get_params_mode().get("AMP_PARAM_B", 0.1))
    distances, dot_products = location_distance(0, num_servos)
    # rate = max(distances, [1e-6] * num_servos)
    # exponential decay: close to 1 at distance=0, ->0 as distance grows
    scale = max(amp_param_a, 1e-6)
    vals = np.exp(-scale * distances)
    return np.array(vals, dtype=float)


# -------------------------
# Helpers
# -------------------------
def base_freq():
    return float(get_params_mode().get("BASE_FREQ", 1.0))


def cycle_from_params():
    return 1.0 / max(base_freq(), 1e-6)


def duty_from_param_a(cycle):
    return float(get_params_mode().get("PARAM_A", 0.15)) * cycle


def rate_from_param_b(duty):
    return duty / 100 / max(float(get_params_mode().get("PARAM_B", 1e-6)), 1e-6)


# -------------------------
# Phase
# -------------------------
def phase(i, num_servos):
    return (
        (i / num_servos)
        * math.pi
        * float(get_params_mode().get("PHASE_RATE", 0.0))
        * -1.0
    )


def azimuth_phase(i):
    return (i % 3) / 3 * math.pi * 2


def azimuth_phase_variable(i, f):
    if f < 0:
        f = 0
    elif f > 1:
        f = 1
    return (i % 3) / 3 * f * math.pi * 2


# -------------------------
# Location-based effects
# -------------------------
def location_distance(i, num_servos):
    r = 1
    p = 1
    num_turns = num_servos / 3.0
    coords = []
    for idx in range(num_servos):
        theta = (idx / num_servos) * num_turns * 2 * math.pi
        z = (idx / num_servos) * num_turns * p
        x = r * math.cos(theta)
        y = r * math.sin(theta)
        coords.append([x, y, z])
    degree = get_params_mode().get("LOCATION_DEGREE", 0)
    height = get_params_mode().get("LOCATION_HEIGHT", 0.7)
    origin = np.array(
        [
            math.cos(degree * math.pi * 2),
            math.sin(degree * math.pi * 2),
            height * 10,
        ]
    )
    distances = [np.linalg.norm(np.array(coord) - origin) for coord in coords]
    origin_vec = origin / np.linalg.norm(origin)
    dot_products = [
        np.dot(np.array(coord) / np.linalg.norm(coord), origin_vec) for coord in coords
    ]
    return np.array(distances, dtype=float), np.array(dot_products, dtype=float)


# -------------------------
# Window functions
# -------------------------
def window_gaussian(t, duty):
    center = duty / 2.0
    sigma = max(duty / 4.0, 1e-6)
    return math.exp(-((t - center) ** 2) / (2.0 * sigma**2))


# -------------------------
# Public mode functions
# -------------------------
def sin(t, num_servos):
    freq = base_freq()
    vals = [
        math.sin(2 * math.pi * freq * t + phase(i, num_servos))
        for i in range(num_servos)
    ]
    return np.array(vals, dtype=float)


def azimuth(t, num_servos):
    def azimuth_core(i, num_servos, t, rate):
        return math.sin(
            2 * math.pi * rate * t + azimuth_phase(i) + phase(i, num_servos)
        )

    cycle = cycle_from_params()
    t_mod = t % cycle
    rate = base_freq()
    vals = [azimuth_core(i, num_servos, t_mod, rate) for i in range(num_servos)]
    return np.array(vals, dtype=float)


def azimuth_variable(t, num_servos):
    def azimuth_core(i, num_servos, t, rate):
        f = float(get_params_mode().get("PARAM_B", 0.0))
        return math.sin(
            2 * math.pi * rate * t + azimuth_phase_variable(i, f) + phase(i, num_servos)
        )

    cycle = cycle_from_params()
    t_mod = t % cycle
    rate = base_freq()
    vals = [azimuth_core(i, num_servos, t_mod, rate) for i in range(num_servos)]
    return np.array(vals, dtype=float)


def soliton(t, num_servos):
    period = cycle_from_params()
    phase_shift = float(get_params_mode().get("PHASE_RATE", 0.0))
    t = (t + phase_shift * period) % period
    width = max(float(get_params_mode().get("PARAM_A", 0.15)), 1e-6)  # 0..1 of cycle
    speed = float(get_params_mode().get("PARAM_B", 1.0))  # 伝播速度スケール
    vals = []
    for i in range(num_servos):
        phase_pos = ((t / period) - (i / num_servos) * speed) % 1.0
        sol = window_gaussian(phase_pos * period, width * period)
        vals.append(sol)
    return np.array(vals, dtype=float)


def damped_oscillation(t, num_servos):
    amp_freq = get_params_mode().get("AMP_FREQ", 0.1)
    damping = max(float(get_params_mode().get("AMP_PARAM_A", 0.1)), 1e-6) * 10
    vals = [
        math.exp(-damping * t)
        * math.sin(2 * math.pi * amp_freq * t + phase(i, num_servos))
        for i in range(num_servos)
    ]
    return np.array(vals, dtype=float)


def damped_oscillation_locational(t, num_servos):
    amp_freq = get_params_mode().get("AMP_FREQ", 0.1)
    damping = max(float(get_params_mode().get("AMP_PARAM_A", 0.1)), 1e-6) * 10
    convey = float(get_params_mode().get("AMP_PARAM_B", 0.1)) * 10
    vals = [0] * num_servos
    distances, dot_products = location_distance(0, num_servos)
    for i in range(num_servos):
        t_i = t - distances[i] / (2 * math.pi * amp_freq) * convey
        if t_i < 0:
            vals[i] = 0
            continue
        vals[i] = math.exp(-damping * t_i) * math.sin(2 * math.pi * amp_freq * t_i)
    return np.array(vals, dtype=float)


def damped_oscillation_displace(t, num_servos):
    amp_freq = get_params_mode().get("AMP_FREQ", 0.1)
    damping = float(get_params_mode().get("PARAM_A", 0.1)) * 10
    convey = float(get_params_mode().get("AMP_PARAM_A", 0.1)) * 10
    vals = [0] * num_servos
    distances, dot_products = location_distance(0, num_servos)
    for i in range(num_servos):
        t_i = t - distances[i] / (2 * math.pi * amp_freq) * convey
        if t_i < 0:
            vals[i] = 0
            continue
        vals[i] = (
            math.exp(-damping * t_i)
            * math.sin(2 * math.pi * amp_freq * t_i)
            * dot_products[i]
        )
    return np.array(vals, dtype=float)


def random(t, num_servos):
    freq = base_freq()
    vals = [0] * num_servos
    for i in range(num_servos):
        np.random.seed(int(t * freq) + i)  # Seed with time for reproducibility
        vals[i] = np.random.uniform(-1, 1)
    return vals


def random_sin(t, num_servos):
    vals = [0] * num_servos
    for i in range(num_servos):
        np.random.seed(i)  # Seed with servo index for consistency
        phase_shift = np.random.uniform(0, 2 * math.pi)
        freq = base_freq()
        vals[i] = math.sin(2 * math.pi * freq * t + phase_shift)
    return vals


def random_sin_freq(t, num_servos):
    vals = [0] * num_servos
    for i in range(num_servos):
        np.random.seed(i)  # Seed with servo index for consistency
        phase_shift = np.random.uniform(0, 2 * math.pi)
        freq = np.random.uniform(0.1, base_freq()) ** 2
        vals[i] = math.sin(2 * math.pi * freq * t + phase_shift)
    return vals


# -------------------------
# Tone-curve spline LUT
# -------------------------
LUT_X = np.linspace(-1.0, 1.0, 7)


def LUT(vals):
    """Apply tone-curve LUT using a shape-preserving cubic Hermite spline.

    Compared to Catmull-Rom, this reduces wiggles/overshoot near the
    endpoints while staying smooth through the 7 control points.
    """

    n = len(LUT_X)
    if n < 2:
        return vals

    params_full = get_params_full()
    lut_y_list = []
    for i in range(n):
        key = f"LUT_Y{i}"
        if key in params_full:
            lut_y_list.append(float(params_full[key]))
        else:
            lut_y_list.append(float(LUT_X[i]))

    lut_y = np.array(lut_y_list, dtype=float)

    # Pre-compute segment widths and secant slopes
    h = np.diff(LUT_X)
    if np.any(h == 0):
        return vals
    delta = np.diff(lut_y) / h

    # Shape-preserving slope estimates (monotone cubic style)
    m = np.empty(n, dtype=float)
    m[0] = delta[0]
    m[-1] = delta[-1]
    for k in range(1, n - 1):
        if delta[k - 1] * delta[k] <= 0:
            m[k] = 0.0
        else:
            m[k] = 0.5 * (delta[k - 1] + delta[k])

    x_min = LUT_X[0]
    x_max = LUT_X[-1]

    for i in range(len(vals)):
        u = float(vals[i])

        # Choose segment index k so LUT_X[k] <= u <= LUT_X[k+1],
        # with clamped extrapolation outside [-1, 1].
        if u <= x_min:
            k = 0
        elif u >= x_max:
            k = n - 2
        else:
            # Uniform grid, so we can locate k by index.
            step = (x_max - x_min) / (n - 1)
            s = (u - x_min) / step
            k = int(math.floor(s))
            k = max(0, min(n - 2, k))

        x_k = LUT_X[k]
        h_k = h[k]
        if h_k == 0:
            continue
        t = (u - x_k) / h_k

        t2 = t * t
        t3 = t2 * t

        h00 = 2 * t3 - 3 * t2 + 1
        h10 = t3 - 2 * t2 + t
        h01 = -2 * t3 + 3 * t2
        h11 = t3 - t2

        y_k = lut_y[k]
        y_k1 = lut_y[k + 1]
        m_k = m[k]
        m_k1 = m[k + 1]

        vals[i] = h00 * y_k + h10 * h_k * m_k + h01 * y_k1 + h11 * h_k * m_k1

    return vals


# -------------------------
# Frame builder
# -------------------------
def make_frame(t, num_servos):
    params_mode = get_params_mode()
    func_name = params_mode.get("FUNC", "sin")
    func = globals().get(func_name, sin)
    direction = float(params_mode.get("DIRECTION", 1.0))
    offset = float(get_params_full().get("STROKE_OFFSET", 0.0))

    raw = func(t * direction, num_servos)
    amp = amplitude_modulation(t, num_servos)

    norm_vals = np.array(raw) * np.array(amp)
    norm_vals = LUT(norm_vals)

    stroke_length = float(get_params_mode().get("STROKE_LENGTH", 20000))
    stroke_length_limit = float(
        get_params_mode().get(
            "STROKE_LENGTH_LIMIT_SPECIFIC",
            get_params_full().get("STROKE_LENGTH_LIMIT", STROKE_LENGTH_LIMIT_HARDCODED),
        )
    )
    stroke_length = max(min(stroke_length, stroke_length_limit), 0)

    return norm_vals * stroke_length + offset
