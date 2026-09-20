"""Portability hygiene test: scan for developer-specific paths."""

import subprocess
from pathlib import Path


def test_no_private_paths_in_source():
    """Scan tracked files for private home directory paths."""
    repo_root = Path(__file__).parent.parent.parent

    # Files/directories to scan
    scan_targets = [
        "src/",
        "tests/",
        "profiles/",
        "docs/",
        "README.md",
        "ARCHITECTURE.md",
        "SPEC.md",
    ]

    # Forbidden patterns
    forbidden = [
        "/home/zacch",
    ]

    violations = []

    for target in scan_targets:
        target_path = repo_root / target
        if not target_path.exists():
            continue

        # Get list of tracked files
        try:
            result = subprocess.run(
                ["git", "ls-files", target],
                cwd=repo_root,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                continue

            files = result.stdout.strip().splitlines()
        except (subprocess.TimeoutExpired, FileNotFoundError):
            continue

        for file in files:
            file_path = repo_root / file
            if not file_path.exists():
                continue

            # Skip binary files
            if file_path.suffix in [".gguf", ".bin", ".png", ".jpg", ".jpeg"]:
                continue

            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
            except (OSError, UnicodeDecodeError):
                continue

            for pattern in forbidden:
                if pattern in content:
                    violations.append(f"{file}: contains '{pattern}'")

    assert not violations, f"Private paths found: {violations}"


def test_no_private_model_name_in_source():
    """Scan for the specific private model name."""
    repo_root = Path(__file__).parent.parent.parent

    # The specific model name that should not be in public docs
    model_name = "Qwen3.8-27B-TTURBO-Fable-C-Fusion-709-L-Uncen-NM-DAU-NEO-MTP-IQ4_XS"

    scan_targets = [
        "src/",
        "tests/",
        "profiles/",
        "docs/",
        "README.md",
    ]

    violations = []

    for target in scan_targets:
        target_path = repo_root / target
        if not target_path.exists():
            continue

        try:
            result = subprocess.run(
                ["git", "ls-files", target],
                cwd=repo_root,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                continue

            files = result.stdout.strip().splitlines()
        except (subprocess.TimeoutExpired, FileNotFoundError):
            continue

        for file in files:
            file_path = repo_root / file
            if not file_path.exists():
                continue

            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
            except (OSError, UnicodeDecodeError):
                continue

            if model_name in content:
                violations.append(f"{file}: contains private model name")

    assert not violations, f"Private model name found: {violations}"