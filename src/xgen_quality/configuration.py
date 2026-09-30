"""Validate consumer declarations and merge the versioned package policy."""

import hashlib
from importlib import metadata, resources
import json
from pathlib import Path
import re

from . import __version__


class QualityError(RuntimeError):
    """A failed check, invalid input, or unusable tool."""


def installation_identity():
    try:
        distribution = metadata.distribution("xgen-quality")
    except metadata.PackageNotFoundError:
        return None
    installed = Path(distribution.locate_file("xgen_quality/configuration.py")).resolve()
    if installed != Path(__file__).resolve() or not distribution.read_text("INSTALLER"):
        return None
    direct_url = distribution.read_text("direct_url.json")
    return {"version": distribution.version,
            "direct_url": json.loads(direct_url) if direct_url else None}


def load_configuration(root):
    if not root.is_dir():
        raise QualityError(f"Repository root is not a directory: {root}")
    path = (root / "tools/quality.json").resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise QualityError(f"Expected owned tools/quality.json under root: {root}")
    try:
        content = path.read_bytes()
        declaration = json.loads(content)
    except (OSError, ValueError) as error:
        raise QualityError(f"Invalid tools/quality.json: {error}") from error
    policy_bytes = resources.files("xgen_quality").joinpath("policy.json").read_bytes()
    policy = json.loads(policy_bytes)
    required = {"schema_version", "standard_version", "quality_version",
                "public_headers", "production_directories"}
    optional = {"coverage", "scope", "test_label", "quality_source"}
    if not isinstance(declaration, dict):
        raise QualityError("tools/quality.json must contain an object")
    if unknown := declaration.keys() - required - optional:
        raise QualityError(f"Unknown configuration fields: {', '.join(sorted(unknown))}")
    if missing := required - declaration.keys():
        raise QualityError(f"Missing configuration fields: {', '.join(sorted(missing))}")
    for field, expected in (("schema_version", 1), ("standard_version", policy["standard_version"]),
                            ("quality_version", __version__)):
        if type(declaration[field]) is not type(expected) or declaration[field] != expected:
            raise QualityError(f"Expected {field} {expected!r}, got {declaration[field]!r}")
    for section in ("scope", "coverage"):
        override = declaration.get(section, {})
        if not isinstance(override, dict) or override.keys() - policy[section].keys():
            raise QualityError(f"Invalid {section} override")
        policy[section].update(override)
    for field, values in policy["scope"].items():
        if not isinstance(values, list) or not all(isinstance(value, str) and value for value in values):
            raise QualityError(f"scope.{field} must be an array of nonempty strings")
    default_exclusions = json.loads(policy_bytes)["scope"]["excluded_directories"]
    policy["scope"]["excluded_directories"] = sorted(set(
        policy["scope"]["excluded_directories"] + default_exclusions))
    for metric, threshold in policy["coverage"].items():
        if type(threshold) not in (int, float) or not 80 <= threshold <= 100:
            raise QualityError(f"coverage.{metric} must be between 80 and 100")
    label = declaration.get("test_label", policy["test_label"])
    if not isinstance(label, str) or not label.strip():
        raise QualityError("test_label must be a nonempty expression")
    try:
        re.compile(label)
    except re.error as error:
        raise QualityError(f"Invalid test_label: {error}") from error
    policy["test_label"] = label
    for field in ("public_headers", "production_directories"):
        paths = declaration[field]
        if not isinstance(paths, list):
            raise QualityError(f"{field} must be an explicit array of repository-relative paths")
        validated = []
        for value in paths:
            if not isinstance(value, str) or not value or "\n" in value or '"' in value:
                raise QualityError(f"Invalid {field} path: {value!r}")
            relative = Path(value)
            resolved = (root / relative).resolve()
            if (relative.is_absolute() or not relative.parts or ".." in relative.parts or
                    not resolved.is_relative_to(root) or resolved == root or
                    any(part in policy["scope"]["excluded_directories"] for part in relative.parts)):
                raise QualityError(f"Invalid {field} path: {value!r}")
            if field == "production_directories" and resolved.exists() and not resolved.is_dir():
                raise QualityError(f"{field} requires directories: {value!r}")
            if resolved in validated:
                raise QualityError(f"Duplicate {field} path: {value!r}")
            validated.append(resolved)
            if relative.parts[0] not in policy["scope"]["directories"]:
                policy["scope"]["directories"].append(relative.parts[0])
        policy[field] = paths
    source = declaration.get("quality_source")
    if source is not None and (not isinstance(source, dict) or set(source) != {"revision"} or
                               not isinstance(source["revision"], str) or
                               not re.fullmatch(r"[0-9a-fA-F]{40}", source["revision"])):
        raise QualityError("quality_source requires one full 40-hex revision")
    policy["quality_source"] = source
    identity = {
        "quality_version": __version__,
        "configuration": {"source": "tools/quality.json", "sha256": hashlib.sha256(content).hexdigest()},
        "policy": {"source": "xgen_quality/policy.json", "sha256": hashlib.sha256(policy_bytes).hexdigest()},
        "declared_quality_source": source,
        "installation": installation_identity(),
    }
    return policy, identity
