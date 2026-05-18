"""Model deployment UI controller."""

from PyQt5.QtWidgets import QInputDialog, QMessageBox

from core.model_workers import RemoteModelScanWorker


class ModelControllerMixin:
    def _set_model_scan_running(self, running):
        if self.model_choose_source_button is not None:
            self.model_choose_source_button.setText("取消" if running else "选择")
            self.model_choose_source_button.setEnabled(True)

    def _start_model_scan(self, password=None):
        remote = self._remote_or_warn()
        if not remote:
            return
        workdir = self.model_workdir_edit.text().strip() if self.model_workdir_edit else ""
        workdir = workdir or "."
        self.pending_model_scan_password = None
        self.model_scan_worker = RemoteModelScanWorker(
            remote,
            workdir,
            password=password if password is not None else (self.sftp_password or self.terminal_password),
            timeout_seconds=20,
            parent=self,
        )
        self.model_scan_worker.message.connect(self._model_scan_message)
        self.model_scan_worker.candidates_ready.connect(self._model_scan_candidates_ready)
        self.model_scan_worker.auth_failed.connect(self._model_scan_auth_failed)
        self.model_scan_worker.failed.connect(self._model_scan_failed)
        self.model_scan_worker.finished.connect(self._model_scan_finished)
        self._set_model_scan_running(True)
        self._append_log("开始扫描远端模型文件: " + workdir)
        self.model_scan_worker.start()

    def choose_model_source_file(self):
        if self.model_scan_worker and self.model_scan_worker.isRunning():
            self.model_scan_worker.cancel()
            self._append_log("已请求取消模型文件扫描。")
            return
        self._start_model_scan()

    def _model_scan_message(self, message):
        self._append_log(message)

    def _model_scan_auth_failed(self, error):
        worker = self.model_scan_worker
        if worker and worker.password:
            QMessageBox.warning(self, "选择模型失败", error)
            return
        password = self._prompt_ssh_password("SFTP 认证")
        if password is None:
            self._append_log("模型文件扫描认证已取消。")
            return
        self.sftp_password = password
        self.pending_model_scan_password = password

    def _model_scan_failed(self, error):
        QMessageBox.warning(self, "选择模型失败", str(error))

    def _model_scan_candidates_ready(self, candidates):
        if not candidates:
            QMessageBox.information(
                self,
                "未找到模型文件",
                "在远程目录 {} 下未找到 .onnx、.engine、.rknn、.pt、.pth 或 .tflite 文件。".format(
                    self.model_workdir_edit.text().strip() or "."
                ),
            )
            return
        selected, ok = QInputDialog.getItem(
            self,
            "选择输入模型",
            "远端模型文件",
            candidates,
            0,
            False,
        )
        if ok and selected:
            self.model_source_edit.setText(selected)
            self._append_log("已选择输入模型: " + selected)

    def _model_scan_finished(self):
        self.model_scan_worker = None
        if self.pending_model_scan_password is not None:
            password = self.pending_model_scan_password
            self.pending_model_scan_password = None
            self._start_model_scan(password=password)
            return
        self._set_model_scan_running(False)
