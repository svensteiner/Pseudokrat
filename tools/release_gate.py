"""Fail-closed release metadata and packaging consistency checks."""

from __future__ import annotations

import argparse
import ast
import os
import re
import sys
import tomllib
from pathlib import Path

VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:[A-Za-z0-9.+-]*)?$")


def project_version(repo_root: Path) -> str:
    with (repo_root / "pyproject.toml").open("rb") as handle:
        version = tomllib.load(handle)["project"]["version"]
    if not isinstance(version, str) or not VERSION_RE.fullmatch(version):
        raise ValueError(f"Ungültige Projektversion: {version!r}")
    return version


def package_version(repo_root: Path) -> str:
    source = (repo_root / "src" / "pseudokrat" / "__init__.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if any(
            isinstance(target, ast.Name) and target.id == "__version__" for target in node.targets
        ):
            value = ast.literal_eval(node.value)
            if isinstance(value, str):
                return value
    raise ValueError("__version__ fehlt in src/pseudokrat/__init__.py")


def validate_release(repo_root: Path, *, tag: str | None = None) -> list[str]:
    """Return all release-blocking errors; an empty list means pass."""
    errors: list[str] = []
    try:
        version = project_version(repo_root)
    except (KeyError, OSError, ValueError, tomllib.TOMLDecodeError) as exc:
        return [str(exc)]

    try:
        runtime_version = package_version(repo_root)
    except (OSError, SyntaxError, ValueError) as exc:
        errors.append(str(exc))
    else:
        if runtime_version != version:
            errors.append(
                f"Versionsdrift: pyproject.toml={version}, pseudokrat.__version__={runtime_version}"
            )

    if tag is not None and tag != f"v{version}":
        errors.append(f"Tag {tag!r} passt nicht zur Projektversion v{version}.")

    required_files = (
        "LICENSE",
        "README.md",
        "packaging/pseudokrat.spec",
        "packaging/installer.iss",
        "packaging/build_windows.ps1",
        "packaging/sign_windows.ps1",
        "packaging/gumroad/START.bat",
    )
    for relative in required_files:
        if not (repo_root / relative).is_file():
            errors.append(f"Release-Datei fehlt: {relative}")

    text_files = {
        relative: (repo_root / relative).read_text(encoding="utf-8-sig")
        for relative in required_files
        if (repo_root / relative).is_file()
    }
    installer = text_files.get("packaging/installer.iss", "")
    if 'GetEnv("PSEUDOKRAT_VERSION")' not in installer:
        errors.append("installer.iss bezieht die Version nicht aus PSEUDOKRAT_VERSION.")
    if "--file" in installer:
        errors.append("installer.iss verwendet die nicht existente CLI-Option --file.")
    if "pseudokrat.example.com" in installer or "CHANGEME" in installer:
        errors.append("installer.iss enthält eine Platzhalter-URL.")

    spec = text_files.get("packaging/pseudokrat.spec", "")
    if 'tomllib.load(_pyproject_file)["project"]["version"]' not in spec:
        errors.append("PyInstaller-Spec liest die kanonische Projektversion nicht.")

    build_script = text_files.get("packaging/build_windows.ps1", "")
    if '"PyInstaller==6.18.0"' not in build_script:
        errors.append("Windows-Build pinnt PyInstaller nicht exakt.")
    if "PSEUDOKRAT_VERSION = $Version" not in build_script:
        errors.append("Windows-Build übergibt die kanonische Version nicht an Inno Setup.")

    start_script = text_files.get("packaging/gumroad/START.bat", "")
    if "exit /b %RC%" not in start_script:
        errors.append("Portable START.bat propagiert den Programm-Exitcode nicht.")

    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--tag", default=None, help="Erwarteter Release-Tag (v<version>).")
    parser.add_argument(
        "--tag-from-env",
        action="store_true",
        help="GITHUB_REF_NAME als verpflichtenden Release-Tag prüfen.",
    )
    args = parser.parse_args(argv)
    tag = os.environ.get("GITHUB_REF_NAME") if args.tag_from_env else args.tag
    if args.tag_from_env and not tag:
        print("RELEASE BLOCKED: GITHUB_REF_NAME fehlt.", file=sys.stderr)
        return 2

    errors = validate_release(args.repo_root.resolve(), tag=tag)
    if errors:
        for error in errors:
            print(f"RELEASE BLOCKED: {error}", file=sys.stderr)
        return 1
    print(f"Release-Gate OK: Pseudokrat {project_version(args.repo_root.resolve())}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
