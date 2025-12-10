import tempfile
from pathlib import Path
from unittest import TestCase, mock

import dev_tool


class DevToolCLITests(TestCase):
    def test_default_no_args_uses_menu_when_tty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            with mock.patch.object(dev_tool, "DEFAULT_BUILD_DIR", tmp_path), \
                mock.patch("dev_tool.detect_generator", return_value=None), \
                mock.patch("dev_tool.prompt_for_choice", return_value="quit"), \
                mock.patch("sys.stdin.isatty", return_value=True), \
                mock.patch("dev_tool.run_command") as run_cmd:
                result = dev_tool.main([])

            self.assertEqual(result, 0)
            run_cmd.assert_not_called()
            # build directory was injected; no configure/build called
            self.assertTrue(tmp_path.exists())

    def test_default_no_args_builds_when_noninteractive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            with mock.patch.object(dev_tool, "DEFAULT_BUILD_DIR", tmp_path), \
                mock.patch("dev_tool.detect_generator", return_value=None), \
                mock.patch("sys.stdin.isatty", return_value=False), \
                mock.patch("dev_tool.run_command") as run_cmd:
                result = dev_tool.main([])

            self.assertEqual(result, 0)
            # configure + build
            self.assertEqual(run_cmd.call_count, 2)
            self.assertTrue(tmp_path.exists())

    def test_run_without_target_prompts_and_executes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            fake_exe = tmp_path / "sample_cli.exe"
            fake_exe.touch()
            with mock.patch.object(dev_tool, "DEFAULT_BUILD_DIR", tmp_path), \
                mock.patch("dev_tool.detect_generator", return_value=None), \
                mock.patch("dev_tool.prompt_for_choice", return_value="sample_cli"), \
                mock.patch("dev_tool.list_runnable_targets", return_value=["sample_cli"]), \
                mock.patch("sys.stdin.isatty", return_value=True), \
                mock.patch("dev_tool.find_built_binary", return_value=fake_exe), \
                mock.patch("dev_tool.run_command") as run_cmd:
                result = dev_tool.main(["run"])

        self.assertEqual(result, 0)
        # configure + build + run
        self.assertEqual(run_cmd.call_count, 3)

    def test_verify_reports_missing(self) -> None:
        with mock.patch("dev_tool.shutil.which", return_value=None), \
            mock.patch("dev_tool.detect_generator", return_value=None), \
            mock.patch("dev_tool.resolve_qt_prefix", return_value=None):
            result = dev_tool.main(["verify"])
        self.assertEqual(result, 1)

    def test_verify_success(self) -> None:
        with mock.patch("dev_tool.shutil.which", return_value="/usr/bin/cmake"), \
            mock.patch("dev_tool.detect_generator", return_value="Ninja"), \
            mock.patch("dev_tool.resolve_qt_prefix", return_value=Path("/qt")):
            result = dev_tool.main(["verify"])
        self.assertEqual(result, 0)
