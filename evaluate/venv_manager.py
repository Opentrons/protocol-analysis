"""Virtual environment management for protocol analysis."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

from evaluate.env_config import EnvironmentConfig


class VenvManager:
    """Manage virtual environments for different Opentrons versions."""

    def __init__(self, base_dir: Path = Path(".venvs")):
        """Initialize the venv manager.

        Args:
            base_dir: Base directory for storing virtual environments
        """
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.base_python = self._detect_base_python()

    def ensure_venv_exists(self, config: EnvironmentConfig) -> Path:
        """Ensure a virtual environment exists for the given configuration.

        Args:
            config: Environment configuration

        Returns:
            Path to the virtual environment's python executable

        Raises:
            RuntimeError: If venv creation or package installation fails
        """
        venv_path = self.base_dir / config.name

        if venv_path.exists():
            python_path = self._python_bin(venv_path)
            if python_path.exists():
                print(f"Virtual environment already exists: {venv_path}")

                # Cached/restored venvs can be present but unusable if their
                # base interpreter moved or was removed (common in CI caches).
                # If the interpreter can't even import stdlib, recreate.
                if not self._python_is_usable(python_path):
                    print(
                        f"Existing venv python is not usable: {python_path}. Recreating."
                    )
                    shutil.rmtree(venv_path, ignore_errors=True)
                    print(f"Creating virtual environment: {venv_path}")
                    self._create_venv(venv_path, config.python_version)
                    python_path = self._python_bin(venv_path)
                    print("Installing packages: " + ", ".join(config.install_specs))
                    self._install_packages(python_path, config.install_specs)
                    return python_path

                # If the venv exists but uses a different Python major.minor than
                # requested, recreate it. This is especially important for 'edge'
                # where we may want a newer interpreter.
                actual_mm = self._python_major_minor(python_path)
                expected_mm = config.python_version
                if actual_mm is not None and actual_mm != expected_mm:
                    print(
                        f"Existing venv python version mismatch for {venv_path}: "
                        f"expected {expected_mm}, found {actual_mm}. Recreating."
                    )
                    shutil.rmtree(venv_path, ignore_errors=True)
                    print(f"Creating virtual environment: {venv_path}")
                    self._create_venv(venv_path, config.python_version)
                    python_path = self._python_bin(venv_path)
                    print("Installing packages: " + ", ".join(config.install_specs))
                    self._install_packages(python_path, config.install_specs)
                    return python_path

                # Some earlier runs may have created the venv but failed to install
                # dependencies. Ensure opentrons is importable; if not, re-install.
                if not self._can_import(python_path, "opentrons"):
                    print(
                        "Existing venv is missing 'opentrons'; reinstalling packages: "
                        + ", ".join(config.install_specs)
                    )
                    self._install_packages(python_path, config.install_specs)
                return python_path

        print(f"Creating virtual environment: {venv_path}")
        self._create_venv(venv_path, config.python_version)

        python_path = self._python_bin(venv_path)
        if not self._python_is_usable(python_path):
            # Extremely defensive: if creation succeeded but the resulting python
            # can't even import stdlib, treat it as corrupted.
            shutil.rmtree(venv_path, ignore_errors=True)
            raise RuntimeError(f"Created venv is not usable: {python_path}")
        print("Installing packages: " + ", ".join(config.install_specs))
        self._install_packages(python_path, config.install_specs)

        return python_path

    def _can_import(self, python_path: Path, module_name: str) -> bool:
        """Return True if a module can be imported in the given interpreter."""
        try:
            subprocess.run(
                [
                    str(python_path),
                    "-c",
                    f"import {module_name}  # noqa: F401\nprint('ok')",
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
            return True
        except Exception:
            return False

    def _python_is_usable(self, python_path: Path) -> bool:
        """Return True if the interpreter can start and import stdlib.

        This specifically guards against cached/restored venvs whose base
        interpreter has moved or been removed, which can manifest as
        `ModuleNotFoundError: encodings` or other fatal startup failures.
        """

        try:
            subprocess.run(
                [
                    str(python_path),
                    "-c",
                    "import encodings, sys; print(sys.version)",
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=10,
            )
            return True
        except Exception:
            return False

    def _create_venv(self, venv_path: Path, python_version: str) -> None:
        """Create a virtual environment.

        Args:
            venv_path: Path where the venv should be created
            python_version: Python version requirement (e.g., "3.10")

        Raises:
            RuntimeError: If venv creation fails
        """
        # Prefer using `uv venv` so we can honor python_version consistently.
        # Fall back to `python -m venv` if uv isn't available.
        try:
            subprocess.run(
                ["uv", "venv", "--python", python_version, str(venv_path)],
                check=True,
                capture_output=True,
                text=True,
            )
            return
        except FileNotFoundError:
            pass
        except subprocess.CalledProcessError as e:
            # If the caller asked for a specific major.minor and uv failed,
            # do not silently fall back to whatever interpreter we have.
            base_mm = self._python_major_minor(self.base_python)
            if base_mm is None or base_mm != python_version:
                raise RuntimeError(
                    f"Failed to create venv with Python {python_version} via uv: {e.stderr}"
                ) from e
            # Otherwise, we can fall back below.

        try:
            subprocess.run(
                [str(self.base_python), "-m", "venv", str(venv_path)],
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as e:
            raise RuntimeError(
                f"Failed to create virtual environment: {e.stderr}"
            ) from e

    def _python_major_minor(self, python_path: Path) -> str | None:
        """Return interpreter major.minor (e.g. '3.12') or None if unknown."""
        try:
            proc = subprocess.run(
                [
                    str(python_path),
                    "-c",
                    "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')",
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=10,
            )
            value = (proc.stdout or "").strip()
            return value or None
        except Exception:
            return None

    def _install_packages(self, python_path: Path, install_specs: list[str]) -> None:
        """Install packages into a virtual environment.

        Args:
            python_path: Path to the venv's python executable
            install_specs: Package specifications for pip install

        Raises:
            RuntimeError: If package installation fails
        """
        current_spec = "--upgrade pip"
        try:
            # Some environments (or partial/corrupted venvs) may not have pip.
            # Try to bootstrap it via ensurepip.
            if not self._can_import(python_path, "pip"):
                subprocess.run(
                    [str(python_path), "-m", "ensurepip", "--upgrade"],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )

            # Upgrade pip first
            subprocess.run(
                [str(python_path), "-m", "pip", "install", "--upgrade", "pip"],
                check=True,
                capture_output=True,
                text=True,
                timeout=120,
            )

            # Install the specified packages (with longer timeout for git installs)
            for spec in install_specs:
                current_spec = spec
                subprocess.run(
                    [
                        str(python_path),
                        "-m",
                        "pip",
                        "install",
                        "--timeout=300",
                        spec,
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=600,
                )
        except subprocess.CalledProcessError as e:
            raise RuntimeError(
                f"Failed to install packages '{current_spec}': {e.stderr}"
            ) from e
        except subprocess.TimeoutExpired as e:
            raise RuntimeError(
                f"Package installation timed out for '{current_spec}'. "
                f"This often happens with git-based installs."
            ) from e

    def get_python_path(self, config: EnvironmentConfig) -> Path:
        """Get the Python executable path for a configuration.

        Args:
            config: Environment configuration

        Returns:
            Path to the python executable
        """
        return self._python_bin(self.base_dir / config.name)

    def _detect_base_python(self) -> Path:
        """Return the python interpreter managed by uv (fall back to sys.executable)."""

        candidates: list[Path] = []
        if os.name == "nt":
            candidates.append(Path(".venv") / "Scripts" / "python.exe")
        else:
            candidates.append(Path(".venv") / "bin" / "python")

        candidates.append(Path(sys.executable))

        for candidate in candidates:
            if candidate.exists():
                return candidate

        # Final fallback: rely on sys.executable even if path doesn't exist (will raise later)
        return Path(sys.executable)

    def _python_bin(self, venv_path: Path) -> Path:
        """Get the python binary inside a venv (handles POSIX/Windows)."""

        if os.name == "nt":
            return venv_path / "Scripts" / "python.exe"
        return venv_path / "bin" / "python"
