from pythonosc.udp_client import SimpleUDPClient
from osc_params import (
    VALS_PER_HOST,
    NUM_SERVOS,
    MOTOR_POSITION_MAPPING,
    get_params_full,
    set_param_full,
    get_params_mode,
)
from osc_modes import make_frame
import sys, time, math, random
from logger_config import logger

prev_vals = None


def get_prev_vals():
    global prev_vals
    if prev_vals is None:
        return [get_params_full().get("STROKE_OFFSET", 50000)] * NUM_SERVOS
    return prev_vals


def set_prev_vals(vals):
    global prev_vals
    prev_vals = vals.copy() if vals is not None else None


def get_clients():
    return [
        SimpleUDPClient(host, int(get_params_full()["PORT"]))
        for host in get_params_full()["HOSTS"]
    ]


def get_client_gh():
    return SimpleUDPClient(get_params_full()["HOST"], int(get_params_full()["PORT"]))


def send_all_setTargetPositionList(vals):

    set_prev_vals(vals)

    mapped_vals = [0] * NUM_SERVOS
    motor_position_mapping = MOTOR_POSITION_MAPPING
    for i in range(NUM_SERVOS):
        mapped_vals[i] = (
            vals[i] if motor_position_mapping == {} else vals[motor_position_mapping[i]]
        )

    sent_boards = False
    sent_gh = False
    if get_params_full().get("SEND_CLIENTS", True):
        clients = get_clients()
        for i, client in enumerate(clients):

            vals_part = mapped_vals[i * VALS_PER_HOST : (i + 1) * VALS_PER_HOST]

            try:
                client.send_message("/setTargetPositionList", vals_part)
                sent_boards = True
            except Exception as e:
                logger.error(f"send error to {get_params_full()['HOSTS'][i]}: {e}")
    if get_params_full().get("SEND_CLIENT_GH", False):
        client_gh = get_client_gh()
        try:
            client_gh.send_message("/setTargetPositionList", mapped_vals)
            sent_gh = True
        except Exception as e:
            logger.error("send error to {}: {}".format(get_params_full()["HOST"], e))

    return sent_boards, sent_gh


def gh_reset():
    if get_params_full().get("SEND_CLIENT_GH", False):
        client_gh = get_client_gh()
        try:
            client_gh.send_message(
                "/reset",
                get_params_full()["NUM_SERVOS"]
                * [get_params_full().get("STROKE_OFFSET", 50000)],
            )
        except Exception as e:
            logger.error("send error to {}: {}".format(get_params_full()["HOST"], e))


def filter_vals(raw_vals, alpha):
    vals = raw_vals.copy()

    prev = get_prev_vals()
    if prev is None:
        vals = raw_vals
    else:
        vals = [int(p + alpha * (c - p)) for p, c in zip(prev, raw_vals)]

    limited_absolute = False
    limit_absolute = get_params_full().get("LIMIT_ABSOLUTE")
    for i in range(len(vals)):
        if vals[i] > limit_absolute:
            vals[i] = limit_absolute
            limited_absolute = True
        elif vals[i] < 0:
            vals[i] = 0
            limited_absolute = True

    limited_relational = False
    limit_relational = get_params_full().get("LIMIT_RELATIONAL")
    valsLPF = vals.copy()

    def solve_relational_limit(a, c):
        return 0.5 * (math.sqrt(4 * c * c - 3 * a * a) - a)

    for i in range(1, len(vals) - 1):
        b_1 = solve_relational_limit(valsLPF[i - 1], limit_relational)
        b_2 = solve_relational_limit(valsLPF[i + 1], limit_relational)
        if b_1 - valsLPF[i] < 0 or b_2 - valsLPF[i] < 0:
            vals[i] = 0.5 * min(b_1 + valsLPF[i], b_2 + valsLPF[i])
            limited_relational = True

    if limited_relational or limited_absolute:
        logger.warning(
            "Output limited: %s%s",
            "ABS " if limited_absolute else "",
            "REL" if limited_relational else "",
        )

    return vals


