"""Public-header spacing contracts beyond clang-format definition layout."""

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from xgen_quality import runner


class SpacingGateTests(unittest.TestCase):
    def test_format_rejects_missing_api_group_spacing_without_modifying_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "tools").mkdir()
            (root / "tools/quality.json").write_text(json.dumps({
                "schema_version": 1, "standard_version": "1.0.0", "quality_version": "0.1.0",
                "public_headers": ["include"], "production_directories": ["src"]}), "utf-8")
            path = root / "include/demo.h"
            path.parent.mkdir()
            source = "/** \\brief First. */\nvoid first(void);\n/** \\brief Second. */\nvoid second(void);\n"
            path.write_text(source, "utf-8")
            gate = runner.Runner(root)
            with mock.patch.object(gate, "tool", return_value="clang-format"):
                with mock.patch.object(gate, "run", return_value=""):
                    with self.assertRaisesRegex(runner.QualityError, "C-020"):
                        gate.format([path])
            self.assertEqual(path.read_text("utf-8"), source)


if __name__ == "__main__":
    unittest.main()
