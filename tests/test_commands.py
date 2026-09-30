"""Command, input-validation and report contracts inherited from the pilot."""

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
from xgen_quality import configuration, runner as quality


class CommandTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.config = {"schema_version": 1, "standard_version": "1.0.0", "quality_version": "0.1.0",
                       "public_headers": ["include/xgen/demo"], "production_directories": ["src"]}
        self.write("tools/quality.json", json.dumps(self.config) + "\n")
        self.runner = quality.Runner(self.root)

    def write(self, name, content):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, "utf-8", newline="")
        return path

    def test_default_selection_includes_untracked_owned_files_and_ignores_vendor(self):
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        source = self.write("src/new.c", "int value;\n")
        self.write("vendor/third.c", "third-party\n")
        self.assertEqual(set(self.runner.select_files([])), {source, self.root / "tools/quality.json"})

    def test_selection_rejects_directories_and_deduplicates_files(self):
        path = self.write("src/group/file.c", "int value;\n")
        with self.assertRaisesRegex(quality.QualityError, "directory"):
            self.runner.select_files(["src/group"])
        self.assertEqual(self.runner.select_files([str(path), str(path)]), [path])

    def test_text_rejects_bom_trailing_whitespace_conflicts_and_invalid_json(self):
        for name, content, error in (("src/a.c", "\ufeffint a;\n", "BOM"),
                                     ("src/a.c", "int a; \n", "whitespace"),
                                     ("src/a.c", "<<<<<<< ours\n", "conflict"),
                                     ("docs/a.json", "{bad}\n", "property name")):
            with self.subTest(content=content):
                with self.assertRaisesRegex((quality.QualityError, ValueError), error):
                    self.runner.check_text([self.write(name, content)])

    def test_text_ignores_binary_and_parses_json_and_yaml(self):
        paths = [self.write("docs/a.bin", "\x00"), self.write("docs/a.json", "{}\n"),
                 self.write("docs/a.yml", "items: [one, two]\n")]
        self.runner.check_text(paths)
        self.assertEqual(self.runner.report["files"], ["docs/a.json", "docs/a.yml"])
        with self.assertRaisesRegex(quality.QualityError, "invalid YAML"):
            self.runner.check_text([self.write("docs/a.yml", "items: [\n")])

    def test_text_rejects_wrong_yaml_dependency(self):
        path = self.write("docs/a.yml", "items: []\n")
        with mock.patch("yaml.__version__", "0.0.0"):
            with self.assertRaisesRegex(quality.QualityError, "PyYAML"):
                self.runner.check_text([path])

    def test_format_no_sources_is_not_applicable(self):
        self.runner.format([self.write("README.md", "Text.\n")])
        self.assertEqual(self.runner.report["status"], "not_applicable")
        self.assertEqual(self.runner.report["commands"], [])

    def test_formatter_is_check_only_and_preserves_argv_paths(self):
        path = self.write("src/file with spaces.c", "int value;\n")
        result = subprocess.CompletedProcess([], 0, "clang-format version 19.1.5", "")
        with mock.patch.dict(os.environ, {"XGEN_CLANG_FORMAT": "out/tools/formatter.exe"}):
            with mock.patch("xgen_quality.runner.subprocess.run", return_value=result) as run:
                self.runner.format([path])
        arguments = run.call_args.args[0]
        self.assertIn("--dry-run", arguments)
        self.assertIn("--Werror", arguments)
        self.assertNotIn("-i", arguments)
        self.assertEqual(arguments[-1], str(path))
        self.assertEqual(path.read_text("utf-8"), "int value;\n")

    def test_discovery_rejects_duplicate_names_and_missing_executable(self):
        for tests in ([{"name": "A"}], [{"name": "A", "command": ["test"]}] * 2):
            with self.subTest(tests=tests):
                with self.assertRaises(quality.QualityError):
                    quality.selected_tests({"tests": tests})

    def test_ctest_records_selected_and_executed_inventory(self):
        inventory = {"tests": [{"name": "A", "command": ["host-tests"]}]}

        def command(arguments, **kwargs):
            if "--version" in arguments:
                return "ctest version 3.31.0"
            if "--show-only=json-v1" in arguments:
                return json.dumps(inventory)
            self.assertIn("--no-tests=error", arguments)
            path = Path(arguments[arguments.index("--output-junit") + 1])
            self.assertTrue(path.is_absolute())
            path.write_text('<testsuite><testcase name="A"/></testsuite>', "utf-8")
            return "1/1 passed"

        with mock.patch.object(self.runner, "run", side_effect=command):
            self.runner.test("out/host", "unit", "Debug")
        self.assertEqual(self.runner.report["selected_tests"], ["A"])
        self.assertEqual(self.runner.report["executed_tests"], ["A"])

    def database(self, production=True):
        self.write("src/demo.c", "int value;\n")
        self.write("tests/test_demo.cpp", "int test;\n")
        records = [{"directory": "../..", "file": "tests/test_demo.cpp", "command": "c++ -c tests/test_demo.cpp"}]
        if production:
            records.append({"directory": "../..", "file": "src/demo.c", "command": "cc -c src/demo.c"})
        self.write("out/host/compile_commands.json", json.dumps(records))

    def test_analysis_excludes_test_translation_units(self):
        self.database()
        for kind in ("cppcheck", "tidy"):
            with self.subTest(kind=kind):
                with mock.patch.object(self.runner, "tool", return_value=kind):
                    with mock.patch.object(self.runner, "run") as run:
                        self.runner.analyze(kind, "out/host")
                self.assertEqual(self.runner.report["files"], [str(self.root / "src/demo.c")])
                self.assertEqual(run.call_count, 1)
                database = json.loads((self.root / "out/reports/compile-db/compile_commands.json").read_text("utf-8"))
                self.assertEqual([Path(e["file"]).name for e in database], ["demo.c"])

    def test_analysis_rejects_empty_or_stale_database(self):
        self.database(production=False)
        with self.assertRaisesRegex(quality.QualityError, "no selected production"):
            self.runner.compilation_database("out/host")
        self.database()
        (self.root / "src/demo.c").unlink()
        with self.assertRaisesRegex(quality.QualityError, "Invalid production"):
            self.runner.compilation_database("out/host")

    def test_coverage_rechecks_thresholds_and_rejects_empty_denominator(self):
        def reports(arguments, **kwargs):
            self.write("out/reports/coverage.json", '{"files": [{"file": "src/demo.c"}]}')
            self.write("out/reports/coverage-summary.json", json.dumps(summary))
            self.assertIn("--gcov-executable", arguments)

        summary = {"files": [{"filename": "src/demo.c"}], "line_total": 10, "line_covered": 7,
                   "branch_total": 10, "branch_covered": 9, "function_total": 10, "function_covered": 9}
        with mock.patch.object(self.runner, "tool", return_value="gcovr"):
            with mock.patch.object(self.runner, "run", side_effect=reports):
                with self.assertRaisesRegex(quality.QualityError, "below"):
                    self.runner.coverage("out/host", "gcov")
                summary["line_total"] = 0
                with self.assertRaisesRegex(quality.QualityError, "no production"):
                    self.runner.coverage("out/host", "gcov")

    def test_empty_production_declaration_cannot_pass_coverage(self):
        self.config["production_directories"] = []
        self.write("tools/quality.json", json.dumps(self.config))
        with self.assertRaisesRegex(quality.QualityError, "production_directories"):
            quality.Runner(self.root).coverage("out/host", None)

    def test_command_failure_is_reported_and_preserves_nonzero_exit(self):
        with mock.patch.object(quality.Runner, "record_provenance"):
            with mock.patch.object(quality.Runner, "docs", side_effect=quality.QualityError("bad public API")):
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    code = quality.main(["docs"], root=self.root)
        self.assertEqual(code, 1)
        report = json.loads((self.root / "out/reports/quality-docs.json").read_text("utf-8"))
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["exit_code"], 1)
        self.assertIn("bad public API", report["error"])

    def test_commands_dispatch_with_explicit_root_and_report_success(self):
        cases = [("test", "test", ["--build-dir", "out/host"]),
                 ("cppcheck", "analyze", ["--build-dir", "out/host"]),
                 ("tidy", "analyze", ["--build-dir", "out/host"]),
                 ("coverage", "coverage", ["--build-dir", "out/host"]),
                 ("format", "format", ["tools/quality.json"])]
        for command, method, arguments in cases:
            with self.subTest(command=command):
                with mock.patch.object(quality.Runner, "record_provenance"):
                    with mock.patch.object(quality.Runner, method) as operation:
                        with contextlib.redirect_stdout(io.StringIO()):
                            self.assertEqual(quality.main([command, *arguments], root=self.root), 0)
                operation.assert_called_once()
                report = json.loads((self.root / f"out/reports/quality-{command}.json").read_text("utf-8"))
                self.assertEqual(report["status"], "passed")

    def test_conflicting_roots_are_rejected_without_operating(self):
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(quality.main(["--root", str(self.root.parent), "text"], root=self.root), 1)

    def test_configuration_rejects_bad_types_overrides_and_duplicate_inputs(self):
        changes = [("schema_version", True), ("scope", {"unknown": []}),
                   ("scope", {"directories": "src"}), ("coverage", {"line": 79}),
                   ("test_label", ""), ("test_label", "["), ("public_headers", "include"),
                   ("public_headers", [""]), ("production_directories", ["src", "src"]),
                   ("production_directories", ["tools/quality.json"])]
        for field, value in changes:
            with self.subTest(field=field, value=value):
                self.write("tools/quality.json", json.dumps({**self.config, field: value}))
                with self.assertRaises(quality.QualityError):
                    quality.Runner(self.root)

    def test_configuration_rejects_invalid_json_and_nonobject(self):
        for text in ("{bad}", "[]"):
            with self.subTest(text=text):
                self.write("tools/quality.json", text)
                with self.assertRaises(quality.QualityError):
                    quality.Runner(self.root)

    def test_metadata_absence_and_installed_archive_are_distinct(self):
        with mock.patch.object(configuration.metadata, "distribution", side_effect=configuration.metadata.PackageNotFoundError):
            self.assertIsNone(configuration.installation_identity())
        distribution = mock.Mock()
        distribution.locate_file.return_value = configuration.__file__
        distribution.version = "0.1.0"
        distribution.read_text.side_effect = ["pip", '{"archive_info": {"hashes": {"sha256": "abc"}}}']
        with mock.patch.object(configuration.metadata, "distribution", return_value=distribution):
            installed = configuration.installation_identity()
        self.assertEqual(installed["direct_url"]["archive_info"]["hashes"]["sha256"], "abc")


if __name__ == "__main__":
    unittest.main()
