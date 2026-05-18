"""Diagnostic report and display control helpers."""

from datetime import datetime
from pathlib import Path

from PyQt5.QtWidgets import QFileDialog, QMessageBox

from services import display_service, remote_ops_service


class ReportDisplayControllerMixin:
    def choose_report_dir(self):
        path = QFileDialog.getExistingDirectory(self, "选择诊断报告保存目录", self.report_dir_edit.text())
        if path:
            self.report_dir_edit.setText(path)

    def generate_diagnostic_report(self):
        command = remote_ops_service.diagnostic_report_command(
            self.network_windows_ip_edit.text(),
            self.network_proxy_port_edit.text(),
            self.video_device_edit.text(),
        )
        self._run_jetson_command("生成诊断报告", command)

    def _save_diagnostic_report(self):
        report_dir = Path(self.report_dir_edit.text().strip() or (self.paths.tool_dir / "reports"))
        report_dir.mkdir(parents=True, exist_ok=True)
        remote = self._normalize_remote_text(self.remote_edit.text())
        safe_remote = remote.replace("@", "_").replace(":", "_").replace("/", "_")
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        report_path = report_dir / "diagnostic-{}-{}.md".format(safe_remote or "device", timestamp)
        body = "\n".join(self.current_command_output)
        header = [
            "# Jetson Tool Panel 诊断报告",
            "",
            "- Remote: {}".format(remote),
            "- Windows IP: {}".format(self.ip_combo.currentText().strip()),
            "- Proxy Port: {}".format(self.port_spin.value()),
            "- Generated: {}".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            "",
            "```text",
            body,
            "```",
            "",
        ]
        report_path.write_text("\n".join(header), encoding="utf-8")
        self._append_log("诊断报告已保存: " + str(report_path))

    def query_jetson_displays(self):
        command = display_service.query_display_command(
            self.display_env_edit.text().strip(),
            self.xauthority_edit.text().strip(),
        )
        self._run_jetson_command("查询 Jetson 显示器", command)

    def set_jetson_resolution(self):
        output = self.display_output_combo.currentText().strip() if self.display_output_combo is not None else "auto"
        mode = self.resolution_combo.currentText().strip() if self.resolution_combo is not None else "1920x1080"
        rate = self.refresh_rate_spin.value() if self.refresh_rate_spin else 0
        framebuffer_fallback = (
            self.framebuffer_fallback_check.isChecked()
            if self.framebuffer_fallback_check
            else True
        )

        if not mode or "x" not in mode.lower():
            QMessageBox.warning(self, "分辨率格式不正确", "请填写类似 1920x1080 的分辨率。")
            return

        remote_script = display_service.set_resolution_command(
            self.display_env_edit.text().strip(),
            self.xauthority_edit.text().strip(),
            output,
            mode,
            rate,
            framebuffer_fallback,
        )
        self._run_jetson_command("设置 Jetson 分辨率", remote_script)

    def auto_jetson_display(self):
        output = self.display_output_combo.currentText().strip() if self.display_output_combo is not None else "auto"
        framebuffer_fallback = (
            self.framebuffer_fallback_check.isChecked()
            if self.framebuffer_fallback_check
            else True
        )
        remote_script = display_service.auto_display_command(
            self.display_env_edit.text().strip(),
            self.xauthority_edit.text().strip(),
            output,
            framebuffer_fallback,
        )
        self._run_jetson_command("恢复 Jetson 显示自动模式", remote_script)
