#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = ROOT / "VERSION"
SEMVER_PATTERN = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-([0-9A-Za-z.-]+))?$")
APP_CONFIG_PATTERN = re.compile(
    r'(app_version:\s*str\s*=\s*Field\(default=")([^"]+)(",\s*validation_alias="APP_VERSION"\))'
)
DOCKER_APP_VERSION_PATTERN = re.compile(r"(^ARG APP_VERSION=)([^\n]+)$", re.MULTILINE)


@dataclass(frozen=True)
class ParsedVersion:
    major: int
    minor: int
    patch: int
    prerelease: str | None


@dataclass(frozen=True)
class VersionTarget:
    label: str
    path: Path
    read_versions: Callable[[Path], list[str]]
    write_version: Callable[[Path, str], None]


def read_version_file() -> str:
    version = VERSION_FILE.read_text(encoding="utf-8").strip()
    validate_version(version)
    return version


def write_version_file(version: str) -> None:
    VERSION_FILE.write_text(f"{version}\n", encoding="utf-8")


def validate_version(version: str) -> ParsedVersion:
    match = SEMVER_PATTERN.fullmatch(version)
    if match is None:
        raise ValueError(
            "Version must follow semver-style 'X.Y.Z' or 'X.Y.Z-prerelease'. "
            f"Received '{version}'."
        )
    major, minor, patch, prerelease = match.groups()
    return ParsedVersion(
        major=int(major),
        minor=int(minor),
        patch=int(patch),
        prerelease=prerelease,
    )


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def read_package_json_versions(path: Path) -> list[str]:
    return [str(read_json(path)["version"])]


def write_package_json_version(path: Path, version: str) -> None:
    payload = read_json(path)
    payload["version"] = version
    write_json(path, payload)


def read_package_lock_versions(path: Path) -> list[str]:
    payload = read_json(path)
    versions = [str(payload["version"])]
    root_package = payload.get("packages", {}).get("")
    if isinstance(root_package, dict) and "version" in root_package:
        versions.append(str(root_package["version"]))
    return versions


def write_package_lock_version(path: Path, version: str) -> None:
    payload = read_json(path)
    payload["version"] = version
    packages = payload.get("packages")
    if isinstance(packages, dict):
        root_package = packages.get("")
        if isinstance(root_package, dict):
            root_package["version"] = version
    write_json(path, payload)


def read_config_versions(path: Path) -> list[str]:
    contents = path.read_text(encoding="utf-8")
    match = APP_CONFIG_PATTERN.search(contents)
    if match is None:
        raise ValueError(f"Unable to find APP_VERSION default in {path}.")
    return [match.group(2)]


def write_config_version(path: Path, version: str) -> None:
    contents = path.read_text(encoding="utf-8")
    updated, replacements = APP_CONFIG_PATTERN.subn(rf"\g<1>{version}\g<3>", contents)
    if replacements != 1:
        raise ValueError(f"Expected to update exactly one APP_VERSION default in {path}, updated {replacements}.")
    path.write_text(updated, encoding="utf-8")


def read_dockerfile_versions(path: Path) -> list[str]:
    return [match.group(2) for match in DOCKER_APP_VERSION_PATTERN.finditer(path.read_text(encoding="utf-8"))]


def write_dockerfile_version(path: Path, version: str) -> None:
    contents = path.read_text(encoding="utf-8")
    updated, replacements = DOCKER_APP_VERSION_PATTERN.subn(rf"\g<1>{version}", contents)
    if replacements == 0:
        raise ValueError(f"Unable to find any APP_VERSION ARG lines in {path}.")
    path.write_text(updated, encoding="utf-8")


TARGETS = (
    VersionTarget(
        label="Admin package manifest",
        path=ROOT / "apps/admin-web/package.json",
        read_versions=read_package_json_versions,
        write_version=write_package_json_version,
    ),
    VersionTarget(
        label="Admin package lock",
        path=ROOT / "apps/admin-web/package-lock.json",
        read_versions=read_package_lock_versions,
        write_version=write_package_lock_version,
    ),
    VersionTarget(
        label="API settings default",
        path=ROOT / "apps/api/app/config.py",
        read_versions=read_config_versions,
        write_version=write_config_version,
    ),
    VersionTarget(
        label="Admin Dockerfile",
        path=ROOT / "apps/admin-web/Dockerfile",
        read_versions=read_dockerfile_versions,
        write_version=write_dockerfile_version,
    ),
    VersionTarget(
        label="API Dockerfile",
        path=ROOT / "apps/api/Dockerfile",
        read_versions=read_dockerfile_versions,
        write_version=write_dockerfile_version,
    ),
)


def current_versions() -> list[tuple[VersionTarget, list[str]]]:
    return [(target, target.read_versions(target.path)) for target in TARGETS]


def check_consistency(version: str) -> list[str]:
    mismatches: list[str] = []
    for target, versions in current_versions():
        if any(found != version for found in versions):
            joined = ", ".join(versions)
            mismatches.append(f"{target.label} [{target.path.relative_to(ROOT)}] has {joined}; expected {version}.")
    return mismatches


