"""Channel-aware command execution controller."""

from dataclasses import dataclass, field
from datetime import datetime

from PyQt5.QtCore import QObject, QTimer, pyqtSignal

from core.command_runner import CommandWorker


@dataclass
class CommandRunState:
    title: str
    command: list
    cwd: object = None
    timeout_seconds: int = None
    done_marker: str = ""
    stop_on_done_marker: bool = False
    started_at: datetime = field(default_factory=datetime.now)
    output: list = field(default_factory=list)
    timed_out: bool = False
    worker: CommandWorker = None
    timer: QTimer = None


class CommandController(QObject):
    started = pyqtSignal(str)
    output = pyqtSignal(str, str)
    timed_out = pyqtSignal(str)
    failed_to_start = pyqtSignal(str, str)
    finished = pyqtSignal(str, int, bool)

    def __init__(self, parent=None, worker_class=CommandWorker):
        super().__init__(parent)
        self.worker_class = worker_class
        self._runs = {}

    def is_running(self, channel=None):
        if channel is not None:
            state = self._runs.get(channel)
            return bool(state and state.worker and state.worker.isRunning())
        return any(self.is_running(item) for item in list(self._runs))

    def state(self, channel):
        return self._runs.get(channel)

    def title(self, channel):
        state = self.state(channel)
        return state.title if state else ""

    def output_lines(self, channel):
        state = self.state(channel)
        return list(state.output) if state else []

    def started_at(self, channel):
        state = self.state(channel)
        return state.started_at if state else None

    def start(
        self,
        channel,
        title,
        command,
        cwd=None,
        timeout_seconds=None,
        done_marker=None,
        stop_on_done_marker=False,
    ):
        if self.is_running(channel):
            return False

        worker = self.worker_class(
            command,
            cwd=cwd,
            done_marker=done_marker,
            stop_on_done_marker=stop_on_done_marker,
            parent=self,
        )
        state = CommandRunState(
            title=title,
            command=list(command),
            cwd=cwd,
            timeout_seconds=timeout_seconds,
            done_marker=done_marker or "",
            stop_on_done_marker=stop_on_done_marker,
            worker=worker,
        )
        self._runs[channel] = state

        worker.output.connect(lambda line, watched=channel: self._handle_output(watched, line))
        worker.failed_to_start.connect(lambda error, watched=channel: self._handle_failed_to_start(watched, error))
        worker.finished_ok.connect(lambda return_code, watched=channel: self._handle_finished(watched, return_code))

        if timeout_seconds:
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(lambda watched=channel: self._handle_timeout(watched))
            state.timer = timer
            timer.start(max(int(timeout_seconds), 1) * 1000)

        worker.start()
        self.started.emit(channel)
        return True

    def stop(self, channel=None):
        channels = [channel] if channel else list(self._runs)
        stopped = False
        for item in channels:
            state = self._runs.get(item)
            if state and state.worker and state.worker.isRunning():
                state.worker.terminate_process()
                state.worker.wait(3000)
                stopped = True
        return stopped

    def _handle_output(self, channel, line):
        state = self._runs.get(channel)
        if state:
            state.output.append(line)
        self.output.emit(channel, line)

    def _handle_timeout(self, channel):
        state = self._runs.get(channel)
        if not state or not state.worker or not state.worker.isRunning():
            return
        state.timed_out = True
        self.timed_out.emit(channel)
        state.worker.terminate_process()

    def _handle_failed_to_start(self, channel, error):
        state = self._runs.get(channel)
        if state and state.timer:
            state.timer.stop()
        self.failed_to_start.emit(channel, error)
        self._runs.pop(channel, None)

    def _handle_finished(self, channel, return_code):
        state = self._runs.get(channel)
        timed_out = bool(state and state.timed_out)
        if state and state.timer:
            state.timer.stop()
        self.finished.emit(channel, int(return_code), timed_out)
        self._runs.pop(channel, None)
