"""Build and consume the real wheel from a clean, offline test environment."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import venv


class WheelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.work = Path(cls.temporary.name)
        cls.repository = Path(__file__).resolve().parents[1]
        cls.environment = dict(os.environ)
        cls.environment.pop("PYTHONPATH", None)
        cls.environment["PIP_NO_INDEX"] = "1"
        cls.environment["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
        cls.invoke([sys.executable, "-m", "pip", "wheel", "--no-deps", "--no-build-isolation",
                    "--no-index", "--wheel-dir", str(cls.work / "wheels"), str(cls.repository)])
        wheel = list((cls.work / "wheels").glob("xgen_quality-*.whl"))
        if len(wheel) != 1:
            raise AssertionError(f"Expected one package wheel, got {wheel}")
        venv.create(cls.work / "venv", with_pip=True)
        cls.python = cls.work / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        cls.invoke([str(cls.python), "-m", "pip", "install", "--no-index", "--no-deps", str(wheel[0])])

    @classmethod
    def invoke(cls, arguments, expected=0):
        result = subprocess.run(arguments, cwd=cls.work, env=cls.environment,
                                capture_output=True, text=True, timeout=180)
        if result.returncode != expected:
            raise AssertionError(f"{arguments}\nexit={result.returncode}\n{result.stdout}\n{result.stderr}")
        return result

    def setUp(self):
        self.consumer = self.work / self.id().split(".")[-1] / "consumer with spaces"
        (self.consumer / "tools").mkdir(parents=True)
        self.config = {"schema_version": 1, "standard_version": "1.0.0", "quality_version": "0.1.0",
                       "public_headers": ["include/xgen/status"], "production_directories": ["src"]}
        (self.consumer / "tools/quality.json").write_text(json.dumps(self.config) + "\n", "utf-8", newline="")
        (self.consumer / "README.md").write_text("Installed consumer.\n", "utf-8", newline="")
        self.invoke(["git", "init", "-q", str(self.consumer)])

    def test_installed_module_runs_without_source_path_and_reports_wheel_hash(self):
        self.invoke([str(self.python), "-I", "-m", "xgen_quality", "--root", str(self.consumer), "text", "README.md"])
        report = json.loads((self.consumer / "out/reports/quality-text.json").read_text("utf-8"))
        self.assertEqual(report["quality_version"], "0.1.0")
        self.assertEqual(report["files"], ["README.md"])
        self.assertEqual(report["installation"]["version"], "0.1.0")
        digest = report["installation"]["direct_url"]["archive_info"]["hashes"]["sha256"]
        self.assertEqual(len(digest), 64)

    def test_installed_thin_launcher_uses_its_own_root(self):
        launcher = self.consumer / "tools/quality.py"
        launcher.write_text("from pathlib import Path\nfrom xgen_quality import main\n"
                            "raise SystemExit(main(root=Path(__file__).resolve().parents[1]))\n", "utf-8", newline="")
        self.invoke([str(self.python), "-I", str(launcher), "text", "README.md"])
        self.assertTrue((self.consumer / "out/reports/quality-text.json").is_file())

    def test_installed_consumer_version_mismatch_fails(self):
        self.config["quality_version"] = "9.0.0"
        (self.consumer / "tools/quality.json").write_text(json.dumps(self.config), "utf-8")
        result = self.invoke([str(self.python), "-I", "-m", "xgen_quality", "--root", str(self.consumer), "text"], expected=1)
        self.assertIn("quality_version", result.stderr)

    def test_wheel_contains_policy_and_controlled_templates(self):
        result = self.invoke([str(self.python), "-I", "-c",
                              "from importlib.resources import files; "
                              "r=files('xgen_quality'); "
                              "assert r.joinpath('policy.json').is_file(); "
                              "assert r.joinpath('templates/.clang-format').is_file(); "
                              "assert r.joinpath('templates/c-component-ci.yml').is_file()"])
        self.assertEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
