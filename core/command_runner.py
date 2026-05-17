"""Background command runner and shell quoting helpers."""

import os
import subprocess

from PyQt5.QtCore import QThread, pyqtSignal


def quote_for_powershell(value):
    return "'" + value.replace("'", "''") + "'"


def quote_for_bash(value):
    return "'" + value.replace("'", "'\"'\"'") + "'"


def format_command(command):
    if os.name == "nt":
        return subprocess.list2cmdline(command)
    return " ".join(quote_for_bash(part) for part in command)


class CommandWorker(QThread):
    output = pyqtSignal(str)
    finished_ok = pyqtSignal(int)
    failed_to_start = pyqtSignal(str)

    def __init__(self, command, cwd=None, parent=None):
        super().__init__(parent)
        self.command = command
        self.cwd = str(cwd) if cwd else None
        self._process = None

    def run(self):
        creationflags = 0
        if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW"):
            creationflags = subprocess.CREATE_NO_WINDOW

        try:
            self._process = subprocess.Popen(
                self.command,
                cwd=self.cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1,
                creationflags=creationflags,
            )
        except Exception as exc:
            self.failed_to_start.emit(str(exc))
            return

        assert self._process.stdout is not None
        for line in self._process.stdout:
            self.output.emit(line.rstrip("\r\n"))

        return_code = self._process.wait()
        self.finished_ok.emit(return_code)

    def terminate_process(self):
        if self._process and self._process.poll() is None:
            self._process.terminate()
