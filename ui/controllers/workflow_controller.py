"""Project workflow and remote operations controller."""

from pathlib import Path

from PyQt5.QtWidgets import QFileDialog, QMessageBox, QTableWidgetItem

from services import remote_ops_service, ssh_service


class WorkflowControllerMixin:
    def _update_process_table(self, rows):
        if self.process_summary_label:
            self.process_summary_label.setText("共解析到 {} 个进程。".format(len(rows)))
        if self.process_table is None:
            return
        self.process_table.setRowCount(0)
        for row_index, row in enumerate(rows[:120]):
            self.process_table.insertRow(row_index)
            values = [row.get("pid", ""), row.get("cpu", ""), row.get("mem", ""), row.get("elapsed", ""), row.get("command", "")]
            for column, value in enumerate(values):
                self.process_table.setItem(row_index, column, QTableWidgetItem(value))
        self.process_table.resizeColumnsToContents()
        self.process_table.horizontalHeader().setStretchLastSection(True)

    def _update_files_table(self, data):
        rows = data.get("rows", [])
        path = data.get("path") or self.remote_file_path_edit.text().strip()
        if self.files_summary_label:
            self.files_summary_label.setText("{}: {} 项".format(path or "远端路径", len(rows)))
        if self.files_table is None:
            return
        self.files_table.setRowCount(0)
        for row_index, row in enumerate(rows[:300]):
            self.files_table.insertRow(row_index)
            values = [row.get("mode", ""), row.get("size", ""), row.get("modified", ""), row.get("name", "")]
            for column, value in enumerate(values):
                self.files_table.setItem(row_index, column, QTableWidgetItem(value))
        self.files_table.resizeColumnsToContents()
        self.files_table.horizontalHeader().setStretchLastSection(True)

    def _update_service_status_page(self, data):
        status = data.get("status", "unknown")
        status_text = data.get("status_text", "未检测")
        self._set_check_card(
            self.service_result_labels,
            "状态",
            status,
            status_text,
            data.get("active", "Active: 未检测"),
            data.get("details", ""),
        )

        loaded = data.get("loaded", "Loaded: 未检测")
        loaded_state = "ok" if "loaded" in loaded.lower() and "not-found" not in loaded.lower() else "unknown"
        self._set_check_card(
            self.service_result_labels,
            "加载",
            loaded_state,
            remote_ops_service.CHECK_STATUS_TEXT.get(loaded_state, "未检测"),
            loaded,
            data.get("details", ""),
        )

        pid = data.get("pid", "Main PID: 未检测")
        pid_state = "ok" if "未检测" not in pid and "n/a" not in pid.lower() else "unknown"
        self._set_check_card(
            self.service_result_labels,
            "进程",
            pid_state,
            remote_ops_service.CHECK_STATUS_TEXT.get(pid_state, "未检测"),
            pid,
            data.get("details", ""),
        )
        if self.service_status_text:
            detail = "\n".join([
                data.get("summary", ""),
                data.get("loaded", ""),
                data.get("active", ""),
                data.get("pid", ""),
            ]).strip()
            self.service_status_text.setPlainText(detail or data.get("details", ""))

    def _note_service_operation_complete(self, title):
        if self.service_status_text:
            self.service_status_text.setPlainText("{} 已完成。\n建议点击“状态”刷新当前服务状态。".format(title))

    def _current_project(self):
        return self._active_context()["project"]

    def _current_device(self):
        return self._active_context()["device"]

    def _remote_command_for_project(self, title, remote_command):
        remote = self._normalize_remote_text(self.remote_edit.text()) or self._current_device().get("ssh")
        return (
            title,
            ssh_service.remote_ssh_command(remote, remote_command, done_marker=True),
            self.paths.app_dir,
            {"done_marker": ssh_service.DONE_MARKER, "stop_on_done_marker": True},
        )

    def _project_sync_step(self):
        project = self._current_project()
        command = ssh_service.sync_command(
            self.paths.sync_script,
            self._normalize_remote_text(self.remote_edit.text()),
            project.get("remote_root", self.remote_path_edit.text().strip()),
            full=self.full_sync_check.isChecked(),
            dry_run=self.dry_run_check.isChecked(),
            no_delete=self.no_delete_check.isChecked(),
        )
        return ("同步到 Jetson", command, self.paths.project_dir)

    def _run_next_workflow_command(self):
        if not self.workflow_queue:
            return
        step = self.workflow_queue.pop(0)
        title, command, cwd = step[:3]
        options = step[3] if len(step) > 3 else {}
        self._run_command(title, command, cwd=cwd, **options)

    def _start_workflow(self, steps):
        if self.command_controller.is_running("short"):
            QMessageBox.warning(self, "命令正在运行", "请等待当前命令结束，或先点击“停止当前命令”。")
            return
        self.workflow_queue = list(steps)
        self._run_next_workflow_command()

    def workflow_sync(self):
        if not self.paths.sync_script.exists():
            QMessageBox.critical(self, "找不到脚本", "找不到 {}".format(self.paths.sync_script))
            return
        self._start_workflow([self._project_sync_step()])

    def workflow_build(self):
        project = self._current_project()
        build_command_text = str(project.get("build_command") or self.project_build_command_edit.text()).strip()
        if not build_command_text:
            QMessageBox.warning(self, "缺少构建命令", "请先在项目配置里填写构建命令。")
            return
        command = remote_ops_service.run_program_command(
            project.get("remote_root", self.remote_path_edit.text().strip()),
            build_command_text,
            background=False,
        )
        self._start_workflow([self._remote_command_for_project("项目构建", command)])

    def workflow_run(self):
        project = self._current_project()
        run_command_text = str(project.get("run_command") or self.run_command_edit.text()).strip()
        if not run_command_text:
            QMessageBox.warning(self, "缺少启动命令", "请先在项目配置或运行控制页填写启动命令。")
            return
        command = remote_ops_service.run_program_command(
            project.get("remote_root", self.remote_path_edit.text().strip()),
            run_command_text,
            background=True,
        )
        self._start_workflow([self._remote_command_for_project("项目后台运行", command)])

    def workflow_stop(self):
        pattern = self._current_project().get("stop_pattern", self.pkill_pattern_edit.text().strip())
        if not pattern:
            QMessageBox.warning(self, "缺少停止关键字", "请先在项目配置里填写停止关键字。")
            return
        answer = QMessageBox.question(
            self,
            "确认停止项目进程",
            "确定结束远端命令行匹配“{}”的进程？".format(pattern),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self._start_workflow([
            self._remote_command_for_project("停止项目进程", remote_ops_service.pkill_pattern_command(pattern))
        ])

    def workflow_logs(self):
        target = self._current_project().get("log_target", self.log_tail_target_combo.currentText())
        remote = self._normalize_remote_text(self.remote_edit.text()) or self._current_device().get("ssh")
        self._start_workflow([
            (
                "实时查看项目日志",
                ssh_service.remote_ssh_command(remote, remote_ops_service.tail_log_command(target, 120)),
                self.paths.app_dir,
                {"channel": "long"},
            )
        ])

    def workflow_sync_build_run(self):
        if not self.paths.sync_script.exists():
            QMessageBox.critical(self, "找不到脚本", "找不到 {}".format(self.paths.sync_script))
            return
        project = self._current_project()
        build_command_text = str(project.get("build_command") or self.project_build_command_edit.text()).strip()
        run_command_text = str(project.get("run_command") or self.run_command_edit.text()).strip()
        if not build_command_text:
            QMessageBox.warning(self, "缺少构建命令", "请先在项目配置里填写构建命令。")
            return
        if not run_command_text:
            QMessageBox.warning(self, "缺少启动命令", "请先在项目配置或运行控制页填写启动命令。")
            return
        build_command = remote_ops_service.run_program_command(
            project.get("remote_root", self.remote_path_edit.text().strip()),
            build_command_text,
            background=False,
        )
        run_command = remote_ops_service.run_program_command(
            project.get("remote_root", self.remote_path_edit.text().strip()),
            run_command_text,
            background=True,
        )
        steps = [
            self._project_sync_step(),
            self._remote_command_for_project("项目构建", build_command),
            self._remote_command_for_project("项目后台运行", run_command),
        ]
        self._start_workflow(steps)

    def run_remote_program(self):
        command = self.run_command_edit.text().strip()
        if not command:
            QMessageBox.warning(self, "缺少启动命令", "请填写要在远端执行的命令。")
            return
        remote_script = remote_ops_service.run_program_command(
            self.run_workdir_edit.text().strip(),
            command,
            self.run_background_check.isChecked(),
        )
        self._run_jetson_command(
            "运行远程程序",
            remote_script,
            long_running=not self.run_background_check.isChecked(),
        )

    def list_remote_processes(self):
        remote = self._remote_or_warn()
        if not remote:
            return
        if self.process_summary_label:
            self.process_summary_label.setText("正在刷新远端进程...")
        self._run_command(
            "刷新远程进程",
            ssh_service.remote_ssh_command(
                remote,
                remote_ops_service.process_list_command(self.process_filter_edit.text()),
                done_marker=True,
            ),
            cwd=self.paths.app_dir,
            done_marker=ssh_service.DONE_MARKER,
            stop_on_done_marker=True,
        )

    def kill_remote_pid(self):
        pid = self.kill_pid_edit.text().strip()
        if not pid:
            QMessageBox.warning(self, "缺少 PID", "请填写要结束的远程进程 PID。")
            return
        answer = QMessageBox.question(
            self,
            "确认结束进程",
            "确定向远端 PID {} 发送 TERM 信号？".format(pid),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self._run_jetson_command("结束远程进程", remote_ops_service.kill_pid_command(pid))

    def pkill_remote_pattern(self):
        pattern = self.pkill_pattern_edit.text().strip()
        if not pattern:
            QMessageBox.warning(self, "缺少关键字", "请填写要匹配的远程进程关键字。")
            return
        answer = QMessageBox.question(
            self,
            "确认按关键字结束进程",
            "确定结束远端命令行匹配“{}”的进程？".format(pattern),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self._run_jetson_command("按关键字结束远程进程", remote_ops_service.pkill_pattern_command(pattern))

    def tail_remote_log(self):
        self._run_jetson_command(
            "实时查看远程日志",
            remote_ops_service.tail_log_command(
                self.log_tail_target_combo.currentText(),
                self.log_tail_lines_spin.value(),
            ),
            long_running=True,
        )

    def run_network_diagnostics(self):
        remote = self._remote_or_warn()
        if not remote:
            return
        self._prepare_check_cards(self.network_result_labels, "正在诊断远端网络")
        if self.network_checks_text:
            self.network_checks_text.setPlainText("正在执行网络诊断...")
        self._run_command(
            "网络连通性诊断",
            ssh_service.remote_ssh_command(
                remote,
                remote_ops_service.network_diagnostics_command(
                    self.network_windows_ip_edit.text(),
                    self.network_proxy_port_edit.text(),
                ),
                done_marker=True,
            ),
            cwd=self.paths.app_dir,
            done_marker=ssh_service.DONE_MARKER,
            stop_on_done_marker=True,
        )

    def run_environment_check(self):
        remote = self._remote_or_warn()
        if not remote:
            return
        self._prepare_environment_cards("正在检查远端开发环境")
        self._run_command(
            "开发环境检查",
            ssh_service.remote_ssh_command(remote, remote_ops_service.environment_check_command(), done_marker=True),
            cwd=self.paths.app_dir,
            done_marker=ssh_service.DONE_MARKER,
            stop_on_done_marker=True,
        )

    def run_device_init_advice(self):
        remote = self._remote_or_warn()
        if not remote:
            return
        if self.environment_init_text:
            self.environment_init_text.setPlainText("正在检查远端初始化状态...")
        self._run_command(
            "设备初始化检查",
            ssh_service.remote_ssh_command(
                remote,
                remote_ops_service.device_init_advice_command(
                    self.network_windows_ip_edit.text() if self.network_windows_ip_edit else self.ip_combo.currentText(),
                    self.network_proxy_port_edit.text() if self.network_proxy_port_edit else self.port_spin.value(),
                ),
                done_marker=True,
            ),
            cwd=self.paths.app_dir,
            done_marker=ssh_service.DONE_MARKER,
            stop_on_done_marker=True,
        )

    def run_peripheral_check(self):
        remote = self._remote_or_warn()
        if not remote:
            return
        self._prepare_check_cards(self.peripheral_result_labels, "正在检测远端外设")
        self._run_command(
            "外设检测",
            ssh_service.remote_ssh_command(
                remote,
                remote_ops_service.peripheral_check_command(self.video_device_edit.text()),
                done_marker=True,
            ),
            cwd=self.paths.app_dir,
            done_marker=ssh_service.DONE_MARKER,
            stop_on_done_marker=True,
        )

    def list_remote_files(self):
        remote = self._remote_or_warn()
        if not remote:
            return
        if self.files_summary_label:
            self.files_summary_label.setText("正在列出远端路径...")
        self._run_command(
            "列出远程文件",
            ssh_service.remote_ssh_command(
                remote,
                remote_ops_service.file_list_command(self.remote_file_path_edit.text()),
                done_marker=True,
            ),
            cwd=self.paths.app_dir,
            done_marker=ssh_service.DONE_MARKER,
            stop_on_done_marker=True,
        )

    def apply_remote_path_bookmark(self):
        if self.remote_path_bookmark_combo is None or self.remote_file_path_edit is None:
            return
        path = self.remote_path_bookmark_combo.currentText().strip()
        if path:
            self.remote_file_path_edit.setText(path)

    def save_remote_path_bookmark(self):
        if not self.remote_file_path_edit:
            return
        remote_path = self.remote_file_path_edit.text().strip()
        if not remote_path:
            QMessageBox.warning(self, "缺少远端路径", "请先填写要收藏的远端路径。")
            return
        reason = remote_ops_service.remote_path_refusal_reason(remote_path)
        if reason:
            QMessageBox.warning(self, "远端路径不安全", "拒绝收藏该路径。\n\n{}\n{}".format(remote_path, reason))
            return
        project = self._current_project()
        if not project.get("id"):
            QMessageBox.warning(self, "缺少项目", "请先选择或保存一个项目。")
            return
        bookmarks = self._remote_path_bookmarks()
        if remote_path not in bookmarks:
            bookmarks.insert(0, remote_path)
        project_payload = dict(project)
        project_payload["file_bookmarks"] = bookmarks[:20]
        self.config_store.upsert_project(project_payload)
        self._refresh_remote_path_bookmarks()
        self._set_combo_text(self.remote_path_bookmark_combo, remote_path)
        self._append_log("已保存远端路径收藏: " + remote_path)

    def delete_remote_path_bookmark(self):
        if self.remote_path_bookmark_combo is None:
            return
        remote_path = self.remote_path_bookmark_combo.currentText().strip()
        if not remote_path:
            return
        project = self._current_project()
        explicit = [str(path).strip() for path in project.get("file_bookmarks", []) if str(path).strip()]
        if remote_path not in explicit:
            QMessageBox.information(self, "默认路径", "该路径来自项目默认值，不需要删除。")
            return
        bookmarks = [
            path for path in explicit
            if path != remote_path
        ]
        project_payload = dict(project)
        project_payload["file_bookmarks"] = bookmarks
        self.config_store.upsert_project(project_payload)
        self._refresh_remote_path_bookmarks()
        self._append_log("已删除远端路径收藏: " + remote_path)

    def mkdir_remote_path(self):
        remote_path = self.remote_file_path_edit.text().strip()
        if not remote_path:
            QMessageBox.warning(self, "缺少远端路径", "请填写要创建的远端目录。")
            return
        reason = remote_ops_service.remote_path_refusal_reason(remote_path)
        if reason:
            QMessageBox.warning(self, "远端路径不安全", "拒绝创建该路径。\n\n{}\n{}".format(remote_path, reason))
            return
        self._run_jetson_command("新建远程目录", remote_ops_service.mkdir_command(remote_path))

    def remove_remote_path(self):
        remote_path = self.remote_file_path_edit.text().strip()
        if not remote_path:
            QMessageBox.warning(self, "缺少远端路径", "请填写要删除的远端路径。")
            return
        reason = remote_ops_service.remote_path_refusal_reason(remote_path, destructive=True)
        if reason:
            QMessageBox.warning(self, "远端路径不安全", "拒绝删除该路径。\n\n{}\n{}".format(remote_path, reason))
            return
        answer = QMessageBox.question(
            self,
            "确认删除远端路径",
            "确定递归删除远端路径？\n\n{}".format(remote_path),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self._run_jetson_command("删除远端路径", remote_ops_service.remove_path_command(remote_path))

    def upload_single_file(self):
        remote = self._remote_or_warn()
        if not remote:
            return
        local_path = self.local_file_path_edit.text().strip()
        if not local_path or not Path(local_path).is_file():
            local_path, _ = QFileDialog.getOpenFileName(self, "选择要上传的文件", str(self.paths.app_dir))
            if not local_path:
                return
            self.local_file_path_edit.setText(local_path)
        remote_path = self.remote_file_path_edit.text().strip()
        if not remote_path:
            QMessageBox.warning(self, "缺少远端路径", "请填写上传目标远端路径。")
            return
        target = "{}:{}".format(remote, remote_path)
        self._run_command("上传单文件", ["scp", "-O", local_path, target], cwd=self.paths.app_dir)

    def download_single_file(self):
        remote = self._remote_or_warn()
        if not remote:
            return
        remote_path = self.remote_file_path_edit.text().strip()
        if not remote_path:
            QMessageBox.warning(self, "缺少远端路径", "请填写要下载的远端文件路径。")
            return
        local_path = self.local_file_path_edit.text().strip()
        if not local_path or not Path(local_path).exists():
            local_path = QFileDialog.getExistingDirectory(self, "选择本地保存目录", str(self.paths.app_dir))
            if not local_path:
                return
            self.local_file_path_edit.setText(local_path)
        source = "{}:{}".format(remote, remote_path)
        self._run_command("下载单文件", ["scp", "-O", source, local_path], cwd=self.paths.app_dir)

    def _service_action(self, action, confirm=False):
        service_name = self.service_name_edit.text().strip()
        if not service_name:
            QMessageBox.warning(self, "缺少服务名", "请填写 systemd 服务名。")
            return
        remote = self._remote_or_warn()
        if not remote:
            return
        if confirm:
            answer = QMessageBox.question(
                self,
                "确认服务操作",
                "确定对远端服务执行 {}？\n\n{}".format(action, service_name),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return
        if action == "status":
            self._prepare_check_cards(self.service_result_labels, "正在查询服务状态")
            if self.service_status_text:
                self.service_status_text.setPlainText("正在查询服务状态...")
        elif action in ("start", "stop", "restart") and self.service_status_text:
            self.service_status_text.setPlainText("正在执行服务操作: {}".format(action))
        self._run_command(
            "服务{}: {}".format(action, service_name),
            ssh_service.remote_ssh_command(
                remote,
                remote_ops_service.service_command(service_name, action),
                done_marker=action != "logs",
            ),
            cwd=self.paths.app_dir,
            channel="long" if action == "logs" else "short",
            done_marker=ssh_service.DONE_MARKER if action != "logs" else None,
            stop_on_done_marker=action != "logs",
        )

    def service_status(self):
        self._service_action("status")

    def service_start(self):
        self._service_action("start", confirm=True)

    def service_stop(self):
        self._service_action("stop", confirm=True)

    def service_restart(self):
        self._service_action("restart", confirm=True)

    def service_logs(self):
        self._service_action("logs")
