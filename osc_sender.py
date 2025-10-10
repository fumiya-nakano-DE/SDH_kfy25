from pythonosc.udp_client import SimpleUDPClient
from osc_params import params, VALS_PER_HOST, NUM_SERVOS
from osc_modes import make_frame
import sys, time

prev_vals = None


def get_prev_vals():
    global prev_vals
    return prev_vals


def set_prev_vals(vals):
    global prev_vals
    prev_vals = vals.copy() if vals is not None else None


def get_clients():
    return [SimpleUDPClient(host, int(params["PORT"])) for host in params["HOSTS"]]


def get_client_gh():
    return SimpleUDPClient(params["HOST"], int(params["PORT"]))


def send_all_setTargetPositionList(vals):
    sent_boards = False
    sent_gh = False
    if params.get("SEND_CLIENTS", True):
        clients = get_clients()
        for i, client in enumerate(clients):
            vals_part = vals[i * VALS_PER_HOST : (i + 1) * VALS_PER_HOST]
            try:
                client.send_message("/setTargetPositionList", vals_part)
                sent_boards = True
            except Exception as e:
                print(f"send error to {params['HOSTS'][i]}:", e)
    if params.get("SEND_CLIENT_GH", False):
        client_gh = get_client_gh()
        try:
            client_gh.send_message("/setTargetPositionList", vals)
            sent_gh = True
        except Exception as e:
            print(f"send error to {params['HOST']}: {e}")
    set_prev_vals(vals)
    return sent_boards, sent_gh


def filter_vals(raw_vals, alpha):
    prev = get_prev_vals()
    if prev is None:
        return raw_vals
    return [int(p + alpha * (c - p)) for p, c in zip(prev, raw_vals)]


def osc_sender(params, stop_event):
    from osc_sender import send_all_setTargetPositionList

    interval = 1.0 / float(params["RATE_fps"])
    start = time.time()
    frame = 0
    last_msg_len = 0
    while not stop_event.is_set():
        now = time.time()
        raw_vals = make_frame(now - start, NUM_SERVOS, params)
        alpha = float(params.get("ALPHA", 0.2))
        prev = get_prev_vals()
        if prev is None:
            filt_vals = raw_vals
        else:
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
        sys.stderr.write(msg + pad)
        sys.stderr.flush()
        last_msg_len = len(msg)
        frame += 1
        elapsed = time.time() - now
        sleep_time = interval - elapsed
        if sleep_time > 0:
            time.sleep(sleep_time)
