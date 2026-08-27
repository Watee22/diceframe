from __future__ import annotations

import json
import stat
import zipfile
from pathlib import Path

import pytest

from src.docker_launcher import contracts
from src.docker_launcher.launcher import DockerLauncher, _version_key


def _package_tree(root: Path, version: str = "2.4.0", probation: int = 0) -> Path:
    package = root / f"DiceFrame-v{version}-docker-update-linux-amd64"
    (package / "app" / "src").mkdir(parents=True)
    (package / "app" / "static-v2").mkdir(parents=True)
    (package / "runtime" / "site-packages").mkdir(parents=True)
    (package / "app" / "web_server.py").write_text("# server\n", encoding="utf-8")
    (package / "app" / "src" / "version.py").write_text(
        f'__version__ = "{version}"\n', encoding="utf-8",
    )
    (package / "app" / "static-v2" / "index.html").write_text("ok", encoding="utf-8")
    (package / "runtime" / "site-packages" / "runtime.txt").write_text("ok", encoding="utf-8")
    (package / "manifest.json").write_text(json.dumps({
        "schema": 1,
        "version": version,
        "platform": "linux-amd64",
        "python_abi": "cp311",
        "launcher_schema_min": 1,
        "runtime_api": 1,
        "data_rollback_safe": True,
        "entrypoint": "app/web_server.py",
        "site_packages": "runtime/site-packages",
        "health_path": "/api/system/update/health",
        "probation_seconds": probation,
    }), encoding="utf-8")
    return package


def _archive(tmp_path: Path, version: str = "2.4.0") -> Path:
    package = _package_tree(tmp_path / "source", version)
    archive = tmp_path / f"DiceFrame-v{version}-docker-update-linux-amd64.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        for path in package.rglob("*"):
            if path.is_file():
                bundle.write(path, path.relative_to(package.parent).as_posix())
    return archive


def test_contract_rejects_links_and_path_traversal(tmp_path):
    traversal = tmp_path / "traversal.zip"
    with zipfile.ZipFile(traversal, "w") as bundle:
        bundle.writestr("DiceFrame/../../outside", "bad")
    with pytest.raises(ValueError, match="unsafe update path"):
        contracts.safe_extract_package(traversal, tmp_path / "out-traversal")

    linked = tmp_path / "linked.zip"
    info = zipfile.ZipInfo("DiceFrame/link")
    info.create_system = 3
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(linked, "w") as bundle:
        bundle.writestr(info, "target")
    with pytest.raises(ValueError, match="symlink"):
        contracts.safe_extract_package(linked, tmp_path / "out-linked")


def test_manifest_binds_application_version(tmp_path):
    package = _package_tree(tmp_path, "2.4.0")
    contracts.validate_package_tree(package, expected_version="2.4.0")
    (package / "app" / "src" / "version.py").write_text(
        '__version__ = "2.4.1"', encoding="utf-8",
    )
    with pytest.raises(ValueError, match="application version"):
        contracts.validate_package_tree(package, expected_version="2.4.0")


def test_manifest_requires_data_safe_rollback(tmp_path):
    package = _package_tree(tmp_path, "2.4.0")
    manifest_path = package / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["data_rollback_safe"] = False
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="data migrations"):
        contracts.validate_package_tree(package, expected_version="2.4.0")


def test_launcher_installs_verified_seed_and_commits_relative_pointer(tmp_path, monkeypatch):
    archive = _archive(tmp_path, "2.4.0")
    checksum = tmp_path / "update.sha256"
    checksum.write_text(
        f"{contracts.file_sha256(archive)}  {archive.name}\n", encoding="utf-8",
    )
    launcher = DockerLauncher(tmp_path / "runtime", archive, checksum, startup_timeout=0)
    seed_dir, manifest = launcher.ensure_seed()
    assert manifest["version"] == "2.4.0"
    assert seed_dir == launcher.versions_dir / "v2.4.0"
    assert json.loads(launcher.seed_state_file.read_text(encoding="utf-8"))["sha256"] == contracts.file_sha256(archive)

    monkeypatch.setattr(
        "src.docker_launcher.launcher.safe_extract_package",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("seed unpacked twice")),
    )
    cached_dir, cached_manifest = launcher.ensure_seed()
    assert cached_dir == seed_dir
    assert cached_manifest["version"] == "2.4.0"

    launcher._commit(seed_dir, None)
    pointer = json.loads(launcher.current_file.read_text(encoding="utf-8"))
    assert pointer["relative_dir"] == "docker-versions/v2.4.0"
    assert not Path(pointer["relative_dir"]).is_absolute()


