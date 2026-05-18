import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class UiSmokeTest(unittest.TestCase):
    def test_main_window_contains_terminal_and_double_pane_files(self):
        try:
            from PyQt5.QtCore import Qt
            from PyQt5.QtWidgets import QApplication
            from ui.main_window import JetsonControlPanel
        except Exception as exc:  # pragma: no cover - only used when Qt is unavailable.
            self.skipTest(str(exc))

        app = QApplication.instance() or QApplication([])
        window = JetsonControlPanel()
        try:
            self.assertIn("terminal", window.page_key_to_index)
            self.assertIsNotNone(window.terminal_output_edit)
            self.assertIsNotNone(window.local_files_table)
            self.assertIsNotNone(window.remote_files_table)
            self.assertIsNotNone(window.transfer_progress_bar)
            self.assertEqual(window.local_files_table.contextMenuPolicy(), Qt.CustomContextMenu)
            self.assertEqual(window.remote_files_table.contextMenuPolicy(), Qt.CustomContextMenu)
            self.assertTrue(hasattr(window, "remote_open_selected_path"))
        finally:
            window.deleteLater()
            app.processEvents()


if __name__ == "__main__":
    unittest.main()
