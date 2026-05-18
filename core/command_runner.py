"""Background command runner and shell quoting helpers."""

import locale
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


def decode_process_output(raw_line):
    if isinstance(raw_line, str):
        return raw_line.rstrip("\r\n")

    encodings = ["utf-8", locale.getpreferredencoding(False), "gb18030"]
    if os.name == "nt":
        encodings.append("mbcs")

    tried = set()
    for encoding in encodings:
        if not encoding:
            continue
        key = encoding.lower()
        if key in tried:
            continue
        tried.add(key)
        try:
            return raw_line.decode(encoding).rstrip("\r\n")
        except (LookupError, UnicodeDecodeError):
            pass

    return raw_line.decode("utf-8", errors="replace").rstrip("\r\n")


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
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=0,
                creationflags=creationflags,
            )
        except Exception as exc:
            self.failed_to_start.emit(str(exc))
            return

        assert self._process.stdout is not None
        for line in self._process.stdout:
            self.output.emit(decode_process_output(line))

        return_code = self._process.wait()
        self.finished_ok.emit(return_code)

    def terminate_process(self, kill_after_seconds=2):
        if self._process and self._process.poll() is None:
            try:
                self._process.terminate()
                self._process.wait(timeout=kill_after_seconds)
            except subprocess.TimeoutExpired:
                self._process.kill()
                try:
                    self._process.wait(timeout=kill_after_seconds)
                except subprocess.TimeoutExpired:
                    pass
            except OSError:
                pass
