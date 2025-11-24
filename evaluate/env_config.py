"""Environment configuration for different Opentrons versions."""

from dataclasses import dataclass
from pathlib import Path


@dataclass
class EnvironmentConfig:
    """Configuration for a specific Opentrons analysis environment."""

    name: str
    python_version: str
    venv_path: Path
    install_specs: list[str]  # pip install specifications (run in order)


# Map robot server versions to their environment configurations
ENVIRONMENT_CONFIGS = {
    "8.0.0": EnvironmentConfig(
        name="opentrons-8.0.0",
        python_version="3.10",
        venv_path=Path(".venvs/opentrons-8.0.0"),
        install_specs=["opentrons==8.0.0", "pandas==1.4.3"],
    ),
    "8.2.0": EnvironmentConfig(
        name="opentrons-8.2.0",
        python_version="3.10",
        venv_path=Path(".venvs/opentrons-8.2.0"),
        install_specs=["opentrons==8.2.0", "pandas==1.4.3"],
    ),
    "8.3.0": EnvironmentConfig(
        name="opentrons-8.3.0",
        python_version="3.10",
        venv_path=Path(".venvs/opentrons-8.3.0"),
        install_specs=["opentrons==8.3.0", "pandas==1.4.3"],
    ),
    "8.4.0": EnvironmentConfig(
        name="opentrons-8.4.0",
        python_version="3.10",
        venv_path=Path(".venvs/opentrons-8.4.0"),
        install_specs=["opentrons==8.4.0", "pandas==1.4.3"],
    ),
    "8.5.0": EnvironmentConfig(
        name="opentrons-8.5.0",
        python_version="3.10",
        venv_path=Path(".venvs/opentrons-8.5.0"),
        install_specs=["opentrons==8.5.0", "pandas==1.4.3"],
    ),
    "8.6.0": EnvironmentConfig(
        name="opentrons-8.6.0",
        python_version="3.10",
        venv_path=Path(".venvs/opentrons-8.6.0"),
        install_specs=["opentrons==8.6.0", "pandas==1.4.3"],
    ),
    "8.7.0": EnvironmentConfig(
        name="opentrons-8.7.0",
        python_version="3.10",
        venv_path=Path(".venvs/opentrons-8.7.0"),
        install_specs=["opentrons==8.7.0", "pandas==1.4.3"],
    ),
    "next": EnvironmentConfig(
        name="opentrons-next",
        python_version="3.10",
        venv_path=Path(".venvs/opentrons-next"),
        install_specs=["opentrons==8.8.0a9", "pandas==1.4.3"],
    ),
}


def get_environment_for_version(robot_version: str) -> EnvironmentConfig:
    """Get the environment configuration for a robot server version.

    Args:
        robot_version: The robot server version (e.g., "8.7.0")

    Returns:
        EnvironmentConfig for the specified version

    Raises:
        ValueError: If the version is not supported
    """
    if robot_version not in ENVIRONMENT_CONFIGS:
        supported = ", ".join(ENVIRONMENT_CONFIGS.keys())
        raise ValueError(
            f"Unsupported robot server version: {robot_version}. "
            f"Supported versions: {supported}"
        )
    return ENVIRONMENT_CONFIGS[robot_version]


def get_supported_versions() -> list[str]:
    """Get list of supported robot server versions.

    Returns:
        List of version strings
    """
    return list(ENVIRONMENT_CONFIGS.keys())
