"""Minimal embedded RFB/VNC client for x11vnc over Paramiko direct-tcpip."""

import queue
import socket
import struct
import threading
import time

from PyQt5.QtCore import QPoint, Qt, QThread, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QImage, QPainter
from PyQt5.QtWidgets import QSizePolicy, QWidget

from services import paramiko_service


RFB_VERSION = b"RFB 003.008\n"
VNC_IO_TIMEOUT_SECONDS = 0.03
ENCODING_RAW = 0
ENCODING_COPYRECT = 1
ENCODING_HEXTILE = 5
ENCODING_DESKTOP_SIZE = -223

HEXTILE_RAW = 1
HEXTILE_BACKGROUND_SPECIFIED = 2
HEXTILE_FOREGROUND_SPECIFIED = 4
HEXTILE_ANY_SUBRECTS = 8
HEXTILE_SUBRECTS_COLORED = 16


class VncClientWorker(QThread):
    connected = pyqtSignal(int, int, str)
    framebuffer = pyqtSignal(QImage)
    status = pyqtSignal(str)
    auth_failed = pyqtSignal(str)
    failed = pyqtSignal(str)
    disconnected = pyqtSignal()

    def __init__(self, remote, remote_port=5900, password=None, parent=None):
        super().__init__(parent)
        self.remote = remote
        self.remote_port = int(remote_port or 5900)
        self.password = password
        self._client = None
        self._channel = None
        self._running = True
        self._outgoing = queue.Queue()
        self._pending_pointer = None
        self._pointer_lock = threading.Lock()
        self._last_pointer_mask = 0
        self._width = 0
        self._height = 0
        self._image = None

    def stop(self):
        self._running = False
        self._close()

    def send_key(self, keysym, down=True):
        self._outgoing.put(struct.pack(">BBHI", 4, 1 if down else 0, 0, int(keysym)))

    def send_pointer(self, x, y, button_mask):
        mask = int(button_mask) & 0xFF
        payload = struct.pack(">BBHH", 5, mask, int(x), int(y))
        with self._pointer_lock:
            if mask != self._last_pointer_mask:
                self._last_pointer_mask = mask
                self._pending_pointer = None
                self._outgoing.put(payload)
            else:
                self._pending_pointer = payload

    def run(self):
        try:
            self.status.emit("正在建立 SSH 直连通道...")
            self._client, target = paramiko_service.create_ssh_client(
                self.remote,
                password=self.password,
                timeout=10,
            )
            transport = self._client.get_transport()
            if transport is None:
                raise RuntimeError("SSH transport is not available.")
            self._channel = self._open_vnc_channel(transport)
            self._channel.settimeout(VNC_IO_TIMEOUT_SECONDS)
            self.status.emit("已连接 VNC: {}:{}".format(target.display, self.remote_port))
            self._handshake()
            self._request_update(incremental=False)
            while self._running:
                self._drain_outgoing()
                try:
                    message_type = self._read_exact(1)
                except socket.timeout:
                    continue
                if not message_type:
                    break
                message_type = message_type[0]
                if message_type == 0:
                    self._handle_framebuffer_update()
                    self._request_update(incremental=True)
                elif message_type == 2:
                    self.status.emit("VNC bell")
                elif message_type == 3:
                    self._handle_server_cut_text()
                else:
                    self.status.emit("忽略 VNC 消息类型: {}".format(message_type))
        except Exception as exc:
            if not self._running:
                pass
            elif "Authentication" in exc.__class__.__name__:
                self.auth_failed.emit(str(exc))
            else:
                self.failed.emit(str(exc))
        finally:
            self._close()
            self.disconnected.emit()

    def _open_vnc_channel(self, transport):
        last_error = None
        deadline = time.monotonic() + 6
        attempt = 0
        while self._running and time.monotonic() < deadline:
            attempt += 1
            try:
                return transport.open_channel(
                    "direct-tcpip",
                    ("127.0.0.1", self.remote_port),
                    ("127.0.0.1", 0),
                )
            except Exception as exc:
                last_error = exc
                message = str(exc).lower()
                if "connection refused" not in message and "connect failed" not in message:
                    raise
                if attempt == 1:
                    self.status.emit("VNC 端口尚未就绪，正在重试...")
                time.sleep(0.4)
        raise RuntimeError("VNC 端口 127.0.0.1:{} 未监听: {}".format(self.remote_port, last_error))

    def _handshake(self):
        version = self._read_exact(12)
        if not version.startswith(b"RFB "):
            raise RuntimeError("Invalid VNC server greeting: {!r}".format(version))
        self._send(RFB_VERSION)
        count = self._read_exact(1)[0]
        if count == 0:
            reason_length = struct.unpack(">I", self._read_exact(4))[0]
            reason = self._read_exact(reason_length).decode("utf-8", errors="replace")
            raise RuntimeError(reason)
        security_types = self._read_exact(count)
        if 1 not in security_types:
            raise RuntimeError("VNC server requires unsupported security type: {}".format(list(security_types)))
        self._send(b"\x01")
        result = struct.unpack(">I", self._read_exact(4))[0]
        if result != 0:
            raise RuntimeError("VNC security handshake failed: {}".format(result))
        self._send(b"\x01")
        server_init = self._read_exact(24)
        self._width, self._height = struct.unpack(">HH", server_init[:4])
        name_length = struct.unpack(">I", server_init[20:24])[0]
        name = self._read_exact(name_length).decode("utf-8", errors="replace") if name_length else "VNC"
        self._image = QImage(self._width, self._height, QImage.Format_RGB32)
        self._image.fill(Qt.black)
        self._set_pixel_format()
        self._set_encodings()
        self.connected.emit(self._width, self._height, name)

    def _set_pixel_format(self):
        pixel_format = struct.pack(
            ">BBBBHHHBBBxxx",
            32,
            24,
            0,
            1,
            255,
            255,
            255,
            16,
            8,
            0,
        )
        self._send(struct.pack(">Bxxx", 0) + pixel_format)

    def _set_encodings(self):
        encodings = [ENCODING_HEXTILE, ENCODING_COPYRECT, ENCODING_RAW, ENCODING_DESKTOP_SIZE]
        payload = struct.pack(">BxH", 2, len(encodings))
        payload += b"".join(struct.pack(">i", item) for item in encodings)
        self._send(payload)

    def _request_update(self, incremental):
        if self._width > 0 and self._height > 0:
            self._send(struct.pack(">BBHHHH", 3, 1 if incremental else 0, 0, 0, self._width, self._height))

    def _handle_framebuffer_update(self):
        self._read_exact(1)
        rect_count = struct.unpack(">H", self._read_exact(2))[0]
        changed = False
        for _index in range(rect_count):
            x, y, width, height, encoding = struct.unpack(">HHHHi", self._read_exact(12))
            if encoding == ENCODING_RAW:
                self._draw_raw_rect(x, y, width, height)
                changed = True
            elif encoding == ENCODING_COPYRECT:
                self._handle_copyrect(x, y, width, height)
                changed = True
            elif encoding == ENCODING_HEXTILE:
                self._handle_hextile(x, y, width, height)
                changed = True
            elif encoding == ENCODING_DESKTOP_SIZE:
                self._width, self._height = width, height
                self._image = QImage(self._width, self._height, QImage.Format_RGB32)
                self._image.fill(Qt.black)
                self.connected.emit(self._width, self._height, "VNC")
                changed = True
            else:
                raise RuntimeError("Unsupported VNC encoding: {}".format(encoding))
        if changed and self._image is not None:
            self.framebuffer.emit(self._image.copy())

    def _draw_raw_rect(self, x, y, width, height):
        raw = self._read_exact(width * height * 4)
        rect = QImage(raw, width, height, QImage.Format_RGB32).copy()
        painter = QPainter(self._image)
        painter.drawImage(x, y, rect)
        painter.end()

    def _handle_copyrect(self, x, y, width, height):
        source_x, source_y = struct.unpack(">HH", self._read_exact(4))
        rect = self._image.copy(source_x, source_y, width, height)
        painter = QPainter(self._image)
        painter.drawImage(x, y, rect)
        painter.end()

    def _handle_hextile(self, x, y, width, height):
        background = QColor(0, 0, 0)
        foreground = QColor(255, 255, 255)
        for tile_y in range(y, y + height, 16):
            tile_height = min(16, y + height - tile_y)
            for tile_x in range(x, x + width, 16):
                tile_width = min(16, x + width - tile_x)
                subencoding = self._read_exact(1)[0]
                if subencoding & HEXTILE_RAW:
                    self._draw_raw_rect(tile_x, tile_y, tile_width, tile_height)
                    continue
                if subencoding & HEXTILE_BACKGROUND_SPECIFIED:
                    background = self._read_pixel_color()
                painter = QPainter(self._image)
                painter.fillRect(tile_x, tile_y, tile_width, tile_height, background)
                painter.end()
                if subencoding & HEXTILE_FOREGROUND_SPECIFIED:
                    foreground = self._read_pixel_color()
                if subencoding & HEXTILE_ANY_SUBRECTS:
                    subrect_count = self._read_exact(1)[0]
                    for _index in range(subrect_count):
                        color = self._read_pixel_color() if subencoding & HEXTILE_SUBRECTS_COLORED else foreground
                        xy = self._read_exact(1)[0]
                        wh = self._read_exact(1)[0]
                        sub_x = xy >> 4
                        sub_y = xy & 0x0F
                        sub_width = (wh >> 4) + 1
                        sub_height = (wh & 0x0F) + 1
                        painter = QPainter(self._image)
                        painter.fillRect(tile_x + sub_x, tile_y + sub_y, sub_width, sub_height, color)
                        painter.end()

    def _read_pixel_color(self):
        value = int.from_bytes(self._read_exact(4), "little")
        return QColor((value >> 16) & 0xFF, (value >> 8) & 0xFF, value & 0xFF)

    def _handle_server_cut_text(self):
        self._read_exact(3)
        length = struct.unpack(">I", self._read_exact(4))[0]
        if length:
            self._read_exact(length)

    def _drain_outgoing(self):
        while self._running:
            sent = False
            while self._running:
                try:
                    payload = self._outgoing.get_nowait()
                except queue.Empty:
                    break
                self._send(payload)
                sent = True
            pointer_payload = self._take_pending_pointer()
            if pointer_payload:
                self._send(pointer_payload)
                sent = True
            if not sent:
                return

    def _take_pending_pointer(self):
        with self._pointer_lock:
            payload = self._pending_pointer
            self._pending_pointer = None
            return payload

    def _read_exact(self, size):
        chunks = []
        remaining = int(size)
        while remaining > 0 and self._running:
            try:
                chunk = self._channel.recv(remaining)
            except socket.timeout:
                self._drain_outgoing()
                continue
            if not chunk:
                raise EOFError("VNC connection closed.")
            chunks.append(chunk)
            remaining -= len(chunk)
        if remaining > 0:
            raise EOFError("VNC read cancelled.")
        return b"".join(chunks)

    def _send(self, payload):
        if self._channel is None:
            return
        self._channel.sendall(payload)

    def _close(self):
        try:
            if self._channel is not None:
                self._channel.close()
        except Exception:
            pass
        try:
            if self._client is not None:
                self._client.close()
        except Exception:
            pass


