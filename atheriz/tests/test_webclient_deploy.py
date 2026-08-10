import importlib.util
from pathlib import Path


def _load_deploy_module():
    path = Path(__file__).parents[2] / "webclient" / "deploy.py"
    spec = importlib.util.spec_from_file_location("atheriz_webclient_deploy", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_package_cleanup_removes_legacy_webclient_assets(tmp_path: Path):
    deploy = _load_deploy_module()
    legacy = tmp_path / "webclient"
    legacy.mkdir()
    (legacy / "index.html").write_text("old")
    (legacy / "js").mkdir()
    (legacy / "js" / "webclient.js").write_text("old")

    deploy.clean_generated_output(tmp_path, remove_legacy_webclient=True)

    assert not legacy.exists()


def test_game_cleanup_preserves_legacy_webclient_assets(tmp_path: Path):
    deploy = _load_deploy_module()
    legacy = tmp_path / "webclient"
    legacy.mkdir()
    (legacy / "index.html").write_text("old")
    (legacy / "js").mkdir()
    legacy_script = legacy / "js" / "webclient.js"
    legacy_script.write_text("old")

    deploy.clean_generated_output(tmp_path)

    assert not (legacy / "index.html").exists()
    assert legacy_script.read_text() == "old"
