import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class UiSmokeTest(unittest.TestCase):
    def test_main_window_contains_terminal_and_double_pane_files(self):
        try:
            from PyQt5.QtCore import Qt
            from PyQt5.QtWidgets import QApplication, QCheckBox, QPushButton
            from ui.main_window import JetsonControlPanel
        except Exception as exc:  # pragma: no cover - only used when Qt is unavailable.
            self.skipTest(str(exc))

        app = QApplication.instance() or QApplication([])
        window = JetsonControlPanel()
        try:
            self.assertIn("terminal", window.page_key_to_index)
            self.assertIn("desktop", window.page_key_to_index)
            self.assertIsNotNone(window.terminal_output_edit)
            self.assertIsNotNone(window.local_files_table)
            self.assertIsNotNone(window.remote_files_table)
            self.assertIsNotNone(window.transfer_progress_bar)
            self.assertEqual(window.local_files_table.contextMenuPolicy(), Qt.CustomContextMenu)
            self.assertEqual(window.remote_files_table.contextMenuPolicy(), Qt.CustomContextMenu)
            self.assertFalse(window.terminal_output_edit.tabChangesFocus())
            self.assertTrue(window.terminal_output_edit._cursor_timer.isActive())
            self.assertTrue(hasattr(window, "remote_open_selected_path"))
            self.assertEqual(
                set(window.monitor_labels),
                {"cpu", "memory", "gpu", "temperature"},
            )
            self.assertIsNotNone(window.monitor_status_label)
            terminal_page = window.page_stack.widget(window.page_key_to_index["terminal"])
            button_texts = [button.text() for button in terminal_page.findChildren(QPushButton)]
            self.assertIn("同步到 Jetson", button_texts)
            self.assertIn("本地预览", button_texts)
            self.assertIn("检测 DISPLAY", button_texts)
            self.assertTrue(hasattr(window, "preview_remote_selected_file"))
            checkbox_texts = [checkbox.text() for checkbox in terminal_page.findChildren(QCheckBox)]
            self.assertIn("连接后导出 DISPLAY", checkbox_texts)
            proxy_page = window.page_stack.widget(window.page_key_to_index["proxy"])
            proxy_button_texts = [button.text() for button in proxy_page.findChildren(QPushButton)]
            self.assertIn("取消 Jetson 代理配置", proxy_button_texts)
            self.assertTrue(hasattr(window, "disable_jetson_proxy_config"))
            model_page = window.page_stack.widget(window.page_key_to_index["model"])
            model_button_texts = [button.text() for button in model_page.findChildren(QPushButton)]
            self.assertIn("选择", model_button_texts)
            self.assertIn("检测 TensorRT", model_button_texts)
            self.assertIn("转换并 Benchmark", model_button_texts)
            self.assertTrue(hasattr(window, "choose_model_source_file"))
            transfer_page = window.page_stack.widget(window.page_key_to_index["transfer"])
            transfer_button_texts = [button.text() for button in transfer_page.findChildren(QPushButton)]
            self.assertIn("预览同步变更", transfer_button_texts)
            self.assertIsNotNone(window.sync_preview_table)
            self.assertIsNotNone(window.task_center_table)
            self.assertIsNotNone(window.runtime_result_text)
            self.assertIsNotNone(window.monitor_history_label)
            self.assertIsNotNone(window.device_overview_table)
            self.assertGreaterEqual(window.device_overview_table.rowCount(), 1)
            desktop_page = window.page_stack.widget(window.page_key_to_index["desktop"])
            desktop_button_texts = [button.text() for button in desktop_page.findChildren(QPushButton)]
            self.assertIn("终端安装 x11vnc", desktop_button_texts)
            self.assertIn("启动并连接", desktop_button_texts)
            self.assertIn("停止服务", desktop_button_texts)
            self.assertIsNotNone(window.remote_desktop_view)
            self.assertTrue(hasattr(window, "connect_remote_desktop"))
            self.assertTrue(hasattr(window, "install_remote_desktop_service_in_terminal"))
        finally:
            window._stop_resource_monitor()
            window.deleteLater()
            app.processEvents()

    def test_terminal_arrow_keys_send_remote_escape_sequences(self):
        try:
            from PyQt5.QtCore import QEvent, Qt
            from PyQt5.QtGui import QKeyEvent
            from PyQt5.QtWidgets import QApplication
            from ui.pages.terminal_page import TerminalOutput
        except Exception as exc:  # pragma: no cover - only used when Qt is unavailable.
            self.skipTest(str(exc))

        class StubWindow:
            def __init__(self):
                self.sent = []

            def terminal_send_text(self, text):
                self.sent.append(text)

        app = QApplication.instance() or QApplication([])
        stub = StubWindow()
        terminal = TerminalOutput(stub)
        try:
            terminal.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Up, Qt.NoModifier))
            terminal.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Down, Qt.NoModifier))
            self.assertEqual(stub.sent, ["\x1b[A", "\x1b[B"])
        finally:
            terminal.deleteLater()
            app.processEvents()


if __name__ == "__main__":
    unittest.main()
