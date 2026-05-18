import unittest
import os
import sys
import time

from core.command_controller import CommandController
from core.command_runner import CommandWorker, decode_process_output


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_QT_APP = None


def process_events_until(predicate, timeout=5):
    global _QT_APP
    from PyQt5.QtWidgets import QApplication

    app = QApplication.instance() or _QT_APP or QApplication([])
    _QT_APP = app
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    return False


class CommandRunnerDecodeTest(unittest.TestCase):
    def test_decodes_utf8_remote_output(self):
        line = "状态 正常 ✓\n".encode("utf-8")
        self.assertEqual(decode_process_output(line), "状态 正常 ✓")

    def test_falls_back_to_windows_code_page_output(self):
        line = "防火墙已启用\n".encode("gbk")
        self.assertEqual(decode_process_output(line), "防火墙已启用")

    def test_replaces_unknown_bytes_instead_of_raising(self):
        decoded = decode_process_output(b"\xff\xfe\xfa\n")
        self.assertIsInstance(decoded, str)

    def test_command_worker_finishes_on_done_marker(self):
        finished = []
        output = []
        worker = CommandWorker(
            [
                sys.executable,
                "-c",
                (
                    "import time; "
                    "print('visible', flush=True); "
                    "print('__JTP_DONE__:7', flush=True); "
                    "time.sleep(5)"
                ),
            ],
            done_marker="__JTP_DONE__",
            stop_on_done_marker=True,
        )
        worker.output.connect(output.append)
        worker.finished_ok.connect(finished.append)

        started = time.monotonic()
        worker.start()
        self.assertTrue(process_events_until(lambda: bool(finished), timeout=4))
        worker.wait(1000)

        self.assertLess(time.monotonic() - started, 4)
        self.assertEqual(output, ["visible"])
        self.assertEqual(finished, [7])

    def test_command_controller_channels_run_independently(self):
        finished = []
        controller = CommandController()
        controller.finished.connect(lambda channel, code, timed_out: finished.append((channel, code, timed_out)))

        self.assertTrue(controller.start(
            "long",
            "long sleep",
            [sys.executable, "-c", "import time; time.sleep(5)"],
        ))
        self.assertTrue(controller.start(
            "short",
            "short print",
            [sys.executable, "-c", "print('short', flush=True)"],
        ))

        self.assertTrue(process_events_until(lambda: any(item[0] == "short" for item in finished), timeout=4))
        self.assertTrue(controller.is_running("long"))
        self.assertFalse(controller.is_running("short"))

        controller.stop("long")
        self.assertTrue(process_events_until(lambda: any(item[0] == "long" for item in finished), timeout=4))
        self.assertFalse(controller.is_running("long"))


if __name__ == "__main__":
    unittest.main()