def osc_sender(stop_event):

    # u[f+1] = u[f] + dudt * dt
    u = 0.0
    u_t_rate = 1.0
    u_t_rate_target = 1.0
    u_t_rate_accel = 0.01  # absolute
    u_t_keep = 0

    dt = 1.0 / float(get_params_full()["RATE_fps"])
    t_schedule = time.time() + dt

    frame = 0
    last_msg_len = 0
    mode = get_params_full().get("MODE")

    easing_from = []
    easing_to = []

    starting_motion = True

    while not stop_event.is_set():
        if mode != get_params_full().get("MODE") or starting_motion:
            starting_motion = False
            mode = get_params_full().get("MODE")
            set_param_full("MODE", mode)
            print(f"=== MODE: {mode} ===")
            logger.info("Switched to mode %s", mode)
            easing_duration = get_params_mode().get("EASING_DURATION", 1.0)
            if easing_duration > 0.0:
                u = -easing_duration
                easing_from = get_prev_vals()
                easing_to = make_frame(0, NUM_SERVOS)
            else:
                u = 0.0
            u_t_keep = 0
            frame = 0

        u_t_keep += dt

        raw_vals = get_prev_vals()
        if u >= 0:
            U_FREQUENTNESS = get_params_mode().get("U_FREQUENTNESS", 0.1)
            U_WIDTH = get_params_mode().get("U_WIDTH", 1.0)
            if U_FREQUENTNESS <= 0.0 or U_WIDTH <= 0.0:
                u_t_rate_target = get_params_mode().get("U_AVERAGE", 1.0)
            elif u_t_keep >= (1.0 / U_FREQUENTNESS):
                u_t_rate_target = random.uniform(
                    get_params_mode().get("U_AVERAGE", 1.0)
                    - get_params_mode().get("U_WIDTH", 1.0) / 2,
                    get_params_mode().get("U_AVERAGE", 1.0)
                    + get_params_mode().get("U_WIDTH", 1.0) / 2,
                )
                u_t_keep = 0.0
                logger.debug("New u_t_rate_target: {:.3f}".format(u_t_rate_target))

            if u_t_rate - u_t_rate_target > u_t_rate_accel:
                u_t_rate -= u_t_rate_accel
            elif u_t_rate - u_t_rate_target < -u_t_rate_accel:
                u_t_rate += u_t_rate_accel
            else:
                u_t_rate = u_t_rate_target
            u_t_rate = max(u_t_rate, 0.0)

            u += u_t_rate * dt

            raw_vals = make_frame(u, NUM_SERVOS)
        else:
            for i in range(NUM_SERVOS):
                raw_vals[i] = easing_from[i] * (
                    1 - (u_t_keep / easing_duration)
                ) + easing_to[i] * (u_t_keep / easing_duration)
            u += dt

        alpha = float(get_params_full().get("ALPHA", 0.2))
        prev = get_prev_vals()
        if prev is None:
            set_prev_vals(raw_vals)
        filt_vals = filter_vals(raw_vals, alpha)
        set_prev_vals(filt_vals)
        sent_boards, sent_gh = send_all_setTargetPositionList(filt_vals)
        msg = (
            f"\rOSC[{frame}] "
            f"{'[boards]' if sent_boards else '[     ]'}"
            f"{'[gh]' if sent_gh else '[  ]'} "
            f"1st8: {filt_vals[:8]}  min:{min(filt_vals):6.1f}  max:{max(filt_vals):6.1f}"
        )
        pad = " " * max(0, last_msg_len - len(msg) + 1)
        print(msg + pad, end="", flush=True)
        last_msg_len = len(msg)

        frame += 1

        t_schedule += dt
        sleep_time = t_schedule - time.time()
        if sleep_time > 0:
            time.sleep(sleep_time)
