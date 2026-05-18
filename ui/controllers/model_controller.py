"""Model deployment UI controller."""

from PyQt5.QtWidgets import QApplication, QInputDialog, QMessageBox

from core.model_workers import RemoteModelScanWorker
from core.config_store import slugify
from services import remote_ops_service


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

    def _current_tensorrt_command(self):
        return remote_ops_service.tensorrt_command(
            self.model_workdir_edit.text(),
            self.model_source_edit.text(),
            self.model_output_edit.text(),
            self.model_precision_combo.currentText(),
        )

    def run_tensorrt_conversion(self):
        self._run_jetson_command("TensorRT 模型转换", self._current_tensorrt_command())

    def run_model_benchmark(self):
        output = self.model_output_edit.text().strip()
        if not output:
            QMessageBox.warning(self, "缺少模型输出文件", "请先填写 engine 或 rknn 输出文件。")
            return
        if output.lower().endswith(".rknn"):
            command = remote_ops_service.rknn_benchmark_template_command(
                self.model_workdir_edit.text(),
                output,
                self.model_test_image_edit.text(),
            )
            self._run_jetson_command("RKNN 运行模板", command)
            return
        command = remote_ops_service.tensorrt_benchmark_command(
            self.model_workdir_edit.text(),
            output,
        )
        self._run_jetson_command("TensorRT Benchmark", command)

    def show_rknn_template(self):
        self._run_jetson_command(
            "显示 RKNN 部署模板",
            remote_ops_service.rknn_template_command(
                self.model_workdir_edit.text(),
                self.model_source_edit.text(),
                self.model_output_edit.text(),
            ),
        )

    def copy_model_command(self):
        command = self._current_tensorrt_command()
        QApplication.clipboard().setText(command)
        self._append_log("已复制 TensorRT 命令模板: " + command)

    def _current_model_profile_id(self):
        return self._combo_current_data(self.model_profile_combo)

    def _model_profile_from_form(self):
        name = self.model_name_edit.text().strip() if self.model_name_edit else "Model"
        profile_id = self._current_model_profile_id() or slugify(name, "model")
        return {
            "id": profile_id,
            "name": name,
            "source": self.model_source_edit.text().strip(),
            "output": self.model_output_edit.text().strip(),
            "precision": self.model_precision_combo.currentText().strip(),
            "test_image": self.model_test_image_edit.text().strip(),
        }

    def save_model_profile(self):
        project = self._current_project()
        if not project.get("id"):
            QMessageBox.warning(self, "缺少项目", "请先选择或保存一个项目。")
            return
        profile = self._model_profile_from_form()
        if not profile["name"]:
            QMessageBox.warning(self, "缺少模型名称", "请填写模型名称。")
            return
        profile_id = self.config_store.upsert_model_profile(project["id"], profile)
        self._refresh_config_selectors()
        self._apply_active_context_to_forms()
        self._set_combo_by_data(self.model_profile_combo, profile_id)
        self._append_log("已保存模型配置: " + profile["name"])

    def load_model_profile(self):
        project = self._current_project()
        profile_id = self._current_model_profile_id()
        profile = None
        for item in project.get("model_profiles", []):
            if item.get("id") == profile_id:
                profile = item
                break
        if not profile:
            QMessageBox.warning(self, "找不到模型配置", "请选择要加载的模型配置。")
            return
        self.model_name_edit.setText(profile.get("name", ""))
        self.model_source_edit.setText(profile.get("source", ""))
        self.model_output_edit.setText(profile.get("output", ""))
        self.model_test_image_edit.setText(profile.get("test_image", ""))
        self._set_combo_text(self.model_precision_combo, profile.get("precision", "fp16"))

    def delete_model_profile(self):
        project = self._current_project()
        profile_id = self._current_model_profile_id()
        if not project.get("id") or not profile_id:
            return
        answer = QMessageBox.question(
            self,
            "确认删除模型配置",
            "确定删除当前模型配置？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self.config_store.delete_model_profile(project["id"], profile_id)
        self._apply_active_context_to_forms()
        self._append_log("已删除模型配置。")

    def _refresh_device_profile_combo(self):
        if self.device_profile_combo is None:
            return
        current = self.device_profile_combo.currentText()
        self.device_profile_combo.clear()
        for device in self.config_store.devices():
            self.device_profile_combo.addItem(device.get("name", device.get("id")), device.get("id"))
        if current:
            index = self.device_profile_combo.findText(current)
            if index >= 0:
                self.device_profile_combo.setCurrentIndex(index)

    def fill_device_profile_from_current(self):
        self.device_remote_edit.setText(self._normalize_remote_text(self.remote_edit.text()))
        self.device_remote_path_edit.setText(self.remote_path_edit.text().strip())
        self.device_local_root_edit.setText(self.local_root_edit.text().strip())
        name = self._normalize_remote_text(self.remote_edit.text()).split("@")[-1] or "设备"
        self.device_name_edit.setText(name)

    def save_device_profile(self):
        name = self.device_name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "缺少名称", "请填写设备档案名称。")
            return
        device_id = slugify(name, "device")
        self.config_store.upsert_device({
            "id": device_id,
            "name": name,
            "type": "linux",
            "ssh": self.device_remote_edit.text().strip(),
            "proxy_host": self.ip_combo.currentText().strip(),
            "proxy_port": self.port_spin.value(),
        })
        current_project = self._current_project()
        project_payload = dict(current_project)
        project_payload.update({
            "device_id": device_id,
            "local_root": self.device_local_root_edit.text().strip(),
            "remote_root": self.device_remote_path_edit.text().strip(),
        })
        self.config_store.upsert_project(project_payload)
        self._refresh_config_selectors()
        self._refresh_device_profile_combo()
        self._apply_active_context_to_forms()
        self._append_log("已保存设备档案: " + name)

    def load_device_profile(self):
        device_id = self._combo_current_data(self.device_profile_combo)
        device = self.config_store.get_device(device_id)
        if not device:
            QMessageBox.warning(self, "找不到档案", "请选择要加载的设备档案。")
            return
        self.config_store.set_active_device(device_id)
        self._refresh_config_selectors()
        self._apply_active_context_to_forms()
        self._append_log("已加载设备档案: " + device.get("name", device_id))

    def delete_device_profile(self):
        device_id = self._combo_current_data(self.device_profile_combo)
        device = self.config_store.get_device(device_id)
        if not device:
            return
        answer = QMessageBox.question(
            self,
            "确认删除档案",
            "确定删除设备档案及其关联项目？\n\n{}".format(device.get("name", device_id)),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self.config_store.delete_device(device_id)
        self._refresh_config_selectors()
        self._refresh_device_profile_combo()
        self._apply_active_context_to_forms()
        self._append_log("已删除设备档案: " + device.get("name", device_id))

    def fill_project_config_from_current(self):
        context = self._active_context()
        project = context["project"]
        self.project_id_edit.setText(project.get("id", "project"))
        self.project_name_edit.setText(project.get("name", "Project"))
        self.project_local_root_edit.setText(self.local_root_edit.text().strip())
        self.project_remote_root_edit.setText(self.remote_path_edit.text().strip())
        self.project_build_command_edit.setText(project.get("build_command", "cmake --build build -j4"))
        self.project_run_command_edit.setText(self.run_command_edit.text().strip())
        self.project_stop_pattern_edit.setText(self.pkill_pattern_edit.text().strip())
        self.project_log_target_edit.setText(self.log_tail_target_combo.currentText().strip())

    def load_project_config_to_form(self):
        self._load_project_config_to_form(self._current_project())

    def save_project_config(self):
        name = self.project_name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "缺少项目名称", "请填写项目名称。")
            return
        project_id = self.project_id_edit.text().strip() or slugify(name, "project")
        device_id = self._current_device().get("id") or self._combo_current_data(self.active_device_combo)
        self.config_store.upsert_project({
            "id": project_id,
            "device_id": device_id,
            "name": name,
            "local_root": self.project_local_root_edit.text().strip(),
            "remote_root": self.project_remote_root_edit.text().strip(),
            "build_command": self.project_build_command_edit.text().strip(),
            "run_command": self.project_run_command_edit.text().strip(),
            "stop_pattern": self.project_stop_pattern_edit.text().strip(),
            "log_target": self.project_log_target_edit.text().strip(),
            "model_profiles": self._current_project().get("model_profiles", []),
        })
        self._refresh_config_selectors()
        self._set_combo_by_data(self.active_project_combo, project_id)
        self.config_store.set_active_project(project_id)
        self._apply_active_context_to_forms()
        self._append_log("已保存项目配置: " + name)

    def delete_project_config(self):
        project = self._current_project()
        project_id = project.get("id")
        if not project_id:
            return
        answer = QMessageBox.question(
            self,
            "确认删除项目",
            "确定删除项目配置？\n\n{}".format(project.get("name", project_id)),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self.config_store.delete_project(project_id)
        self._refresh_config_selectors()
        self._apply_active_context_to_forms()
        self._append_log("已删除项目配置: " + project.get("name", project_id))
