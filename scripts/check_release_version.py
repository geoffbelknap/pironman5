#!/usr/bin/env python3
import argparse
import ast
import re
import sys
from pathlib import Path


VERSION_RE = re.compile(
    r"^"
    r"(?P<release>\d+(?:\.\d+)*)"
    r"(?P<pre>(a|b|rc)\d+)?"
    r"(?P<post>\.post\d+)?"
    r"(?P<dev>\.dev\d+)?"
    r"(?P<local>\+[a-z0-9]+(?:[._-][a-z0-9]+)*)?"
    r"$",
    re.IGNORECASE,
)


def read_version(path):
    module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in module.body:
        if isinstance(node, ast.Assign):
            names = [target.id for target in node.targets if isinstance(target, ast.Name)]
            if "__version__" in names and isinstance(node.value, ast.Constant):
                if isinstance(node.value.value, str):
                    return node.value.value
    raise ValueError(f"Could not find __version__ in {path}")


def fail(message):
    print(message, file=sys.stderr)
    return 1


def main(argv=None):
    parser = argparse.ArgumentParser(description="Validate release version metadata")
    parser.add_argument("--version-file", default="pironman5/version.py", help="Path to the package version file")
    parser.add_argument("--tag", help="Expected git tag, for example v1.0.1")
    parser.add_argument("--stable", action="store_true", help="Require a stable public release version")
    args = parser.parse_args(argv)

    try:
        version = read_version(Path(args.version_file))
    except (OSError, SyntaxError, ValueError) as exc:
        return fail(str(exc))

    match = VERSION_RE.match(version)
    if not match:
        return fail(f"Invalid version: {version}")

    if args.tag and args.tag != f"v{version}":
        return fail(f"Tag {args.tag} does not match version {version}; expected v{version}")

    if args.stable:
        if match.group("local"):
            return fail("stable releases must not use local version metadata")
        if match.group("dev"):
            return fail("stable releases must not use dev versions")
        if match.group("pre"):
            return fail("stable releases must not use prerelease versions")

    print(f"version ok: {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
