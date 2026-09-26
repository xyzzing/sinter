"""Portability hygiene test: scan for developer-specific paths.

These tests must themselves be clean of the literals they forbid, or they
would be their own violation. The patterns are therefore assembled at runtime
from fragments: there is no contiguous ``/home/<user>`` string in this file,
so it needs no exemption from its own scan.
"""

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent

#: Assembled, never written out: keeps this scanner out of its own results.
PRIVATE_PATH = "/" + "home" + "/" + "zacch"
PRIVATE_MODEL_NAME = "Qwen3.8-27B-" + "TTURBO-Fable-C-Fusion-709-L-Uncen-NM-DAU-NEO-" + "MTP-IQ4_XS"

BINARY_SUFFIXES = (".gguf", ".bin", ".png", ".jpg", ".jpeg")


def _tracked_files(targets):
    """Yield (repo-relative name, text) for tracked, non-binary files."""
    for target in targets:
        if not (REPO_ROOT / target).exists():
            continue
        try:
            result = subprocess.run(
                ["git", "ls-files", target],
                cwd=REPO_ROOT, capture_output=True, text=True, timeout=10,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            continue
        if result.returncode != 0:
            continue
        for file in result.stdout.strip().splitlines():
            path = REPO_ROOT / file
            if not path.exists() or path.suffix in BINARY_SUFFIXES:
                continue
            try:
                yield file, path.read_text(encoding="utf-8", errors="ignore")
            except (OSError, UnicodeDecodeError):
                continue


def _scan(targets, needle, label):
    return _violations(_tracked_files(targets), needle, label)


def _violations(files, needle, label):
    """Pure detection step, so the check itself can be tested."""
    return [f"{file}: contains {label}"
            for file, content in files if needle in content]


#: Everywhere project-authored text can live. benchmarks/ and scripts/ were
#: added after a private model name reached a setup script unnoticed: the scan
#: is only as good as its target list.
SCAN_TARGETS = ["src/", "tests/", "profiles/", "docs/", "benchmarks/",
                "scripts/", "README.md", "ARCHITECTURE.md", "SPEC.md"]


def test_no_private_paths_in_source():
    """No tracked source or test file hardcodes a developer home path."""
    targets = SCAN_TARGETS
    assert PRIVATE_PATH not in Path(__file__).read_text(), \
        "this scanner must not contain its own forbidden literal"
    violations = _scan(targets, PRIVATE_PATH, "a private home path")
    assert not violations, f"Private paths found: {violations}"


def test_no_private_model_name_in_source():
    """No tracked source file names the private model artifact."""
    targets = SCAN_TARGETS
    violations = _scan(targets, PRIVATE_MODEL_NAME, "the private model name")
    assert not violations, f"Private model name found: {violations}"


def test_detection_step_reports_a_real_violation():
    """Guard: a genuine hit must be reported, not silently swallowed."""
    forged = [("forged.py", f'PATH = "/{PRIVATE_PATH}/projects"\n'),
              ("clean.py", "PATH = '/usr/bin'\n")]
    hits = _violations(forged, PRIVATE_PATH, "a private home path")
    assert hits == ["forged.py: contains a private home path"]


def test_scan_covers_every_project_text_directory():
    """A new top-level text directory must not slip past the scan."""
    for target in ("benchmarks/", "scripts/"):
        assert target in SCAN_TARGETS, target
