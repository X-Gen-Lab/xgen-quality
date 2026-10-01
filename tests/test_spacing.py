"""Public-header spacing contracts beyond clang-format definition layout."""

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from xgen_quality import runner
from xgen_quality.spacing import check_header_spacing


HEADER = r'''/** \file demo.h
 * \brief Public API.
 */

#ifndef DEMO_H
#define DEMO_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/** \brief First API. */
void first(void);

/** \brief Second API. */
void second(void);

#ifdef __cplusplus
}
#endif

#endif /* DEMO_H */
'''


class HeaderSpacingTests(unittest.TestCase):
    def test_canonical_header_passes(self):
        self.assertEqual(check_header_spacing(HEADER), [])

    def test_structural_boundaries_require_one_blank(self):
        boundaries = [
            (" */", "#ifndef DEMO_H"),
            ("#define DEMO_H", "#include <stddef.h>"),
            ("#include <stdint.h>", "#ifdef __cplusplus"),
            ("#endif", "/** \\brief First API. */"),
            ("void first(void);", "/** \\brief Second API. */"),
            ("void second(void);", "#ifdef __cplusplus"),
            ("#endif", "#endif /* DEMO_H */"),
        ]
        for left, right in boundaries:
            for count in (0, 2):
                with self.subTest(left=left, right=right, count=count):
                    source = HEADER.replace(left + "\n\n" + right,
                                            left + "\n" * (count + 1) + right)
                    issues = check_header_spacing(source)
                    self.assertEqual(len(issues), 1, issues)
                    self.assertEqual(issues[0].rule, "C-020")
                    self.assertEqual(issues[0].expected_blank_lines, 1)
                    self.assertEqual(issues[0].line - issues[0].previous_line - 1, count)

    def test_guard_and_linkage_directives_remain_contiguous(self):
        for left, right in [("#ifndef DEMO_H", "#define DEMO_H"),
                            ("#ifdef __cplusplus", 'extern "C" {'),
                            ('extern "C" {', "#endif"),
                            ("#ifdef __cplusplus", "}"), ("}", "#endif")]:
            with self.subTest(left=left):
                source = HEADER.replace(left + "\n" + right, left + "\n\n" + right)
                issues = check_header_spacing(source)
                self.assertEqual(len(issues), 1, issues)
                self.assertEqual(issues[0].expected_blank_lines, 0)

    def test_documentation_must_touch_declaration(self):
        source = "/** @brief UTF-8 内容. */\n\nvoid first(void);\n"
        issues = check_header_spacing(source)
        self.assertEqual([(i.line, i.previous_line, i.rule, i.expected_blank_lines)
                          for i in issues], [(3, 1, "DOC-013", 0)])

    def test_members_and_function_bodies_are_not_paragraph_checked(self):
        source = r'''/** \brief Object. */
typedef struct {
    /** \brief Field. */

    int field;
    int other; /**< Tail field. */
    /** \brief Another field. */
    int third;
} object_t;

static inline void function(void) {
    /** \brief Local documentation. */

    int value = 0;
    (void)value;
}
'''
        self.assertEqual(check_header_spacing(source), [])

    def test_comment_contents_and_trailing_documentation_are_opaque(self):
        source = r'''/** \brief Object.
 *
 * \code
 * /** \brief Not a new comment.
 * \endcode
 */
int value; /**< trailing description */

/** \brief API. */
void api(void);
'''
        self.assertEqual(check_header_spacing(source), [])

    def test_macro_continuations_and_literal_contents_are_opaque(self):
        source = r'''#define CONTINUED(x) \
/** \brief Not an API. */ \
"still a macro" \
"#ifdef __cplusplus"

const char *text = "escaped \\\" /** \\brief fake */";
const char quote = '\'';
const char *raw = u8R"tag(
/** \brief Fake API. */

void fake(void);
#ifdef __cplusplus
extern "C" {
#endif
)tag";

/** \brief Real API. */
void real(void);
'''
        self.assertEqual(check_header_spacing(source), [])

    def test_documented_macros_form_separate_api_groups(self):
        source = "/** \\brief A. */\n#define A 1\n/** \\brief B. */\n\n#define B 2\n"
        self.assertEqual([(i.rule, i.line) for i in check_header_spacing(source)],
                         [("C-020", 3), ("DOC-013", 5)])

    def test_conditional_wrappers_remain_manual(self):
        source = r'''#if USE_ONE
/** \brief One API. */
void one(void);
#else
/** \brief Alternative API. */
void alternative(void);
#endif

/** \brief Conditional type. */

#if USE_ONE
typedef int number_t;
#else
typedef long number_t;
#endif
'''
        self.assertEqual(check_header_spacing(source), [])

    def test_empty_and_partial_noncanonical_headers_are_safe(self):
        for source in ("", "\n", "#pragma once\n", "/** @brief Incomplete. */\n",
                       "int value;\n/**< not a declaration group */\n",
                       "// ordinary comment\nint value;\n",
                       "/** @defgroup api API\n * @{\n */\nint value;\n"):
            with self.subTest(source=source):
                self.assertEqual(check_header_spacing(source), [])

    def test_post_definition_annotation_belongs_to_previous_group(self):
        source = "void first(void);\n// NOLINTEND(example)\n/** @brief Next. */\nvoid next(void);\n"
        issues = check_header_spacing(source)
        self.assertEqual([(i.previous_line, i.line) for i in issues], [(2, 3)])

    def test_leading_contract_comment_and_doxygen_are_one_group(self):
        source = "int previous;\n\n/* Caller owns the buffer. */\n/** @brief Initialize. */\nvoid init(void);\n"
        self.assertEqual(check_header_spacing(source), [])
        issues = check_header_spacing(source.replace("previous;\n\n", "previous;\n"))
        self.assertEqual([(i.previous_line, i.line) for i in issues], [(1, 2)])

    def test_header_without_extern_c_has_include_and_guard_boundaries(self):
        source = "#ifndef DEMO_H\n#define DEMO_H\n\n#include <stdint.h>\n/** @brief Value. */\nint value;\n#endif\n"
        issues = check_header_spacing(source)
        self.assertEqual([(i.previous_line, i.line) for i in issues], [(4, 5), (6, 7)])


class SpacingGateTests(unittest.TestCase):
    def test_format_rejects_missing_api_group_spacing_without_modifying_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
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
            self.assertEqual(gate.report["spacing_diagnostics"][0]["path"], "include/demo.h")

    def test_format_only_checks_selected_public_headers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / "tools").mkdir()
            (root / "tools/quality.json").write_text(json.dumps({
                "schema_version": 1, "standard_version": "1.0.0", "quality_version": "0.1.0",
                "public_headers": ["include/public.h"], "production_directories": ["src"]}), "utf-8")
            path = root / "include/private.h"
            path.parent.mkdir()
            path.write_text("/** @brief A. */\nvoid a(void);\n/** @brief B. */\nvoid b(void);\n", "utf-8")
            gate = runner.Runner(root)
            with mock.patch.object(gate, "tool", return_value="clang-format"):
                with mock.patch.object(gate, "run", return_value=""):
                    gate.format([path])
            self.assertEqual(gate.report["spacing_diagnostics"], [])


if __name__ == "__main__":
    unittest.main()
