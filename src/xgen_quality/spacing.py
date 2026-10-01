"""Read-only spacing checks for documented declarations in ordinary C headers.

This deliberately recognizes a small set of lexical header patterns. It does not
parse declarations, expand macros, or prescribe paragraphs inside function bodies.
"""

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class Diagnostic:
    line: int
    previous_line: int
    rule: str
    expected_blank_lines: int
    message: str


@dataclass(frozen=True)
class _Token:
    kind: str
    value: str
    line: int
    end_line: int
    standalone: bool


# Comments, continued directives and literals are opaque before punctuation is
# considered. Raw strings are accepted here only to avoid reading their contents
# as C declarations; this checker does not claim general C++ layout support.
_LEXEMES = re.compile(
    r'(?P<directive>^[ \t]*\#(?:\\\n|[^\n])*)'
    r'|(?P<comment>/\*[\s\S]*?\*/|//(?:\\\n|[^\n])*)'
    r'|(?P<raw>(?:u8|u|U|L)?R"(?P<delimiter>[^ ()\\\t\r\n]{0,16})'
    r'\([\s\S]*?\)(?P=delimiter)")'
    r'|(?P<literal>(?:u8|u|U|L)?(?:"(?:\\[\s\S]|[^"\\])*"'
    r"|'(?:\\[\s\S]|[^'\\])*'))"
    r'|(?P<word>[A-Za-z_][A-Za-z_0-9]*)'
    r'|(?P<symbol>[^\s])', re.MULTILINE)


def _tokens(text):
    line = 1
    previous_end = 0
    for match in _LEXEMES.finditer(text):
        line += text.count("\n", previous_end, match.start())
        value = match.group()
        end_line = line + value.count("\n")
        line_start = text.rfind("\n", 0, match.start()) + 1
        yield _Token(match.lastgroup, value, line, end_line,
                     not text[line_start:match.start()].strip())
        line = end_line
        previous_end = match.end()


def _directive(token):
    return re.sub(r"\s+", " ", token.value.replace("\\\n", " ")).strip()