def test_launcher_seed_checksum_is_bound_to_container_filename(tmp_path):
    archive = _archive(tmp_path, "2.4.0")
    archive = archive.rename(tmp_path / "update.zip")
    checksum = tmp_path / "update.sha256"
    checksum.write_text(
        f"{contracts.file_sha256(archive)}  update.zip\n", encoding="utf-8",
    )
    launcher = DockerLauncher(tmp_path / "runtime", archive, checksum)

    seed_dir, manifest = launcher.ensure_seed()

    assert manifest["version"] == "2.4.0"
    assert seed_dir.is_dir()


def test_launcher_commits_healthy_candidate_and_rolls_back_failed_one(tmp_path, monkeypatch):
    archive = _archive(tmp_path, "2.4.0")
    checksum = tmp_path / "update.sha256"
    checksum.write_text(
        f"{contracts.file_sha256(archive)}  {archive.name}\n", encoding="utf-8",
    )
    launcher = DockerLauncher(tmp_path / "runtime", archive, checksum)
    previous = _package_tree(launcher.versions_dir, "2.3.2")
    candidate = _package_tree(launcher.versions_dir, "2.4.0")
    spawned: list[Path] = []
    monkeypatch.setattr(launcher, "_stop_child", lambda *args, **kwargs: None)
    monkeypatch.setattr(launcher, "_spawn", lambda path: spawned.append(path))
    monkeypatch.setattr(launcher, "_prune", lambda: None)
    monkeypatch.setattr(launcher, "_wait_healthy", lambda path: path == candidate)

    assert launcher._launch_candidate(candidate, previous) is True
    assert json.loads(launcher.current_file.read_text(encoding="utf-8"))["version"] == "2.4.0"
    assert not launcher.signal_file.exists()

    broken = _package_tree(launcher.versions_dir, "2.5.0")
    monkeypatch.setattr(launcher, "_wait_healthy", lambda path: path == candidate)
    assert launcher._launch_candidate(broken, candidate) is False
    assert spawned[-2:] == [broken, candidate]
    assert json.loads(launcher.state_file.read_text(encoding="utf-8"))["state"] == "rolled-back"


def test_launcher_uses_previous_when_current_is_damaged(tmp_path):
    archive = _archive(tmp_path, "2.4.0")
    checksum = tmp_path / "update.sha256"
    checksum.write_text(
        f"{contracts.file_sha256(archive)}  {archive.name}\n", encoding="utf-8",
    )
    launcher = DockerLauncher(tmp_path / "runtime", archive, checksum)
    seed_source = _package_tree(launcher.versions_dir, "2.4.0")
    seed = seed_source.rename(launcher.versions_dir / "v2.4.0")
    previous_source = _package_tree(launcher.versions_dir, "2.3.2")
    previous = previous_source.rename(launcher.versions_dir / "v2.3.2")
    launcher.current_file.parent.mkdir(parents=True, exist_ok=True)
    launcher.current_file.write_text(json.dumps({
        "relative_dir": "docker-versions/v2.4.1",
        "previous_relative_dir": "docker-versions/v2.3.2",
    }), encoding="utf-8")

    selected, fallback = launcher._choose_startup(
        seed, contracts.validate_package_tree(seed),
    )
    assert selected == previous
    assert fallback is None


def test_version_order_handles_prereleases():
    assert _version_key("2.4.0-beta.1") < _version_key("2.4.0")
    assert _version_key("2.4.0-beta.10") > _version_key("2.4.0-beta.2")
    assert _version_key("2.4.1") > _version_key("2.4.0")