def sync_version(version: str) -> None:
    for target in TARGETS:
        target.write_version(target.path, version)


def bump_version(version: str, part: str, *, pre_label: str) -> str:
    parsed = validate_version(version)
    if part == "major":
        return f"{parsed.major + 1}.0.0"
    if part == "minor":
        return f"{parsed.major}.{parsed.minor + 1}.0"
    if part == "patch":
        return f"{parsed.major}.{parsed.minor}.{parsed.patch + 1}"
    if part == "release":
        return f"{parsed.major}.{parsed.minor}.{parsed.patch}"
    if part != "prerelease":
        raise ValueError(f"Unsupported bump part '{part}'.")

    if parsed.prerelease is None:
        return f"{parsed.major}.{parsed.minor}.{parsed.patch}-{pre_label}.1"

    prerelease_match = re.fullmatch(r"([0-9A-Za-z-]+)\.(\d+)", parsed.prerelease)
    if prerelease_match and prerelease_match.group(1) == pre_label:
        next_number = int(prerelease_match.group(2)) + 1
        return f"{parsed.major}.{parsed.minor}.{parsed.patch}-{pre_label}.{next_number}"

    return f"{parsed.major}.{parsed.minor}.{parsed.patch}-{pre_label}.1"


def command_show(_: argparse.Namespace) -> int:
    print(read_version_file())
    return 0


def command_check(_: argparse.Namespace) -> int:
    version = read_version_file()
    mismatches = check_consistency(version)
    if mismatches:
        for mismatch in mismatches:
            print(mismatch, file=sys.stderr)
        return 1
    print(f"Version files are consistent at {version}.")
    return 0


def command_sync(args: argparse.Namespace) -> int:
    version = args.version or read_version_file()
    validate_version(version)
    if args.write_version_file:
        write_version_file(version)
    sync_version(version)
    print(f"Synchronized version {version}.")
    return 0


def command_set(args: argparse.Namespace) -> int:
    version = args.version
    validate_version(version)
    if args.dry_run:
        print(version)
        return 0
    write_version_file(version)
    sync_version(version)
    print(f"Set version to {version}.")
    return 0


def command_bump(args: argparse.Namespace) -> int:
    current = read_version_file()
    next_version = bump_version(current, args.part, pre_label=args.pre_label)
    if args.dry_run:
        print(next_version)
        return 0
    write_version_file(next_version)
    sync_version(next_version)
    print(f"Bumped version from {current} to {next_version}.")
    return 0


def command_check_tag(args: argparse.Namespace) -> int:
    version = read_version_file()
    tag = args.tag.strip()
    if not tag.startswith("v"):
        print(f"Release tags must start with 'v'. Received '{tag}'.", file=sys.stderr)
        return 1
    expected = f"v{version}"
    if tag != expected:
        print(f"Release tag '{tag}' does not match VERSION '{expected}'.", file=sys.stderr)
        return 1
    print(f"Release tag {tag} matches VERSION.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage the repo's single-source application version.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    show_parser = subparsers.add_parser("show", help="Print the canonical repo version.")
    show_parser.set_defaults(func=command_show)

    check_parser = subparsers.add_parser("check", help="Fail if any version consumer drifts from VERSION.")
    check_parser.set_defaults(func=command_check)

    sync_parser = subparsers.add_parser("sync", help="Sync all version consumers from VERSION or an explicit value.")
    sync_parser.add_argument("--version", help="Version to write instead of the current VERSION file value.")
    sync_parser.add_argument(
        "--write-version-file",
        action="store_true",
        help="Also overwrite VERSION when --version is provided.",
    )
    sync_parser.set_defaults(func=command_sync)

    set_parser = subparsers.add_parser("set", help="Set VERSION and sync all consumers to an explicit version.")
    set_parser.add_argument("version", help="Explicit version value to write.")
    set_parser.add_argument("--dry-run", action="store_true", help="Print the requested version without writing files.")
    set_parser.set_defaults(func=command_set)

    bump_parser = subparsers.add_parser("bump", help="Compute the next version, write VERSION, and sync consumers.")
    bump_parser.add_argument("part", choices=("major", "minor", "patch", "prerelease", "release"))
    bump_parser.add_argument(
        "--pre-label",
        default="alpha",
        help="Prerelease label to use for prerelease bumps. Defaults to 'alpha'.",
    )
    bump_parser.add_argument("--dry-run", action="store_true", help="Print the bumped version without writing files.")
    bump_parser.set_defaults(func=command_bump)

    check_tag_parser = subparsers.add_parser("check-tag", help="Fail if a release tag does not match VERSION.")
    check_tag_parser.add_argument("tag", help="Git tag name, such as v2.0.0-alpha.1.")
    check_tag_parser.set_defaults(func=command_check_tag)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return int(args.func(args))
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
