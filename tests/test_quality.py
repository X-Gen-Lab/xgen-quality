"""Regression tests for quality-gate input and result validation."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

PACKAGE = Path(__file__).resolve().parents[1] / "src/xgen_quality"
sys.path.insert(0, str(PACKAGE.parent))
from xgen_quality import runner as quality


class QualityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        (self.root / "tools").mkdir()
        (self.root / "tools/quality.json").write_text(json.dumps({
            "schema_version": 1, "standard_version": "1.0.0", "quality_version": "0.1.0",
            "public_headers": ["include/xgen/crc"], "production_directories": ["src"]
        }), "utf-8")
        self.runner = quality.Runner(self.root)

    def write(self, name, content):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="")
        return path

    def test_rejects_path_outside_repository(self):
        with self.assertRaisesRegex(quality.QualityError, "outside"):
            self.runner.select_files(["../escape.c"])

    def test_rejects_explicit_excluded_source(self):
        self.write("out/generated.c", "int value;\n")
        with self.assertRaisesRegex(quality.QualityError, "scope"):
            self.runner.select_files(["out/generated.c"])

    def test_unknown_path_is_not_treated_as_deleted(self):
        with mock.patch.object(self.runner, "git_files", return_value=set()):
            with self.assertRaisesRegex(quality.QualityError, "unknown"):
                self.runner.select_files(["src/missing.c"])

    def test_known_deleted_path_is_ignored(self):
        with mock.patch.object(
            self.runner, "git_files", return_value={"src/removed.c"}
        ):
            self.assertEqual(self.runner.select_files(["src/removed.c"]), [])

    def test_file_with_spaces_is_one_input(self):
        path = self.write("docs/name with spaces.md", "Valid text.\n")
        self.assertEqual(self.runner.select_files([str(path)]), [path])

    def test_text_rejects_crlf(self):
        path = self.write("src/example.c", "int value;\r\n")
        with self.assertRaisesRegex(quality.QualityError, "LF"):
            self.runner.check_text([path])

    def test_markdown_allows_exact_two_space_line_break(self):
        path = self.write("docs/example.md", "First line.  \nSecond.\n")
        self.runner.check_text([path])

    def test_test_discovery_rejects_empty_suite(self):
        with self.assertRaisesRegex(quality.QualityError, "no tests"):
            quality.selected_tests({"tests": []})

    def test_test_discovery_rejects_disabled_case(self):
        document = {"tests": [{"name": "Example.Case", "command": ["test"],
                                "properties": [{"name": "DISABLED", "value": True}]}]}
        with self.assertRaisesRegex(quality.QualityError, "disabled"):
            quality.selected_tests(document)

    def test_junit_rejects_all_skipped(self):
        path = self.write("result.xml", '<testsuite><testcase name="A" '
                          'status="notrun"><skipped/></testcase></testsuite>')
        with self.assertRaisesRegex(quality.QualityError, "skip|notrun"):
            quality.validate_junit(path, ["A"])

    def test_junit_rejects_missing_selected_name(self):
        path = self.write("result.xml", '<testsuite><testcase name="A" '
                          'status="run"/></testsuite>')
        with self.assertRaisesRegex(quality.QualityError, "names"):
            quality.validate_junit(path, ["A", "B"])

    def test_junit_accepts_exact_executed_suite(self):
        path = self.write("result.xml", '<testsuite><testcase name="A" '
                          'status="run"/><testcase name="B" '
                          'status="run"/></testsuite>')
        quality.validate_junit(path, ["A", "B"])

    def test_junit_rejects_empty_inventory_and_empty_report(self):
        path = self.write("result.xml", '<testsuite tests="0"/>')
        with self.assertRaisesRegex(quality.QualityError, "nonempty"):
            quality.validate_junit(path, [])

    def test_junit_rejects_failure_with_matching_names(self):
        path = self.write("result.xml", '<testsuite><testcase name="A">'
                          '<failure message="assertion failed"/></testcase></testsuite>')
        with self.assertRaisesRegex(quality.QualityError, "failure"):
            quality.validate_junit(path, ["A"])

    def test_junit_rejects_disabled_summary_without_skipped_element(self):
        path = self.write("result.xml", '<testsuite disabled="1">'
                          '<testcase name="A"/></testsuite>')
        with self.assertRaisesRegex(quality.QualityError, "disabled"):
            quality.validate_junit(path, ["A"])

    def test_nonzero_tool_status_propagates(self):
        result = subprocess.CompletedProcess(["analyzer"], 7, "", "parse failed")
        with mock.patch("xgen_quality.runner.subprocess.run", return_value=result):
            with self.assertRaisesRegex(quality.QualityError, "7.*parse failed"):
                self.runner.run(["analyzer"])

    def test_tool_timeout_is_a_failed_check(self):
        with mock.patch("xgen_quality.runner.subprocess.run", side_effect=subprocess.TimeoutExpired("analyzer", 1)):
            with self.assertRaisesRegex(quality.QualityError, "Cannot run"):
                self.runner.run(["analyzer"])

    def test_wrong_tool_version_is_rejected(self):
        with mock.patch.object(self.runner, "run", return_value="clang-format version 18.1.0"):
            with self.assertRaisesRegex(quality.QualityError, "19.1.5"):
                self.runner.tool("clang_format")

    def test_report_records_head_dirty_state_and_configuration_hash(self):
        head = "a" * 40
        with mock.patch.object(self.runner, "run", side_effect=[head + "\n", " M src/a.c\0"]):
            self.runner.record_provenance()
        self.assertEqual(self.runner.report["source"], {"head": head, "dirty": True})
        expected = hashlib.sha256((self.root / "tools/quality.json").read_bytes()).hexdigest()
        self.assertEqual(self.runner.report["configuration_sha256"], expected)

    def test_unborn_repository_reports_null_head(self):
        with mock.patch.object(self.runner, "run", side_effect=["", ""]):
            self.runner.record_provenance()
        self.assertEqual(self.runner.report["source"], {"head": None, "dirty": False})

    def test_docs_rejects_missing_public_headers(self):
        with mock.patch.object(self.runner, "tool", return_value="doxygen"):
            with mock.patch.object(self.runner, "run"):
                with self.assertRaisesRegex(quality.QualityError, "no public headers"):
                    self.runner.docs()

    def test_docs_rejects_header_without_file_documentation(self):
        self.write("include/xgen/crc/probe.h", "int undocumented_api(int input);\n")
        with mock.patch.object(self.runner, "tool", return_value="doxygen"):
            with mock.patch.object(self.runner, "run"):
                with self.assertRaisesRegex(quality.QualityError, "probe.h.*file documentation"):
                    self.runner.docs()

    def test_docs_rejects_file_command_in_ordinary_comment(self):
        self.write("include/xgen/crc/probe.h", "/* \\file probe.h */\n")
        with mock.patch.object(self.runner, "tool", return_value="doxygen"):
            with mock.patch.object(self.runner, "run"):
                with self.assertRaisesRegex(quality.QualityError, "file documentation"):
                    self.runner.docs()

    def test_docs_accepts_doxygen_file_comment_forms(self):
        for comment in ("/** \\file probe.h */", "/*! @file probe.h */",
                        "/// \\file probe.h", "//! @file probe.h"):
            with self.subTest(comment=comment):
                self.write("include/xgen/crc/probe.h", comment + "\n")
                with mock.patch.object(self.runner, "tool", return_value="doxygen"):
                    with mock.patch.object(self.runner, "run") as run:
                        self.runner.docs()
                self.assertIn("include/xgen/crc/probe.h", self.runner.report["files"])
                run.assert_called_once()

    def write_coverage_summary(self):
        summary = {"files": [{"filename": "src/crc.c"}]}
        for metric in ("line", "branch", "function"):
            summary.update({f"{metric}_total": 10, f"{metric}_covered": 9})
        self.write("out/reports/coverage-summary.json", json.dumps(summary))

    def test_coverage_rejects_missing_detailed_report(self):
        with mock.patch.object(self.runner, "tool", return_value="gcovr"):
            with mock.patch.object(self.runner, "run", side_effect=lambda *a, **k: self.write_coverage_summary()):
                with self.assertRaisesRegex(quality.QualityError, "detailed coverage report"):
                    self.runner.coverage("out/build", None)

    def test_coverage_rejects_empty_detailed_report(self):
        def produce_reports(*args, **kwargs):
            self.write_coverage_summary()
            self.write("out/reports/coverage.json", '{"files": []}')

        with mock.patch.object(self.runner, "tool", return_value="gcovr"):
            with mock.patch.object(self.runner, "run", side_effect=produce_reports):
                with self.assertRaisesRegex(quality.QualityError, "detailed coverage report"):
                    self.runner.coverage("out/build", None)

    def test_coverage_does_not_reuse_stale_detailed_report(self):
        destination = self.write("out/reports/coverage.json", '{"files": [{"file": "src/crc.c"}]}')
        with mock.patch.object(self.runner, "tool", return_value="gcovr"):
            with mock.patch.object(self.runner, "run", side_effect=lambda *a, **k: self.write_coverage_summary()):
                with self.assertRaisesRegex(quality.QualityError, "detailed coverage report"):
                    self.runner.coverage("out/build", None)
        self.assertFalse(destination.exists())

    def test_coverage_requests_and_preserves_detailed_report(self):
        detail = {"gcovr/format_version": "0.14", "files": [{"file": "src/crc.c",
                  "lines": [{"line_number": 8, "count": 0, "branches": [{"count": 0}]}]}]}

        def produce_reports(arguments, **kwargs):
            self.assertEqual(Path(arguments[arguments.index("--json") + 1]),
                             self.root / "out/reports/coverage.json")
            self.write_coverage_summary()
            self.write("out/reports/coverage.json", json.dumps(detail))

        with mock.patch.object(self.runner, "tool", return_value="gcovr"):
            with mock.patch.object(self.runner, "run", side_effect=produce_reports):
                self.runner.coverage("out/build", None)
        self.assertEqual(json.loads((self.root / "out/reports/coverage.json").read_text("utf-8")), detail)


if __name__ == "__main__":
    unittest.main()
