from pythonosc.udp_client import SimpleUDPClient
from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import BlockingOSCUDPServer
from pythonosc import osc_bundle_builder
from pythonosc import osc_message_builder
import threading
import time

HOST = "127.0.0.1"
PORT_SEND = 10000

client = SimpleUDPClient(HOST, PORT_SEND)


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


"""
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
"""


def continuous():
    for i in range(0, 200, 2):
        sendosc_message("/U_AVERAGE", [i * 0.01])
        time.sleep(0.1)


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

    print(f"Sending bundle: {bundle}")  # デバッグ用にバンドル内容を出力
    client.send(bundle.build())


if __name__ == "__main__":
    continuous()
    mode_change()
    # set_mode_with_params("101")
