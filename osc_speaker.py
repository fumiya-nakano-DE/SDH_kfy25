from pythonosc.udp_client import SimpleUDPClient


class OSCSpeaker:
    def __init__(self, host="127.0.0.1", port=10001):
        """
        Initialize the OSC speaker with the target host and port.
        """
        self.host = host
        self.port = port
        self.client = SimpleUDPClient(self.host, self.port)

    def send_message(self, address, *args):
        """
        Send an OSC message to the specified address with arguments.
        """
        self.client.send_message(address, args)
        print(f"Sending OSC Message to {self.host}:{self.port} - {address} {args}")

    def close(self):
        """
        Close the OSC client (no explicit close needed for pythonosc).
        """
        print("OSC Speaker closed.")


osc_speaker = OSCSpeaker()
