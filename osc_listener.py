from pythonosc.osc_packet import OscPacket
from pythonosc.osc_bundle import OscBundle
from pythonosc.dispatcher import Dispatcher
import socketserver
import threading

_message_callbacks = []
_bundle_callbacks = []  # バンドル専用のコールバックリスト


def register_message_callback(cb):
    _message_callbacks.append(cb)


def register_bundle_callback(cb):
    _bundle_callbacks.append(cb)


class MyUDPHandler(socketserver.BaseRequestHandler):
    def handle(self):
        data, _ = self.request
        try:
            pkt = OscPacket(data)
        except Exception as e:
            print("Invalid OSC packet:", e)
            return

        is_bundle = False
        try:
            is_bundle = OscBundle.dgram_is_bundle(data)
        except Exception:
            pass

        if is_bundle:
            print(f"Received a bundle {pkt.messages}")
            bundle_contents = []
            for timed in pkt.messages:
                msg = timed.message
                addr = msg.address
                args = msg.params
                bundle_contents.append((addr, args))

            for cb in _bundle_callbacks:
                try:
                    cb(bundle_contents)
                except Exception as e:
                    print("Bundle callback error:", e)
        else:
            for timed in pkt.messages:
                msg = timed.message
                addr = msg.address
                args = msg.params
                print(f"Received a single message {addr} {args}")
                for cb in _message_callbacks:
                    try:
                        cb(addr, *args)
                    except Exception as e:
                        print("Callback error:", e)


def start_osc_listener(port):
    class Server(socketserver.ThreadingUDPServer):
        allow_reuse_address = True

    server = Server(("0.0.0.0", port), MyUDPHandler)
    print(f"OSC listener (low-level) started on port {port}")
    server.serve_forever()


def start_osc_listener_thread(port=10000):
    t = threading.Thread(target=start_osc_listener, args=(port,), daemon=True)
    t.start()
