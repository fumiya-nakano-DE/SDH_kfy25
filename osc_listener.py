from pythonosc.osc_packet import OscPacket
from pythonosc.osc_bundle import OscBundle
from pythonosc.dispatcher import Dispatcher
import socketserver
import threading
from logger_config import logger

_message_callbacks = []
_bundle_callbacks = []


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
            logger.error("Invalid OSC packet: %s", e)
            return

        is_bundle = False
        try:
            is_bundle = OscBundle.dgram_is_bundle(data)
        except Exception:
            pass

        if is_bundle:
            logger.info("Received a bundle with %d messages", len(pkt.messages))
            bundle_contents = []
            for timed in pkt.messages:
                msg = timed.message
                addr = msg.address
                args = msg.params
                bundle_contents.append((addr, args))
                logger.debug(" → Bundle Message: %s %s", addr, args)

            for cb in _bundle_callbacks:
                try:
                    cb(bundle_contents)
                except Exception as e:
                    logger.error("Bundle callback error: %s", e)
        else:
            for timed in pkt.messages:
                msg = timed.message
                addr = msg.address
                args = msg.params
                logger.info("Received a single message: %s %s", addr, args)
                for cb in _message_callbacks:
                    try:
                        cb(addr, *args)
                    except Exception as e:
                        logger.error("Callback error: %s", e)


def start_osc_listener(port):
    class Server(socketserver.ThreadingUDPServer):
        allow_reuse_address = True

    server = Server(("0.0.0.0", port), MyUDPHandler)
    logger.info(f"OSC listener from PLAYER started on port {port}")
    server.serve_forever()


def start_osc_listener_thread(port=10000):
    t = threading.Thread(target=start_osc_listener, args=(port,), daemon=True)
    t.start()
