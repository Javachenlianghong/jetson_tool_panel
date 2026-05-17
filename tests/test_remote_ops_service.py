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
        self.assertIn("trtexec", command)
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
        self.assertIn("--loadEngine=", command)
        self.assertIn("--duration=10", command)


if __name__ == "__main__":
    unittest.main()