class VncDisplayWidget(QWidget):
    pointer_event = pyqtSignal(int, int, int)
    key_event = pyqtSignal(int, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._image = QImage()
        self._frame_size = (0, 0)
        self._button_mask = 0
        self._pending_pointer_event = None
        self._pointer_emit_timer = QTimer(self)
        self._pointer_emit_timer.setInterval(16)
        self._pointer_emit_timer.timeout.connect(self._flush_pending_pointer_event)
        self.setMinimumHeight(420)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)
        self.setCursor(Qt.ArrowCursor)

    def set_framebuffer(self, image):
        self._image = image
        self._frame_size = (image.width(), image.height())
        self.setCursor(Qt.BlankCursor if not image.isNull() else Qt.ArrowCursor)
        self.update()

    def clear(self):
        self._image = QImage()
        self._frame_size = (0, 0)
        self._pending_pointer_event = None
        self._pointer_emit_timer.stop()
        self.setCursor(Qt.ArrowCursor)
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.black)
        if self._image.isNull():
            painter.setPen(Qt.white)
            painter.drawText(self.rect(), Qt.AlignCenter, "未连接远程桌面")
            painter.end()
            return
        target = self._target_rect()
        painter.drawImage(target, self._image)
        painter.end()

    def mousePressEvent(self, event):
        self.setFocus()
        self._button_mask |= self._button_from_event(event)
        self._emit_pointer(event.pos(), immediate=True)

    def mouseReleaseEvent(self, event):
        self._button_mask &= ~self._button_from_event(event)
        self._emit_pointer(event.pos(), immediate=True)

    def mouseMoveEvent(self, event):
        self._emit_pointer(event.pos())

    def wheelEvent(self, event):
        mask = 8 if event.angleDelta().y() > 0 else 16
        point = event.position().toPoint() if hasattr(event, "position") else event.pos()
        x, y = self._map_point(point)
        self.pointer_event.emit(x, y, mask)
        self.pointer_event.emit(x, y, 0)

    def keyPressEvent(self, event):
        keysym = self._keysym(event)
        if keysym is not None:
            self.key_event.emit(keysym, True)
            event.accept()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        keysym = self._keysym(event)
        if keysym is not None:
            self.key_event.emit(keysym, False)
            event.accept()
            return
        super().keyReleaseEvent(event)

    def _emit_pointer(self, point, immediate=False):
        x, y = self._map_point(point)
        if immediate:
            self._pending_pointer_event = None
            self.pointer_event.emit(x, y, self._button_mask)
            return
        self._pending_pointer_event = (x, y, self._button_mask)
        if not self._pointer_emit_timer.isActive():
            self._pointer_emit_timer.start()

    def _flush_pending_pointer_event(self):
        event = self._pending_pointer_event
        self._pending_pointer_event = None
        if event is None:
            self._pointer_emit_timer.stop()
            return
        self.pointer_event.emit(*event)

    def _button_from_event(self, event):
        if event.button() == Qt.LeftButton:
            return 1
        if event.button() == Qt.MiddleButton:
            return 2
        if event.button() == Qt.RightButton:
            return 4
        return 0

    def _target_rect(self):
        image_width, image_height = self._frame_size
        if image_width <= 0 or image_height <= 0:
            return self.rect()
        scale = min(self.width() / image_width, self.height() / image_height)
        width = int(image_width * scale)
        height = int(image_height * scale)
        x = (self.width() - width) // 2
        y = (self.height() - height) // 2
        return self.rect().adjusted(x, y, -(self.width() - x - width), -(self.height() - y - height))

    def _map_point(self, point):
        image_width, image_height = self._frame_size
        if image_width <= 0 or image_height <= 0:
            return 0, 0
        target = self._target_rect()
        x = int((point.x() - target.x()) * image_width / max(target.width(), 1))
        y = int((point.y() - target.y()) * image_height / max(target.height(), 1))
        return max(0, min(image_width - 1, x)), max(0, min(image_height - 1, y))

    def _keysym(self, event):
        key_map = {
            Qt.Key_Backspace: 0xFF08,
            Qt.Key_Tab: 0xFF09,
            Qt.Key_Return: 0xFF0D,
            Qt.Key_Enter: 0xFF0D,
            Qt.Key_Escape: 0xFF1B,
            Qt.Key_Delete: 0xFFFF,
            Qt.Key_Home: 0xFF50,
            Qt.Key_Left: 0xFF51,
            Qt.Key_Up: 0xFF52,
            Qt.Key_Right: 0xFF53,
            Qt.Key_Down: 0xFF54,
            Qt.Key_PageUp: 0xFF55,
            Qt.Key_PageDown: 0xFF56,
            Qt.Key_End: 0xFF57,
        }
        if event.key() in key_map:
            return key_map[event.key()]
        text = event.text()
        if text:
            return ord(text[0])
        return None
