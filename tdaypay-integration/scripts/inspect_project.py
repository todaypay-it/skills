#!/usr/bin/env python3
"""Inspect a project without exposing file contents or secrets."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

MANIFESTS = (
    "package.json", "pyproject.toml", "requirements.txt", "go.mod", "pom.xml",
    "build.gradle", "build.gradle.kts", "composer.json", "Gemfile", "Cargo.toml",
)
SKIP_DIRS = {
    ".git", ".idea", ".vscode", "node_modules", "vendor", "dist", "build",
    "target", ".next", ".venv", "venv", "__pycache__", "coverage",
}
LANGUAGES = {
    ".ts": "TypeScript", ".tsx": "TypeScript", ".js": "JavaScript", ".jsx": "JavaScript",
    ".py": "Python", ".java": "Java", ".kt": "Kotlin", ".go": "Go", ".cs": "C#",
    ".php": "PHP", ".rb": "Ruby", ".rs": "Rust", ".scala": "Scala",
}
SIGNALS = {
    "frameworks": {
        "next": "Next.js", "@nestjs/core": "NestJS", "express": "Express", "fastify": "Fastify",
        "django": "Django", "fastapi": "FastAPI", "flask": "Flask", "spring-boot": "Spring Boot",
        "laravel": "Laravel", "rails": "Rails", "gin-gonic": "Gin",
    },
    "http": {
        "axios": "Axios", "undici": "Undici", "httpx": "HTTPX", "requests": "Requests",
        "aiohttp": "aiohttp", "okhttp": "OkHttp", "guzzle": "Guzzle", "restsharp": "RestSharp",
        "webclient": "Spring WebClient", "restclient": "Spring RestClient",
    },
    "validation": {
        "zod": "Zod", "joi": "Joi", "class-validator": "class-validator",
        "pydantic": "Pydantic", "marshmallow": "Marshmallow", "hibernate-validator": "Bean Validation",
        "fluentvalidation": "FluentValidation",
    },
    "tests": {
        "jest": "Jest", "vitest": "Vitest", "pytest": "pytest", "junit": "JUnit",
        "testify": "testify", "xunit": "xUnit", "nunit": "NUnit", "phpunit": "PHPUnit",
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--max-code-files", type=int, default=400)
    return parser.parse_args()


def safe_files(root: Path, max_files: int) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if any(part in SKIP_DIRS for part in path.relative_to(root).parts):
            continue
        if path.is_file() and path.suffix.lower() in LANGUAGES and path.stat().st_size <= 512_000:
            files.append(path)
            if len(files) >= max_files:
                break
    return files


def read_limited(path: Path, limit: int = 1_000_000) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")[:limit]
    except OSError:
        return ""


def manifest_texts(root: Path) -> tuple[list[str], str]:
    found: list[str] = []
    texts: list[str] = []
    for name in MANIFESTS:
        candidates = [root / name]
        if name == "requirements.txt":
            candidates.extend(sorted(root.glob("requirements*.txt")))
        for path in candidates:
            if path.is_file():
                relative = str(path.relative_to(root))
                if relative not in found:
                    found.append(relative)
                    texts.append(read_limited(path).lower())
    return found, "\n".join(texts)


def dependency_signals(manifest_text: str) -> dict[str, list[str]]:
    return {
        category: sorted({label for needle, label in values.items() if needle in manifest_text})
        for category, values in SIGNALS.items()
    }


def style_summary(files: list[Path]) -> dict[str, Any]:
    indent_widths: Counter[int] = Counter()
    quote_counts = {"single": 0, "double": 0}
    semicolon_lines = 0
    code_lines = 0
    for path in files[:100]:
        text = read_limited(path, 120_000)
        for line in text.splitlines()[:1000]:
            if not line.strip():
                continue
            code_lines += 1
            match = re.match(r"^( +)\S", line)
            if match:
                width = len(match.group(1))
                if width <= 8:
                    indent_widths[width] += 1
            if path.suffix.lower() in {".js", ".jsx", ".ts", ".tsx"}:
                quote_counts["single"] += len(re.findall(r"(?<!\\)'[^'\n]*'", line))
                quote_counts["double"] += len(re.findall(r'(?<!\\)"[^"\n]*"', line))
                semicolon_lines += int(line.rstrip().endswith(";"))
    indent = indent_widths.most_common(1)[0][0] if indent_widths else None
    quote_style = None
    if quote_counts["single"] + quote_counts["double"]:
        quote_style = "single" if quote_counts["single"] >= quote_counts["double"] else "double"
    return {
        "indentSpacesObserved": indent,
        "javascriptQuoteStyleObserved": quote_style,
        "javascriptSemicolonRatio": round(semicolon_lines / code_lines, 3) if code_lines else None,
        "note": "Observed style is heuristic; confirm against formatter/linter configuration and nearby production code.",
    }


def integration_candidates(root: Path, files: list[Path]) -> list[str]:
    pattern = re.compile(r"(payment|payout|gateway|provider|client|webhook|callback)", re.IGNORECASE)
    return [str(path.relative_to(root)) for path in files if pattern.search(path.name)][:30]


def main() -> int:
    args = parse_args()
    root = args.root.expanduser().resolve()
    if not root.is_dir():
        raise SystemExit(f"error: project root is not a directory: {root}")
    manifests, manifest_text = manifest_texts(root)
    files = safe_files(root, args.max_code_files)
    language_counts = Counter(LANGUAGES[path.suffix.lower()] for path in files)
    result = {
        "root": str(root),
        "manifests": manifests,
        "languagesByFileCount": dict(language_counts.most_common()),
        "primaryLanguage": language_counts.most_common(1)[0][0] if language_counts else None,
        "dependencySignals": dependency_signals(manifest_text),
        "style": style_summary(files),
        "nearbyIntegrationCandidates": integration_candidates(root, files),
        "filesSampled": len(files),
        "nextChecks": [
            "Inspect the closest production integration module and its tests.",
            "Confirm configuration, secret, logging, error, persistence, and webhook conventions.",
            "Confirm business actions, currencies, channels, idempotency owner, and status lifecycle.",
        ],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
