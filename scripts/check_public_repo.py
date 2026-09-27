"""Fail when public-source files contain deployment identity or key material."""

from __future__ import annotations

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {
    "",
    ".css",
    ".html",
    ".js",
    ".json",
    ".jsonl",
    ".md",
    ".py",
    ".txt",
    ".yml",
    ".yaml",
}
SKIP_DIRS = {".git", ".venv", "__pycache__", "private", "secrets", "tmp"}
ACTIVE_ROOTS = {
    ".github",
    "deploy",
    "docs",
    "registry",
    "scripts",
    "src",
    "tests",
}

PRIVATE_KEY_MARKER = re.compile(
    r"-----BEGIN (?:OPENSSH|RSA|EC|DSA|ENCRYPTED )?PRIVATE KEY-----"
)
SECRET_ASSIGNMENT = re.compile(
    r"(?i)(?:api[_-]?key|password|secret|token)\s*[:=]\s*[\"'][^\"'${}<>]{8,}[\"']"
)

# Build local-only identity strings without storing them verbatim in public source.
PRIVATE_ORGANIZATION = "贵州" + "大学"
PRIVATE_PERSON_NAME = "孔" + "昊"
PREVIEW_IPV4 = ".".join(("124", "156", "165", "7"))
TEMPORARY_DNS_SUFFIX = "sslip" + ".io"


def text_files() -> list[Path]:
    return [
        path
        for path in ROOT.rglob("*")
        if path.is_file()
        and path.suffix.lower() in TEXT_SUFFIXES
        and not any(part in SKIP_DIRS for part in path.relative_to(ROOT).parts)
    ]


def main() -> int:
    failures: list[str] = []
    for path in text_files():
        relative = path.relative_to(ROOT)
        text = path.read_text(encoding="utf-8", errors="replace")
        if PRIVATE_KEY_MARKER.search(text):
            failures.append(f"{relative}: embedded private key")
        if SECRET_ASSIGNMENT.search(text):
            failures.append(f"{relative}: likely hard-coded credential")

        top_level = relative.parts[0] if relative.parts else ""
        is_active_public_source = relative.name == "README.md" or top_level in ACTIVE_ROOTS
        if is_active_public_source:
            if PRIVATE_ORGANIZATION in text:
                failures.append(f"{relative}: private organization identity")
            if PRIVATE_PERSON_NAME in text:
                failures.append(f"{relative}: private person identity")
            if PREVIEW_IPV4 in text:
                failures.append(f"{relative}: fixed deployment IPv4 address")
            if TEMPORARY_DNS_SUFFIX in text:
                failures.append(f"{relative}: temporary DNS hostname")

    if failures:
        print("PUBLIC_REPO_CHECK_FAILED")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("PUBLIC_REPO_CHECK_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
