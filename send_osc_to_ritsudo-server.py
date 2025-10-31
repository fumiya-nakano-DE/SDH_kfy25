from pythonosc.udp_client import SimpleUDPClient
from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import BlockingOSCUDPServer
from pythonosc import osc_bundle_builder
from pythonosc import osc_message_builder
import threading
import time

HOST = "127.0.0.1"
PORT_SEND = 10000
PORT_RECEIVE = 10001  # 修正: 送信元のポートと一致させる

client = SimpleUDPClient(HOST, PORT_SEND)


def start_receiver(port):
    dispatcher = Dispatcher()

    def _print_handler(address, *msg_args):
        try:
            print(f"[OSC {port}] {address} {msg_args}")
        except Exception as e:
            print(f"Handler error on {port}: {e}")

    dispatcher.set_default_handler(_print_handler)
    server = BlockingOSCUDPServer(("0.0.0.0", port), dispatcher)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    print(f"OSC Receiver started on {HOST}:{port} (printing incoming messages)")
    return server, t


def sendosc_message(message, args):
    try:
        client.send_message(message, args)
        print(f"Message:{message}{args} sent successfully")
    except Exception as e:
        print("Error sending message:", e)


def sendosc_bundle(bundle):
    try:
        client.send(bundle)
        print(f"Bundle:{bundle} sent successfully")
    except Exception as e:
        print("Error sending bundle:", e)


def continuous():
    for i in range(0, 200, 2):
        sendosc_message("/U_AVERAGE", [i * 0.01])
        time.sleep(0.1)


# =================================================


def mode_change():
    modes = ["101", "102", "201", "202", "301", "302", "401"]
    for mode in modes:
        sendosc_message("/MODE", [mode])
        print(f"Changed mode to {mode}")
        time.sleep(1)


def set_mode_with_params(mode):
    bundle = osc_bundle_builder.OscBundleBuilder(osc_bundle_builder.IMMEDIATELY)

    msg = osc_message_builder.OscMessageBuilder(address="/MODE")
    msg.add_arg(mode)
    bundle.add_content(msg.build())

    msg = osc_message_builder.OscMessageBuilder(address="/EASING_DURATION")
    msg.add_arg(1.0)
    bundle.add_content(msg.build())

    print(f"Sending bundle: {bundle}")
    client.send(bundle.build())


# =================================================

if __name__ == "__main__":
    start_receiver(PORT_RECEIVE)
    # sendosc_message("/RaiseError", [])

    # sendosc_message("/Neutral", [])
    # time.sleep(1)
    # sendosc_message("/Start", [])
    # time.sleep(3)
    # sendosc_message("/Release", [])

    # set_mode_with_params("421")
    # time.sleep(5)
    # set_mode_with_params("421")

    # sendosc_message("/STROKE_LENGTH", [500000])
    # time.sleep(3)
    sendosc_message("/GetAverageSpeed", [])
    sendosc_message("/GetSpeed", [])
    sendosc_message("/GetPosition", [])

    try:
        print("Running... press Ctrl-C to stop")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Interrupted by user, exiting.")