def check_header_spacing(text):
    """Return line-based C-020 / DOC-013 diagnostics without changing *text*.

    Callers select public headers. Only canonical include guards / extern-C
    groups and standalone top-level Doxygen ``brief`` blocks are checked.
    Conditional declaration wrappers, macro-generated APIs and body paragraphs
    remain review responsibilities. Line numbers are one-based; the gap between
    ``previous_line`` and ``line`` must contain ``expected_blank_lines`` blanks.
    """
    tokens = list(_tokens(text))
    lines = text.splitlines()
    diagnostics = {}

    def gap(previous, current, expected, rule, description):
        if current.line <= previous.end_line:
            return
        between = lines[previous.end_line:current.line - 1]
        if any(line.strip() for line in between) or len(between) == expected:
            return
        key = (previous.end_line, current.line)
        diagnostics[key] = Diagnostic(
            current.line, previous.end_line, rule, expected,
            f"{description}: expected {expected} blank line(s), found {len(between)}")

    code = [token for token in tokens if token.kind != "comment"]
    positions = {id(token): index for index, token in enumerate(tokens)}
    for index, token in enumerate(tokens[:-1]):
        if token.kind == "directive" and re.match(r"#\s*include\b", _directive(token)):
            if tokens[index + 1].kind != "directive":
                gap(token, tokens[index + 1], 1, "C-020", "include section boundary")
    guard = None
    if len(code) >= 2 and code[0].kind == code[1].kind == "directive":
        match = re.fullmatch(r"#\s*ifndef ([A-Za-z_]\w*)", _directive(code[0]))
        if match and re.fullmatch(r"#\s*define " + match[1], _directive(code[1])):
            guard = code[0]
            gap(code[0], code[1], 0, "C-020", "include guard directives")
            following = tokens[positions[id(code[1])] + 1:]
            if following:
                gap(code[1], following[0], 1, "C-020", "header content after include guard")

    opening_ends = set()
    closing_ends = set()
    linkage_braces = set()
    for index, token in enumerate(code):
        if token.kind != "directive" or not re.fullmatch(
                r"#\s*ifdef __cplusplus", _directive(token)):
            continue
        tail = code[index + 1:index + 5]
        opening = (len(tail) == 4 and [t.value for t in tail[:3]] ==
                   ["extern", '"C"', "{"] and
                   re.fullmatch(r"#\s*endif(?: /\*.*\*/| //.*)?", _directive(tail[3])))
        closing = (len(tail) >= 2 and tail[0].value == "}" and
                   re.fullmatch(r"#\s*endif(?: /\*.*\*/| //.*)?", _directive(tail[1])))
        if not opening and not closing:
            continue
        group = [token] + tail[:4 if opening else 2]
        for previous, current in zip(group, group[1:]):
            gap(previous, current, 0, "C-020", "extern C directive group")
        token_index = positions[id(token)]
        if token_index:
            gap(tokens[token_index - 1], token, 1, "C-020", "extern C boundary")
        final_index = positions[id(group[-1])]
        if final_index + 1 < len(tokens):
            gap(group[-1], tokens[final_index + 1], 1, "C-020", "extern C boundary")
        (opening_ends if opening else closing_ends).add(id(group[-1]))
        linkage_braces.add(id(tail[2] if opening else tail[0]))

    depth = 0
    parentheses = 0
    for index, token in enumerate(tokens):
        if token.kind == "symbol":
            if token.value == "{" and id(token) not in linkage_braces:
                depth += 1
            elif token.value == "}" and id(token) not in linkage_braces:
                depth = max(0, depth - 1)
            elif token.value == "(":
                parentheses += 1
            elif token.value == ")":
                parentheses = max(0, parentheses - 1)
        if (token.kind != "comment" or not token.standalone or depth or parentheses or
                not token.value.startswith("/**") or token.value.startswith("/**<")):
            continue
        following = tokens[index + 1] if index + 1 < len(tokens) else None
        if re.search(r"[\\@]file\b", token.value):
            if index == 0 and following:
                gap(token, following, 1, "C-020", "file documentation boundary")
            continue
        if not re.search(r"[\\@]brief\b", token.value):
            continue
        # A directive wrapping a declaration is ambiguous without preprocessing.
        # Directly documented #define APIs are unambiguous and remain supported.
        if following and (following.kind != "directive" or re.match(
                r"#\s*define\b", _directive(following))):
            gap(token, following, 0, "DOC-013", "documentation must touch its declaration")
        group_start = index
        # A leading contract comment followed immediately by a brief block is
        # one documentation group. A post-definition tool annotation belongs
        # to the preceding declaration and must not be pulled into that group.
        while group_start:
            previous = tokens[group_start - 1]
            if (previous.kind != "comment" or not previous.standalone or
                    previous.value.startswith("/**") or "NOLINTEND" in previous.value or
                    previous.end_line + 1 != tokens[group_start].line):
                break
            group_start -= 1
        if group_start:
            previous = tokens[group_start - 1]
            if (previous.kind != "directive" or re.match(
                    r"#\s*define\b", _directive(previous)) or
                    id(previous) in opening_ends | closing_ends):
                gap(previous, tokens[group_start], 1, "C-020", "independent API documentation group")

    # Without extern C, the last declaration and final include-guard directive
    # still form separate header sections. Nested/conditional endings are not
    # inferred here; only an ordinary final declaration followed by #endif.
    if guard and len(tokens) > 1 and tokens[-1].kind == "directive" and re.fullmatch(
            r"#\s*endif(?: /\*.*\*/| //.*)?", _directive(tokens[-1])):
        if tokens[-2].value in {";", "}"}:
            gap(tokens[-2], tokens[-1], 1, "C-020", "final include guard boundary")
    return sorted(diagnostics.values(), key=lambda item: (item.line, item.rule))
