"""Consumer contracts for explicitly rooted, versioned shared checks."""

import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import xgen_quality
from xgen_quality import runner as quality


class ConsumerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve() / "consumer with spaces"
        (self.root / "tools").mkdir(parents=True)
        self.config = {"schema_version": 1, "standard_version": "1.0.0",
                       "quality_version": "0.1.0", "public_headers": ["include/xgen/bytes"],
                       "production_directories": ["src"]}
        self.save_config()

    def save_config(self):
        (self.root / "tools/quality.json").write_text(json.dumps(self.config) + "\n", "utf-8", newline="")

    def test_minimal_consumer_uses_shared_tool_policy(self):
        runner = quality.Runner(self.root)
        self.assertEqual(runner.config["tools"]["clang_format"]["version"], "19.1.5")
        self.assertEqual(runner.config["coverage"], {"line": 80, "branch": 80, "function": 80})
        self.assertEqual(runner.report["quality_version"], xgen_quality.__version__)
        self.assertEqual(runner.report["policy"]["source"], "xgen_quality/policy.json")
        self.assertEqual(len(runner.report["policy"]["sha256"]), 64)

    def test_missing_configuration_is_an_explicit_failure(self):
        (self.root / "tools/quality.json").unlink()
        with self.assertRaisesRegex(quality.QualityError, "tools/quality.json"):
            quality.Runner(self.root)

    def test_rejects_mismatching_quality_version(self):
        self.config["quality_version"] = "9.0.0"
        self.save_config()
        with self.assertRaisesRegex(quality.QualityError, "quality_version"):
            quality.Runner(self.root)

    def test_rejects_mismatching_standard_version(self):
        self.config["standard_version"] = "9.0.0"
        self.save_config()
        with self.assertRaisesRegex(quality.QualityError, "standard_version"):
            quality.Runner(self.root)

    def test_rejects_unknown_or_copied_tool_settings(self):
        self.config["tools"] = {}
        self.save_config()
        with self.assertRaisesRegex(quality.QualityError, "Unknown.*tools"):
            quality.Runner(self.root)

    def test_rejects_nonexistent_repository_root(self):
        with self.assertRaisesRegex(quality.QualityError, "root"):
            quality.Runner(self.root / "missing")

    def test_requires_explicit_public_and_production_inputs(self):
        for field in ("public_headers", "production_directories"):
            with self.subTest(field=field):
                value = self.config.pop(field)
                self.save_config()
                with self.assertRaisesRegex(quality.QualityError, field):
                    quality.Runner(self.root)
                self.config[field] = value

    def test_rejects_input_paths_outside_owned_repository(self):
        for path in ("../escape", str(self.root / "src"), "out/generated", "."):
            with self.subTest(path=path):
                self.config["production_directories"] = [path]
                self.save_config()
                with self.assertRaisesRegex(quality.QualityError, "production_directories"):
                    quality.Runner(self.root)

    def test_docs_uses_configured_module_headers_and_doxygen_input(self):
        for module in ("bytes", "status"):
            with self.subTest(module=module):
                relative = f"include/xgen/{module}"
                self.config["public_headers"] = [relative]
                self.save_config()
                header = self.root / relative / f"{module}.h"
                header.parent.mkdir(parents=True)
                header.write_text(f"/** \\file {module}.h */\n", "utf-8")
                runner = quality.Runner(self.root)
                with mock.patch.object(runner, "tool", return_value="doxygen"):
                    with mock.patch.object(runner, "run") as run:
                        runner.docs()
                self.assertIn(header.relative_to(self.root).as_posix(), runner.report["files"])
                self.assertIn(f'INPUT = "{header.as_posix()}"', run.call_args.kwargs["input_text"])

    def test_compilation_database_uses_configured_production_directory(self):
        self.config["production_directories"] = ["lib"]
        self.save_config()
        source = self.root / "lib/bytes.c"
        source.parent.mkdir()
        source.write_text("int value;\n", "utf-8")
        build = self.root / "out/build"
        build.mkdir(parents=True)
        (build / "compile_commands.json").write_text(json.dumps([
            {"directory": str(self.root), "file": "lib/bytes.c", "arguments": ["cc", "-c", "lib/bytes.c"]}
        ]), "utf-8")
        _, files = quality.Runner(self.root).compilation_database("out/build")
        self.assertEqual(files, [str(source)])

    def test_main_uses_explicit_root_from_unrelated_working_directory(self):
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        (self.root / "README.md").write_text("Consumer.\n", "utf-8", newline="")
        previous = Path.cwd()
        self.addCleanup(os.chdir, previous)
        os.chdir(self.temporary.name)
        with contextlib.redirect_stdout(io.StringIO()):
            result = xgen_quality.main(["text", "README.md"], root=self.root)
        self.assertEqual(result, 0)
        report = json.loads((self.root / "out/reports/quality-text.json").read_text("utf-8"))
        self.assertEqual(report["files"], ["README.md"])
        self.assertEqual(report["configuration"]["source"], "tools/quality.json")

    def test_cli_requires_explicit_root(self):
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertNotEqual(xgen_quality.main(["text"]), 0)

    def test_cli_root_option_selects_consumer(self):
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        (self.root / "README.md").write_text("Consumer.\n", "utf-8", newline="")
        with contextlib.redirect_stdout(io.StringIO()):
            result = xgen_quality.main(["--root", str(self.root), "text", "README.md"])
        self.assertEqual(result, 0)

    def test_source_revision_is_an_unverified_declaration(self):
        self.config["quality_source"] = {"revision": "a" * 40}
        self.save_config()
        runner = quality.Runner(self.root)
        self.assertEqual(runner.report["declared_quality_source"], self.config["quality_source"])
        self.assertIsNone(runner.report["installation"])

    def test_rejects_invalid_source_revision(self):
        self.config["quality_source"] = {"revision": "main"}
        self.save_config()
        with self.assertRaisesRegex(quality.QualityError, "quality_source"):
            quality.Runner(self.root)


if __name__ == "__main__":
    unittest.main()
