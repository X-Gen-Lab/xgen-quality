"""Run repository quality checks without downloading or modifying source files."""

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

from . import __version__
from .configuration import QualityError, load_configuration
from .spacing import check_header_spacing



def selected_tests(document):
    tests = document.get("tests", [])
    if not tests:
        raise QualityError("CTest selected no tests")
    names = []
    for test in tests:
        if any(p["name"] == "DISABLED" and p["value"]
               for p in test.get("properties", [])):
            raise QualityError(f"CTest selected disabled test: {test.get('name')}")
        if not test.get("name") or not test.get("command"):
            raise QualityError("CTest test has no name or executable command")
        names.append(test["name"])
    if len(names) != len(set(names)):
        raise QualityError("CTest discovered duplicate test names")
    return names


def validate_junit(path, expected):
    root = ET.parse(path).getroot()
    cases = list(root.iter("testcase"))
    if not expected or Counter(c.get("name") for c in cases) != Counter(expected):
        raise QualityError("JUnit names do not match selected nonempty CTest suite")
    for node in root.iter():
        if node.tag in {"failure", "error", "skipped"}:
            raise QualityError(f"JUnit reports {node.tag}")
        if node.get("status", "run").lower() in {"notrun", "disabled", "skipped"}:
            raise QualityError(f"JUnit test is {node.get('status')}")
        for key in ("failures", "errors", "skipped", "disabled"):
            if int(node.get(key, "0")):
                raise QualityError(f"JUnit reports nonzero {key}")


