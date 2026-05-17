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
        self.assertIn("rm -rf", command)


if __name__ == "__main__":
    unittest.main()
