import unittest

from services import remote_ops_service


class RemoteOpsServiceTest(unittest.TestCase):
    def test_run_program_background_quotes_command(self):
        command = remote_ops_service.run_program_command("/tmp/my project", "python3 app.py --name 'demo'", True)
        self.assertIn("nohup", command)
        self.assertIn("/tmp/my project", command)
        self.assertIn("python3 app.py", command)

    def test_tensorrt_command_uses_precision_flag(self):
        command = remote_ops_service.tensorrt_command("/tmp", "model.onnx", "model.engine", "fp16")
        self.assertIn("trtexec_bin", command)
        self.assertIn("/usr/src/tensorrt/bin/trtexec", command)
        self.assertIn('"$trtexec_bin"', command)
        self.assertIn("--fp16", command)
        self.assertIn("--onnx=model.onnx", command)

    def test_file_remove_refuses_unsafe_paths(self):
        command = remote_ops_service.remove_path_command("/")
        self.assertIn("Refuse to remove unsafe path", command)
        self.assertNotIn("rm -rf", command)

    def test_file_remove_requires_absolute_non_root_path(self):
        for unsafe_path in ("~", "$HOME", "/home", "/tmp", "//", "/home/jetson/..", "relative/path"):
            with self.subTest(path=unsafe_path):
                command = remote_ops_service.remove_path_command(unsafe_path)
                self.assertIn("Refuse to remove unsafe path", command)
                self.assertNotIn("rm -rf", command)

        command = remote_ops_service.remove_path_command("/home/jetson/project/build")
        self.assertIn("rm -rf", command)
        self.assertIn("/home/jetson/project/build", command)

    def test_mkdir_refuses_empty_and_system_roots(self):
        command = remote_ops_service.mkdir_command("/home")
        self.assertIn("Refuse to create unsafe path", command)
        self.assertNotIn("mkdir -p", command)

    def test_rknn_template_quotes_user_paths(self):
        command = remote_ops_service.rknn_template_command(
            "/tmp/demo",
            "models/source model's.onnx",
            "output; rm -rf /.rknn",
        )
        self.assertIn("model_path=", command)
        self.assertIn("output_path=", command)
        self.assertIn("printf 'Input model: %s", command)
        self.assertNotIn('echo "Input model: models/source', command)

    def test_device_init_advice_is_read_only(self):
        command = remote_ops_service.device_init_advice_command("192.168.1.11", 7897)
        self.assertIn("Device initialization checklist", command)
        self.assertIn("Suggested install commands", command)
        self.assertIn("cat <<'EOF'", command)

    def test_tensorrt_benchmark_loads_existing_engine(self):
        command = remote_ops_service.tensorrt_benchmark_command("/tmp/demo", "model.engine")
        self.assertIn("trtexec_bin", command)
        self.assertIn("--loadEngine=", command)
        self.assertIn("--duration=10", command)

    def test_suggest_engine_output_name_includes_precision(self):
        self.assertEqual(
            remote_ops_service.suggest_engine_output_name("models/yolov8n.onnx", "fp16"),
            "yolov8n-fp16.engine",
        )
        self.assertEqual(
            remote_ops_service.suggest_engine_output_name("models/yolov8n.onnx", "fp32"),
            "yolov8n.engine",
        )

    def test_model_validate_command_checks_input_and_output(self):
        command = remote_ops_service.model_validate_command("/project", "models/a.onnx", "models/a.engine", "test.jpg")
        self.assertIn("Model validation", command)
        self.assertIn("input model not found", command)
        self.assertIn("output directory is not writable", command)

    def test_parse_tensorrt_output_extracts_metrics_and_warnings(self):
        result = remote_ops_service.parse_tensorrt_output([
            "[I] Throughput: 22.5 qps",
            "[I] Latency: min = 1.1 ms, max = 2.2 ms, mean = 1.5 ms",
            "[W] Some tactics do not have sufficient workspace memory to run.",
        ])
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["metrics"]["throughput"], "22.5 qps")
        self.assertIn("workspace", result["summary"])

    def test_diagnose_command_output_returns_actionable_display_hint(self):
        hints = remote_ops_service.diagnose_command_output(["Gtk-WARNING **: cannot open display:"])
        self.assertTrue(any("DISPLAY" in hint for hint in hints))

    def test_parse_environment_check_output_groups_statuses(self):
        output = [
            "Environment check",
            "== OS ==",
            "Ubuntu 22.04",
            "== Python ==",
            "Python 3.10.12",
            "pip 23.0",
            "== OpenCV Python ==",
            "不可用",
            "== Jetson ==",
            "nv_tegra_release 不存在",
            "tegrastats 不存在",
            "TensorRT Python 不可用",
            "== Common libraries ==",
            "numpy: 1.26.0",
            "torch: 不可用 (No module named torch)",
        ]
        result = remote_ops_service.parse_environment_check_output(output)
        by_title = {item["title"]: item for item in result["items"]}

        self.assertEqual(by_title["OS"]["status"], "ok")
        self.assertEqual(by_title["Python"]["status"], "ok")
        self.assertEqual(by_title["OpenCV Python"]["status"], "warning")
        self.assertEqual(by_title["Jetson"]["status"], "unknown")
        self.assertEqual(by_title["Common libraries"]["status"], "warning")

    def test_parse_device_init_advice_output_keeps_actionable_sections(self):
        output = [
            "Device initialization checklist",
            "== System identity ==",
            "jetson",
            "== Network and proxy ==",
            "Suggested temporary proxy:",
            "  export http_proxy=http://192.168.1.11:7897",
            "== Required tools ==",
            "[OK] git -> /usr/bin/git",
            "[MISS] cmake",
            "== Suggested install commands ==",
            "sudo apt update",
            "sudo apt install -y git cmake",
        ]
        summary = remote_ops_service.parse_device_init_advice_output(output)

        self.assertIn("Network and proxy", summary)
        self.assertIn("[MISS] cmake", summary)
        self.assertIn("sudo apt install", summary)

    def test_parse_network_diagnostics_output_groups_checks(self):
        output = [
            "== IP addresses ==",
            "eth0 192.168.1.20/24",
            "== Ping public IP 8.8.8.8 ==",
            "[OK] Ping public IP 8.8.8.8",
            "== DNS github.com ==",
            "[OK] DNS github.com",
            "== Ping github.com ==",
            "[FAIL] Ping github.com",
            "== Windows proxy port ==",
            "[OK] Windows proxy port",
            "== pip config ==",
            "global.index-url='https://pypi.org/simple'",
        ]
        result = remote_ops_service.parse_network_diagnostics_output(output)
        by_title = {item["title"]: item for item in result["groups"]}

        self.assertEqual(by_title["远端地址"]["status"], "ok")
        self.assertEqual(by_title["公网连通"]["status"], "ok")
        self.assertEqual(by_title["DNS / GitHub"]["status"], "error")
        self.assertEqual(by_title["Windows 代理"]["status"], "ok")

    def test_parse_peripheral_check_output_marks_missing_devices(self):
        output = [
            "== USB ==",
            "Bus 001 Device 001: ID 1d6b:0002",
            "== Video devices ==",
            "未发现 /dev/video*",
            "== Storage ==",
            "sda 100G",
        ]
        result = remote_ops_service.parse_peripheral_check_output(output)
        by_title = {item["title"]: item for item in result["items"]}

        self.assertEqual(by_title["USB"]["status"], "ok")
        self.assertEqual(by_title["摄像头"]["status"], "warning")
        self.assertEqual(by_title["磁盘"]["status"], "ok")

    def test_parse_process_and_file_tables(self):
        processes = remote_ops_service.parse_process_list_output([
            "PID   PPID  CPU  MEM  ELAPSED   COMMAND",
            "123   1     9.5  3.2  01:02     python3 detect.py --arg",
        ])
        self.assertEqual(processes[0]["pid"], "123")
        self.assertEqual(processes[0]["command"], "python3 detect.py --arg")

        files = remote_ops_service.parse_file_list_output([
            "Listing: /home/jetson",
            "total 4",
            "drwxr-xr-x 2 jetson jetson 4.0K May 18 10:20 project",
            "-rw-r--r-- 1 jetson jetson 12 May 18 10:21 run.log",
        ])
        self.assertEqual(files["path"], "/home/jetson")
        self.assertEqual(files["rows"][0]["name"], "project")
        self.assertEqual(files["rows"][1]["size"], "12")

    def test_parse_service_status_output(self):
        result = remote_ops_service.parse_service_status_output([
            "● demo.service - Demo",
            "     Loaded: loaded (/etc/systemd/system/demo.service; enabled)",
            "     Active: active (running) since Mon 2026-05-18 10:00:00 CST;",
            "   Main PID: 1234 (demo)",
        ])
        self.assertEqual(result["status"], "ok")
        self.assertIn("active (running)", result["active"])
        self.assertIn("Main PID", result["pid"])


if __name__ == "__main__":
    unittest.main()
