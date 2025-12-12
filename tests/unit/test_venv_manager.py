"""Unit tests for VenvManager."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch


from evaluate.env_config import EnvironmentConfig
from evaluate.venv_manager import VenvManager


def test_ensure_venv_exists_reinstalls_if_opentrons_missing(tmp_path: Path):
    config = EnvironmentConfig(
        name="opentrons-test",
        python_version="3.10",
        venv_path=tmp_path / "unused",
        install_specs=["opentrons==8.7.0"],
    )

    manager = VenvManager(base_dir=tmp_path)
    venv_path = tmp_path / config.name
    (venv_path / "bin").mkdir(parents=True)
    python_path = venv_path / "bin" / "python"
    python_path.write_text("#!/bin/sh\nexit 0\n")

    with patch.object(manager, "_can_import", return_value=False) as can_import:
        with patch.object(manager, "_install_packages") as install:
            returned = manager.ensure_venv_exists(config)

    assert returned == python_path
    can_import.assert_called()
    install.assert_called_once()


def test_can_import_returns_false_on_subprocess_failure(tmp_path: Path):
    manager = VenvManager(base_dir=tmp_path)

    with patch("evaluate.venv_manager.subprocess.run", side_effect=Exception("boom")):
        assert manager._can_import(Path("/fake/python"), "opentrons") is False


def test_ensure_venv_exists_recreates_when_python_version_mismatch(tmp_path: Path):
    config = EnvironmentConfig(
        name="opentrons-edge",
        python_version="3.12",
        venv_path=tmp_path / "unused",
        install_specs=["opentrons==8.8.0"],
    )

    manager = VenvManager(base_dir=tmp_path)
    venv_path = tmp_path / config.name
    (venv_path / "bin").mkdir(parents=True)
    python_path = venv_path / "bin" / "python"
    python_path.write_text("#!/bin/sh\nexit 0\n")

    with patch.object(manager, "_python_major_minor", return_value="3.10"):
        with patch("evaluate.venv_manager.shutil.rmtree") as rmtree:
            with patch.object(manager, "_create_venv") as create:
                with patch.object(manager, "_install_packages") as install:
                    returned = manager.ensure_venv_exists(config)

    assert returned == python_path
    rmtree.assert_called_once()
    create.assert_called_once()
    install.assert_called_once()


def test_install_packages_bootstraps_pip_when_missing(tmp_path: Path):
    manager = VenvManager(base_dir=tmp_path)

    python_path = Path("/fake/python")

    calls: list[list[str]] = []

    def fake_run(cmd: list[str], **kwargs):  # type: ignore[no-untyped-def]
        calls.append([str(c) for c in cmd])

        class Result:
            stdout = ""
            stderr = ""

        return Result()

    with patch.object(manager, "_can_import", side_effect=[False]):
        with patch("evaluate.venv_manager.subprocess.run", side_effect=fake_run):
            manager._install_packages(python_path, ["opentrons==8.7.0"])

    assert any(cmd[:3] == [str(python_path), "-m", "ensurepip"] for cmd in calls)
    assert any(cmd[:4] == [str(python_path), "-m", "pip", "install"] for cmd in calls)
