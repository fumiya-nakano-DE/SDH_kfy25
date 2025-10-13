from pythonosc.udp_client import SimpleUDPClient
from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import BlockingOSCUDPServer
import threading
import time

HOST = "10.0.0.100"
PORT_SEND = 50000
PORT_RECEIVE = 50100

client = SimpleUDPClient(HOST, PORT_SEND)

def sendosc(message, args):
    try:
        client.send_message(message, args)
        print(f"Message:{message}{args} sent successfully")
    except Exception as e:
        print("Error sending message:", e)


def start_receiver(port: int = 50100):
    """Start an OSC receiver on given port in a background thread and print messages.

    Returns (server, thread).
    """
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
    print(f"OSC Receiver started on 0.0.0.0:{port} (printing incoming messages)")
    return server, t
    
def main():
    sendosc("/enableServoMode", [255, 0])
    sendosc("/setSpeedProfile",[255,100,100,100])
    sendosc("/goTo", [255,50000])
    time.sleep(1)
    for _ in range(10):
        sendosc("/goTo", [255,60000])
        time.sleep(2)
        sendosc("/goTo", [255,40000])
        time.sleep(2)
    sendosc("/goTo", [255,50000])



if __name__ == "__main__":
    start_receiver(PORT_RECEIVE)
    print(f"HOST:{HOST} SEND:{PORT_SEND} RECEIVE:{PORT_RECEIVE}")

    main()

    print("Listening... Press Ctrl+C to exit.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Exiting.")