class Runner:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.config, identity = load_configuration(self.root)
        self.report = {"schema_version": 1, "standard_version": self.config["standard_version"],
                       "versions": {}, "files": [], "commands": [], **identity}

    def inside(self, name):
        path = (self.root / name).resolve()
        if not path.is_relative_to(self.root):
            raise QualityError(f"Path outside repository: {name}")
        return path

    def record_provenance(self):
        head = self.run(["git", "rev-parse", "--verify", "--quiet", "HEAD"], allowed_codes=(0, 1))
        status = self.run(["git", "status", "--porcelain=v1", "--untracked-files=normal", "-z"])
        self.report["source"] = {"head": head.strip() or None, "dirty": bool(status)}
        self.report["configuration_sha256"] = hashlib.sha256(
            (self.root / "tools/quality.json").read_bytes()
        ).hexdigest()

    def run(self, arguments, *, input_text=None, timeout=120, allowed_codes=(0,)):
        arguments = [str(arg) for arg in arguments]
        try:
            result = subprocess.run(arguments, cwd=self.root, input=input_text,
                                    capture_output=True, text=True, encoding="utf-8",
                                    errors="replace", timeout=timeout, check=False)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise QualityError(f"Cannot run {arguments[0]}: {error}") from error
        self.report["commands"].append({"arguments": arguments, "exit_code": result.returncode,
                                         "stdout": result.stdout, "stderr": result.stderr})
        if result.returncode not in allowed_codes:
            raise QualityError(f"{arguments[0]} exited {result.returncode}: "
                               f"{result.stderr.strip()} {result.stdout.strip()}")
        return result.stdout

    def tool(self, name):
        spec = self.config["tools"][name]
        command = os.environ.get(spec["environment"], spec["command"])
        if "/" in command or "\\" in command:
            command = str((self.root / command).resolve())
        output = self.run([command, "--version"])
        version = spec["version"]
        if not re.search(r"(?<![\d.])" + re.escape(version) + r"(?![\d.])", output):
            raise QualityError(f"{command}: expected version {version}, got {output.strip()}")
        self.report["versions"][name] = {"expected": version, "actual": output.strip(),
                                          "executable": command}
        return command

    def git_files(self, all_files=False):
        arguments = ["git", "ls-files", "-z", "--cached"]
        if all_files:
            arguments += ["--others", "--exclude-standard"]
        result = set(filter(None, self.run(arguments).split("\0")))
        result.update(filter(None, self.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=D", "-z"]
        ).split("\0")))
        return result

    def in_scope(self, path):
        relative = path.relative_to(self.root)
        scope = self.config["scope"]
        if any(part in scope["excluded_directories"] for part in relative.parts):
            return False
        return (relative.as_posix() in scope["root_files"] or
                (len(relative.parts) > 1 and relative.parts[0] in scope["directories"]))

    def select_files(self, names):
        explicit = bool(names)
        names = names or sorted(self.git_files(all_files=True))
        selected = []
        for name in names:
            path = self.inside(name)
            if not self.in_scope(path):
                if explicit:
                    raise QualityError(f"File outside owned scope: {name}")
                continue
            if not path.exists():
                if path.relative_to(self.root).as_posix() in self.git_files():
                    continue
                raise QualityError(f"unknown file, not a recorded deletion: {name}")
            if not path.is_file():
                raise QualityError(f"Expected file, got directory: {name}")
            if path not in selected:
                selected.append(path)
        return selected

    def check_text(self, paths):
        scope = self.config["scope"]
        for path in paths:
            if (path.suffix.lower() not in scope["text_extensions"] and
                    path.name not in scope["text_names"] + scope["root_files"]):
                continue
            data = path.read_bytes()
            text = data.decode("utf-8")
            if "\r" in text or (text and not text.endswith("\n")):
                raise QualityError(f"{path}: expected LF and final newline")
            if text.startswith("\ufeff") or "\x00" in text:
                raise QualityError(f"{path}: unexpected BOM or NUL in text")
            for number, line in enumerate(text.splitlines(), 1):
                trailing = line[len(line.rstrip(" \t")):]
                allowed = path.suffix == ".md" and trailing == "  " and line.strip()
                if trailing and not allowed:
                    raise QualityError(f"{path}:{number}: trailing whitespace")
                if re.match(r"^(<<<<<<<|>>>>>>>|\|\|\|\|\|\|\|)(?: |$)", line):
                    raise QualityError(f"{path}:{number}: merge conflict marker")
            if path.suffix == ".json":
                json.loads(text)
            if path.suffix in {".yml", ".yaml"} or path.name in {".clang-format", ".clang-tidy"}:
                try:
                    import yaml
                except ImportError as error:
                    raise QualityError("Prepare the pinned PyYAML dependency") from error
                expected = self.config["tools"]["pyyaml"]["version"]
                if yaml.__version__ != expected:
                    raise QualityError(f"Expected PyYAML {expected}, got {yaml.__version__}")
                self.report["versions"]["pyyaml"] = yaml.__version__
                try:
                    list(yaml.safe_load_all(text))
                except yaml.YAMLError as error:
                    raise QualityError(f"{path}: invalid YAML: {error}") from error
            self.report["files"].append(path.relative_to(self.root).as_posix())

    def reports(self, name=""):
        directory = self.inside("out/reports")
        directory.mkdir(parents=True, exist_ok=True)
        return self.inside(directory / name)

    def format(self, paths):
        paths = [p for p in paths if p.suffix in self.config["scope"]["format_extensions"]]
        self.report["files"] = [p.relative_to(self.root).as_posix() for p in paths]
        if not paths:
            self.report["status"] = "not_applicable"
            return
        command = self.tool("clang_format")
        for path in paths:
            self.run([command, f"--style=file:{self.root / '.clang-format'}",
                      "--dry-run", "--Werror", path])
        diagnostics = []
        public = [self.inside(name) for name in self.config["public_headers"]]
        for path in paths:
            if not any(path == header or path.is_relative_to(header) for header in public):
                continue
            for item in check_header_spacing(path.read_text("utf-8")):
                diagnostics.append({"path": path.relative_to(self.root).as_posix(),
                                    **vars(item)})
        self.report["spacing_diagnostics"] = diagnostics
        if diagnostics:
            raise QualityError("\n".join(
                f"{item['path']}:{item['line']}: {item['rule']}: {item['message']}"
                for item in diagnostics))

    def test(self, build, label, configuration):
        self.report["versions"]["ctest"] = self.run(["ctest", "--version"]).strip()
        command = ["ctest", "--test-dir", self.inside(build), "-C", configuration, "-L", label]
        names = selected_tests(json.loads(self.run(command + ["--show-only=json-v1"])))
        self.report["selected_tests"] = names
        destination = self.reports("ctest-results.xml")
        destination.unlink(missing_ok=True)
        self.run(command + ["--no-tests=error", "--output-on-failure",
                            "--output-junit", destination], timeout=600)
        validate_junit(destination, names)
        self.report["executed_tests"] = names

    def compilation_database(self, build):
        source = self.inside(self.inside(build) / "compile_commands.json")
        entries = json.loads(source.read_text("utf-8"))
        filtered = []
        for entry in entries:
            directory = Path(entry["directory"])
            if not directory.is_absolute():
                directory = self.inside(build) / directory
            path = (directory / entry["file"]).resolve()
            if (any(path.is_relative_to(self.inside(name)) for name in self.config["production_directories"])
                    and path.suffix in {".c", ".cc", ".cpp"}):
                if not path.is_file() or not (entry.get("command") or entry.get("arguments")):
                    raise QualityError(f"Invalid production compilation entry: {path}")
                filtered.append({**entry, "directory": str(directory.resolve()), "file": str(path)})
        if not filtered:
            raise QualityError("Compilation database contains no selected production translation units")
        directory = self.reports("compile-db")
        directory.mkdir(exist_ok=True)
        self.inside(directory / "compile_commands.json").write_text(
            json.dumps(filtered, indent=2) + "\n", "utf-8")
        self.report["files"] = sorted({e["file"] for e in filtered})
        return directory, self.report["files"]

    def analyze(self, kind, build):
        directory, files = self.compilation_database(build)
        if kind == "cppcheck":
            self.run([self.tool("cppcheck"), f"--project={directory / 'compile_commands.json'}",
                      "--enable=warning,performance,portability", "--error-exitcode=1", "--inline-suppr"],
                     timeout=600)
        else:
            command = self.tool("clang_tidy")
            for path in files:
                self.run([command, path, "-p", directory,
                          f"--config-file={self.root / '.clang-tidy'}", "--warnings-as-errors=*"],
                         timeout=300)

    def docs(self):
        headers = set()
        for name in self.config["public_headers"]:
            path = self.inside(name)
            paths = [path] if path.is_file() else path.rglob("*.h")
            headers.update(self.inside(p) for p in paths if p.suffix == ".h" and self.in_scope(self.inside(p)))
        headers = sorted(headers)
        if not headers:
            raise QualityError("Doxygen input contains no public headers")
        self.report["files"] = ["Doxyfile"] + [p.relative_to(self.root).as_posix() for p in headers]
        for path in headers:
            comments = re.findall(r"/\*(?:\*|!)[\s\S]*?\*/|^\s*//[/!].*$",
                                  path.read_text("utf-8"), re.MULTILINE)
            if not any(re.search(r"(?:^|[\s*])(?:\\|@)file(?:\s|$)", comment) for comment in comments):
                raise QualityError(f"{path}: missing Doxygen file documentation")
        command = self.tool("doxygen")
        directory = self.reports("doxygen")
        directory.mkdir(exist_ok=True)
        config = f'@INCLUDE = "{(self.root / "Doxyfile").as_posix()}"\n'
        config += "INPUT = " + " ".join(f'"{p.as_posix()}"' for p in headers) + "\n"
        config += f'OUTPUT_DIRECTORY = "{directory.as_posix()}"\n'
        config += f'WARN_LOGFILE = "{self.inside(directory / "warnings.log").as_posix()}"\n'
        self.run([command, "-"], input_text=config, timeout=300)

    def coverage(self, build, gcov):
        if not self.config["production_directories"]:
            raise QualityError("Coverage requires production_directories")
        command = [self.tool("gcovr"), "--root", self.root]
        for name in self.config["production_directories"]:
            command += ["--filter", re.escape(self.inside(name).as_posix()) + "/"]
        command.append("--json-summary")
        destination = self.reports("coverage-summary.json")
        destination.unlink(missing_ok=True)
        command.append(destination)
        detailed = self.reports("coverage.json")
        detailed.unlink(missing_ok=True)
        command += ["--json", detailed]
        for metric, threshold in self.config["coverage"].items():
            command += [f"--fail-under-{metric}", str(threshold)]
        if gcov:
            command += ["--gcov-executable", gcov]
        self.run(command + [self.inside(build)], timeout=600)
        if not detailed.is_file() or not json.loads(detailed.read_text("utf-8")).get("files"):
            raise QualityError("Missing or empty detailed coverage report")
        summary = json.loads(destination.read_text("utf-8"))
        if not summary.get("files") or summary.get("line_total", 0) <= 0 or summary.get("function_total", 0) <= 0:
            raise QualityError("Coverage report contains no production coverage data")
        for metric, threshold in self.config["coverage"].items():
            total = summary[f"{metric}_total"]
            if total and 100 * summary[f"{metric}_covered"] / total < threshold:
                raise QualityError(f"Coverage {metric} below {threshold}%")
        self.report["coverage"] = summary
        self.report["files"] = [entry["filename"] for entry in summary["files"]]


