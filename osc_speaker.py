from pythonosc.udp_client import SimpleUDPClient
from logger_config import logger

class OSCSpeaker:
    def __init__(self, host="127.0.0.1", port=10001):
        self.host = host
        self.port = port
        self.client = SimpleUDPClient(self.host, self.port)

    def send_message(self, address, *args):
        self.client.send_message(address, args)
        logger.info(f"Sending OSC Message to {self.host}:{self.port} - {address} {args}")

    def close(self):
        logger.info("OSC Speaker closed.")


osc_speaker = OSCSpeaker()
