import os
import struct
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QPoint, Qt
from PyQt5.QtGui import QColor, QImage, QPainter

from core.vnc_client import (
    ENCODING_COPYRECT,
    ENCODING_HEXTILE,
    ENCODING_RAW,
    RFB_VERSION,
    VNC_IO_TIMEOUT_SECONDS,
    VncClientWorker,
    VncDisplayWidget,
)


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

    def test_display_widget_hides_local_cursor_only_while_showing_remote_frame(self):
        app = QApplication.instance() or QApplication([])
        widget = VncDisplayWidget()
        try:
            self.assertEqual(widget.cursor().shape(), Qt.ArrowCursor)

            image = QImage(8, 8, QImage.Format_RGB32)
            image.fill(Qt.black)
            widget.set_framebuffer(image)
            self.assertEqual(widget.cursor().shape(), Qt.BlankCursor)

            widget.clear()
            self.assertEqual(widget.cursor().shape(), Qt.ArrowCursor)
        finally:
            widget.deleteLater()
            app.processEvents()

    def test_pointer_moves_are_coalesced_to_latest_position(self):
        worker = VncClientWorker("jetson@192.168.55.1")
        worker._channel = FakeChannel(b"")

        worker.send_pointer(1, 2, 0)
        worker.send_pointer(3, 4, 0)
        worker.send_pointer(5, 6, 0)
        worker._drain_outgoing()

        self.assertEqual(len(worker._channel.sent), 1)
        self.assertEqual(struct.unpack(">BBHH", worker._channel.sent[0]), (5, 0, 5, 6))

    def test_pointer_button_transitions_are_not_coalesced_away(self):
        worker = VncClientWorker("jetson@192.168.55.1")
        worker._channel = FakeChannel(b"")

        worker.send_pointer(1, 2, 0)
        worker.send_pointer(10, 20, 1)
        worker.send_pointer(11, 21, 1)
        worker.send_pointer(12, 22, 0)
        worker._drain_outgoing()

        packets = [struct.unpack(">BBHH", item) for item in worker._channel.sent]
        self.assertEqual(packets, [(5, 1, 10, 20), (5, 0, 12, 22)])
        self.assertLessEqual(VNC_IO_TIMEOUT_SECONDS, 0.05)

    def test_display_widget_coalesces_mouse_moves_in_ui_layer(self):
        app = QApplication.instance() or QApplication([])
        widget = VncDisplayWidget()
        widget.setMinimumHeight(1)
        widget.resize(100, 100)
        image = QImage(100, 100, QImage.Format_RGB32)
        image.fill(Qt.black)
        widget.set_framebuffer(image)
        events = []
        widget.pointer_event.connect(lambda x, y, mask: events.append((x, y, mask)))
        try:
            widget._emit_pointer(QPoint(10, 20))
            widget._emit_pointer(QPoint(30, 40))

            self.assertEqual(events, [])
            widget._flush_pending_pointer_event()
            self.assertEqual(events, [(30, 40, 0)])

            widget._emit_pointer(QPoint(50, 60), immediate=True)
            self.assertEqual(events[-1], (50, 60, 0))
        finally:
            widget.deleteLater()
            app.processEvents()

    def test_set_encodings_prefers_hextile_copyrect_then_raw(self):
        worker = VncClientWorker("jetson@192.168.55.1")
        worker._channel = FakeChannel(b"")

        worker._set_encodings()

        message = worker._channel.sent[-1]
        self.assertEqual(message[0], 2)
        count = struct.unpack(">H", message[2:4])[0]
        encodings = [
            struct.unpack(">i", message[4 + index * 4:8 + index * 4])[0]
            for index in range(count)
        ]
        self.assertEqual(encodings[:3], [ENCODING_HEXTILE, ENCODING_COPYRECT, ENCODING_RAW])

    def test_copyrect_encoding_copies_existing_pixels(self):
        worker = VncClientWorker("jetson@192.168.55.1")
        worker._image = QImage(4, 4, QImage.Format_RGB32)
        worker._image.fill(Qt.black)
        painter = QPainter(worker._image)
        painter.fillRect(0, 0, 2, 2, QColor(255, 0, 0))
        painter.end()
        payload = b"".join([
            b"\x00",
            struct.pack(">H", 1),
            struct.pack(">HHHHi", 2, 0, 2, 2, ENCODING_COPYRECT),
            struct.pack(">HH", 0, 0),
        ])
        worker._channel = FakeChannel(payload)

        worker._handle_framebuffer_update()

        self.assertEqual(worker._image.pixelColor(2, 0), QColor(255, 0, 0))
        self.assertEqual(worker._image.pixelColor(3, 1), QColor(255, 0, 0))

    def test_hextile_encoding_fills_background_and_subrects(self):
        worker = VncClientWorker("jetson@192.168.55.1")
        worker._image = QImage(4, 4, QImage.Format_RGB32)
        worker._image.fill(Qt.black)
        green_pixel = (0x0000FF00).to_bytes(4, "little")
        red_pixel = (0x00FF0000).to_bytes(4, "little")
        payload = b"".join([
            b"\x00",
            struct.pack(">H", 1),
            struct.pack(">HHHHi", 1, 1, 2, 2, ENCODING_HEXTILE),
            b"\x1A",
            green_pixel,
            b"\x01",
            red_pixel,
            b"\x00",
            b"\x00",
        ])
        worker._channel = FakeChannel(payload)

        worker._handle_framebuffer_update()

        self.assertEqual(worker._image.pixelColor(1, 1), QColor(255, 0, 0))
        self.assertEqual(worker._image.pixelColor(2, 2), QColor(0, 255, 0))


if __name__ == "__main__":
    unittest.main()
