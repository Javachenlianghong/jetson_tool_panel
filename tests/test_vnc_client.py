import os
import struct
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

from core.vnc_client import RFB_VERSION, VncClientWorker


class FakeChannel:
    def __init__(self, payload):
        self.payload = bytearray(payload)
        self.sent = []

    def recv(self, size):
        if not self.payload:
            return b""
        chunk = bytes(self.payload[:size])
        del self.payload[:size]
        return chunk

    def sendall(self, payload):
        self.sent.append(payload)


class VncClientTest(unittest.TestCase):
    def test_handshake_reads_name_length_from_server_init_packet(self):
        app = QApplication.instance() or QApplication([])
        name = b"Jetson Desktop"
        pixel_format = bytes(16)
        payload = b"".join([
            RFB_VERSION,
            b"\x01",
            b"\x01",
            struct.pack(">I", 0),
            struct.pack(">HH", 800, 600),
            pixel_format,
            struct.pack(">I", len(name)),
            name,
        ])
        worker = VncClientWorker("jetson@192.168.55.1")
        worker._channel = FakeChannel(payload)
        connected = []
        worker.connected.connect(lambda width, height, title: connected.append((width, height, title)))

        worker._handshake()

        self.assertEqual(connected, [(800, 600, "Jetson Desktop")])
        self.assertTrue(any(item == RFB_VERSION for item in worker._channel.sent))
        self.assertGreater(worker._width, 0)
        self.assertIsNotNone(worker._image)
        app.processEvents()


if __name__ == "__main__":
    unittest.main()