def main(arguments=None, root=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", help="Explicit consumer repository root")
    parser.add_argument("--version", action="version", version=f"xgen-quality {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("text", "format"):
        commands.add_parser(name).add_argument("files", nargs="*")
    for name in ("test", "cppcheck", "tidy", "coverage"):
        command = commands.add_parser(name)
        command.add_argument("--build-dir", required=True)
        if name == "test":
            command.add_argument("--label")
            command.add_argument("--config", default="Debug")
        if name == "coverage":
            command.add_argument("--gcov-executable")
    commands.add_parser("docs")
    args = parser.parse_args(arguments)
    runner = None
    exit_code = 0
    try:
        if sys.version_info < (3, 12):
            raise QualityError("Python 3.12 or newer is required")
        if root is None and args.root is None:
            raise QualityError("Provide --root PATH or main(root=PATH)")
        if root is not None and args.root is not None and Path(root).resolve() != Path(args.root).resolve():
            raise QualityError("--root conflicts with the explicit launcher root")
        runner = Runner(root if root is not None else args.root)
        runner.report.update(command=args.command, status="passed", started=datetime.now(timezone.utc).isoformat())
        runner.record_provenance()
        if args.command in {"text", "format"}:
            paths = runner.select_files(args.files)
            (runner.check_text if args.command == "text" else runner.format)(paths)
            if args.command == "text" and not runner.report["files"]:
                runner.report["status"] = "not_applicable"
        elif args.command == "test":
            runner.test(args.build_dir, args.label or runner.config["test_label"], args.config)
        elif args.command in {"cppcheck", "tidy"}:
            runner.analyze(args.command, args.build_dir)
        elif args.command == "docs":
            runner.docs()
        else:
            runner.coverage(args.build_dir, args.gcov_executable)
    except (QualityError, OSError, ValueError, KeyError, TypeError, ET.ParseError) as error:
        exit_code = 1
        print(f"quality: {error}", file=sys.stderr)
        if runner:
            runner.report.update(status="failed", error=str(error))
    if runner:
        runner.report["exit_code"] = exit_code
        try:
            report = runner.reports(f"quality-{args.command}.json")
            report.write_text(json.dumps(runner.report, indent=2, ensure_ascii=False) + "\n", "utf-8")
            print(f"{args.command}: {runner.report['status']} ({report})")
        except (OSError, QualityError) as error:
            print(f"Cannot write quality report: {error}", file=sys.stderr)
            exit_code = 1
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
