"""Sinter interactive setup wizard.

Menu-based CLI for installing and integrating llama.cpp with Sinter,
detecting existing installations, and configuring profiles.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from sinter.config import ProfileSpec, load_config, save_config


@dataclass
class InstallationInfo:
    """Detected installation information."""
    llama_server_binary: Optional[Path] = None
    llama_server_version: Optional[str] = None
    systemd_service: Optional[str] = None
    running_process: Optional[dict] = None
    model_files: list[Path] = field(default_factory=list)
    config_file: Optional[Path] = None


def clear_screen() -> None:
    """Clear terminal screen."""
    os.system("clear")


def print_banner() -> None:
    """Print Sinter setup banner."""
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║              SINTER INTERACTIVE SETUP WIZARD               ║")
    print("║         Local 27B LLM Inference on 24GB GPU               ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print()


def detect_installation() -> InstallationInfo:
    """Detect existing llama.cpp installation and configuration."""
    info = InstallationInfo()

    # Check for existing Sinter config
    config = load_config()
    if config.config_dir.exists():
        info.config_file = config.config_dir / "config.toml"

    # Search for llama-server binary
    search_paths = [
        "/usr/local/bin/llama-server",
        "/usr/bin/llama-server",
        Path.home() / "llama.cpp/build/bin/llama-server",
        Path.home() / "llama_rocmfpx_build/ROCmFPX/build/bin/llama-server",
    ]
    for path in search_paths:
        if Path(path).exists():
            info.llama_server_binary = Path(path)
            break

    # Also check PATH
    if info.llama_server_binary is None:
        found = shutil.which("llama-server")
        if found:
            info.llama_server_binary = Path(found)

    # Try to get version
    if info.llama_server_binary:
        try:
            result = subprocess.run(
                [str(info.llama_server_binary), "--version"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                info.llama_server_version = result.stdout.strip()
        except (subprocess.TimeoutExpired, OSError):
            pass

    # Check for systemd service
    try:
        result = subprocess.run(
            ["systemctl", "--user", "list-units", "--type=service", "--all"],
            capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.splitlines():
            if "llama" in line.lower() and "service" in line.lower():
                # Extract service name
                parts = line.split()
                if parts:
                    info.systemd_service = parts[0]
                    break
    except (subprocess.TimeoutExpired, OSError):
        pass

    # Check for running llama-server processes
    try:
        result = subprocess.run(
            ["pgrep", "-a", "llama-server"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            for line in result.stdout.strip().splitlines():
                parts = line.split(maxsplit=1)
                if len(parts) == 2:
                    info.running_process = {
                        "pid": int(parts[0]),
                        "cmdline": parts[1],
                    }
                    break
    except (subprocess.TimeoutExpired, OSError):
        pass

    # Search for model files
    model_dirs = [
        Path.home() / ".local/share/sinter/models",
        Path.home() / "models",
        Path.home() / ".cache/sinter/models",
    ]
    for model_dir in model_dirs:
        if model_dir.exists():
            for f in model_dir.rglob("*.gguf"):
                info.model_files.append(f)
            for f in model_dir.rglob("*.bin"):
                info.model_files.append(f)

    return info


def install_llama_cpp() -> bool:
    """Install llama.cpp from source."""
    print("Installing llama.cpp from source...")
    print("This may take several minutes.")
    print()

    # Check for dependencies
    deps = ["git", "cmake", "make", "g++"]
    missing = []
    for dep in deps:
        if shutil.which(dep) is None:
            missing.append(dep)

    if missing:
        print(f"Missing dependencies: {', '.join(missing)}")
        print("Please install them first:")
        print(f"  sudo dnf install {' '.join(missing)}")
        print()
        return False

    # Clone repo
    repo_dir = Path.home() / "llama.cpp"
    if not repo_dir.exists():
        print(f"Cloning llama.cpp to {repo_dir}...")
        try:
            subprocess.run(
                ["git", "clone", "https://github.com/ggerganov/llama.cpp.git", str(repo_dir)],
                check=True
            )
        except subprocess.CalledProcessError as e:
            print(f"Failed to clone repo: {e}")
            return False

    # Build
    print("Building llama.cpp...")
    build_dir = repo_dir / "build"
    build_dir.mkdir(exist_ok=True)

    try:
        subprocess.run(
            ["cmake", "-B", str(build_dir), "-DCMAKE_BUILD_TYPE=Release"],
            cwd=repo_dir, check=True
        )
        subprocess.run(
            ["cmake", "--build", str(build_dir), "-j", str(os.cpu_count())],
            cwd=repo_dir, check=True
        )
    except subprocess.CalledProcessError as e:
        print(f"Failed to build: {e}")
        return False

    # Verify
    server_binary = build_dir / "bin" / "llama-server"
    if server_binary.exists():
        print(f"llama-server built successfully: {server_binary}")
        return True
    else:
        print("Build completed but llama-server not found.")
        return False


def download_model() -> bool:
    """Download a 27B model."""
    print("Downloading 27B model...")
    print("Options:")
    print("  1. Qwen-2.5-27B (GGUF Q4_K_M) - ~14.5GB")
    print("  2. Llama-3.1-27B (GGUF Q4_K_M) - ~15GB")
    print("  3. Custom URL")
    print()

    choice = input("Select option (1-3): ").strip()

    model_dir = Path.home() / ".local/share/sinter/models"
    model_dir.mkdir(parents=True, exist_ok=True)

    if choice == "1":
        url = "https://huggingface.co/Qwen/Qwen2.5-27B-GGUF/resolve/main/qwen2.5-27b-q4_k_m.gguf"
        filename = "qwen2.5-27b-q4_k_m.gguf"
    elif choice == "2":
        url = "https://huggingface.co/meta-llama/Llama-3.1-27B-GGUF/resolve/main/llama-3.1-27b-q4_k_m.gguf"
        filename = "llama-3.1-27b-q4_k_m.gguf"
    elif choice == "3":
        url = input("Enter model URL: ").strip()
        filename = url.split("/")[-1]
    else:
        print("Invalid choice.")
        return False

    target = model_dir / filename
    print(f"Downloading to {target}...")

    try:
        subprocess.run(
            ["wget", "-c", "-O", str(target), url],
            check=True
        )
        print(f"Downloaded: {target}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Download failed: {e}")
        return False


def configure_profile(binary: Path, model: Path) -> bool:
    """Configure Sinter profile for the detected installation."""
    print("Configuring Sinter profile...")

    config = load_config()

    # Generate profile alias
    model_name = model.name.replace(".gguf", "").replace(".bin", "")
    alias = re.sub(r"[^a-z0-9_-]", "-", model_name.lower())[:20]

    profile = ProfileSpec(
        alias=alias,
        weights_path=model,
        backend_binary=binary,
    )

    config.profiles[alias] = profile
    config.default_profile = alias

    save_config(config)
    print(f"Profile '{alias}' configured in {config.config_dir / 'config.toml'}")
    return True


def test_connection(port: int = 8080, timeout: int = 5) -> bool:
    """Test connection to llama-server."""
    import urllib.request

    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/health", timeout=timeout
        ) as response:
            if response.status == 200:
                print(f"✓ Connected to llama-server on port {port}")
                return True
    except Exception as e:
        print(f"✗ Failed to connect: {e}")

    return False


def show_status(info: InstallationInfo) -> None:
    """Display detected installation status."""
    print("══════════════════════════════════════════════════════════════")
    print("DETECTED INSTALLATION STATUS")
    print("══════════════════════════════════════════════════════════════")
    print()

    if info.llama_server_binary:
        print(f"✓ llama-server binary: {info.llama_server_binary}")
        if info.llama_server_version:
            print(f"  Version: {info.llama_server_version}")
    else:
        print("✗ llama-server binary: NOT FOUND")

    if info.systemd_service:
        print(f"✓ systemd service: {info.systemd_service}")
    else:
        print("✗ systemd service: NOT FOUND")

    if info.running_process:
        print(f"✓ Running process: PID {info.running_process['pid']}")
        print(f"  Command: {info.running_process['cmdline'][:80]}...")
    else:
        print("✗ Running process: NOT FOUND")

    if info.model_files:
        print(f"✓ Model files found: {len(info.model_files)}")
        for model in info.model_files[:5]:
            print(f"  - {model}")
    else:
        print("✗ Model files: NOT FOUND")

    if info.config_file and info.config_file.exists():
        print(f"✓ Sinter config: {info.config_file}")
    else:
        print("✗ Sinter config: NOT FOUND")

    print()


def run_setup_wizard() -> int:
    """Run the interactive setup wizard."""
    while True:
        clear_screen()
        print_banner()

        print("Main Menu:")
        print("  1. Detect existing installation")
        print("  2. Install llama.cpp")
        print("  3. Download 27B model")
        print("  4. Configure Sinter profile")
        print("  5. Test connection")
        print("  6. Exit")
        print()

        choice = input("Select option (1-6): ").strip()

        if choice == "1":
            print("Detecting installation...")
            info = detect_installation()
            show_status(info)
            input("Press Enter to continue...")

        elif choice == "2":
            if install_llama_cpp():
                print("Installation successful!")
            else:
                print("Installation failed.")
            input("Press Enter to continue...")

        elif choice == "3":
            if download_model():
                print("Model downloaded successfully!")
            else:
                print("Download failed.")
            input("Press Enter to continue...")

        elif choice == "4":
            info = detect_installation()
            if info.llama_server_binary and info.model_files:
                model = info.model_files[0]
                if configure_profile(info.llama_server_binary, model):
                    print("Profile configured successfully!")
                else:
                    print("Profile configuration failed.")
            else:
                print("Need llama-server binary and model file first.")
                print("Run options 2 and 3.")
            input("Press Enter to continue...")

        elif choice == "5":
            port = input("Port (default 8080): ").strip()
            if not port:
                port = "8080"
            if test_connection(int(port)):
                print("Connection test passed!")
            else:
                print("Connection test failed.")
            input("Press Enter to continue...")

        elif choice == "6":
            print("Goodbye!")
            return 0

        else:
            print("Invalid choice.")
            input("Press Enter to continue...")

    return 0


if __name__ == "__main__":
    sys.exit(run_setup_wizard())
