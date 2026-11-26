"""E2E plugin validation, PluginManager discovery, FastAPI routes, CLI, and A->B->A profile isolation tests."""
from __future__ import annotations

import base64
import importlib.util
import shutil
import sys
import uuid
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_SRC = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _install_into_home(home: Path) -> Path:
    target = home / "plugins" / "forx-latex"
    shutil.copytree(PLUGIN_SRC, target, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", "node_modules"))
    (home / "config.yaml").write_text("plugins:\n  enabled: [forx-latex]\n", encoding="utf-8")
    return target


def _load_api_app(plugin_root: Path):
    name = "forx_latex_api_test_" + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(name, plugin_root / "dashboard" / "plugin_api.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    app = FastAPI()
    app.include_router(mod.router, prefix="/api/plugins/forx-latex")
    return app


def test_hermes_validate_and_plugin_manager_discovery(tmp_path, monkeypatch):
    from hermes_cli.plugin_validate import validate_plugin_dir
    from hermes_cli.plugins import PluginManager

    report = validate_plugin_dir(PLUGIN_SRC)
    assert report.ok, f"Validation failed: {report.checks}"

    home = tmp_path / "hermes_home"
    _install_into_home(home)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setenv("FORX_HOME", str(home))

    manager = PluginManager(scope_key=str(home))
    manager.discover_and_load()
    loaded = next(p for p in manager.list_plugins() if p["name"] == "forx-latex")
    assert loaded["enabled"] and not loaded["error"], loaded
    assert "latex" in manager._cli_commands
    assert loaded["tools"] == 8
    assert any(entry["plugin_key"] == "forx-latex" for entry in manager._plugin_skills.values())


def test_fastapi_e2e_and_profile_isolation_aba(tmp_path, monkeypatch):
    home_a = tmp_path / "home_a"
    home_b = tmp_path / "home_b"
    root_a = _install_into_home(home_a)
    _install_into_home(home_b)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    # Profile A
    monkeypatch.setenv("HERMES_HOME", str(home_a))
    monkeypatch.setenv("FORX_HOME", str(home_a))
    app = _load_api_app(root_a)

    with TestClient(app) as client:
        st = client.get("/api/plugins/forx-latex/status")
        assert st.status_code == 200 and st.json()["template_count"] == 12

        created = client.post(
            "/api/plugins/forx-latex/projects",
            json={"name": "Blockchain Consensus", "template_id": "elsevier-bcra", "request_id": "req-1"},
        )
        assert created.status_code == 200
        pid = created.json()["project"]["id"]

        # Idempotent replay
        replay = client.post(
            "/api/plugins/forx-latex/projects",
            json={"name": "Blockchain Consensus", "template_id": "elsevier-bcra", "request_id": "req-1"},
        )
        assert replay.status_code == 200 and replay.json()["project"]["id"] == pid

        # Edit + snapshot + diff + restore
        orig_intro = client.get(f"/api/plugins/forx-latex/projects/{pid}/file", params={"path": "sections/01_intro.tex"}).json()["content"]
        snaps_before = client.get(f"/api/plugins/forx-latex/projects/{pid}/snapshots").json()["snapshots"]
        init_snap_id = snaps_before[-1]["id"]

        put_res = client.put(
            f"/api/plugins/forx-latex/projects/{pid}/file",
            json={"path": "sections/01_intro.tex", "content": orig_intro + "\n% Modified line\n"},
        )
        assert put_res.status_code == 200 and put_res.json()["project"]["revision"] == 2

        diff_res = client.get(f"/api/plugins/forx-latex/projects/{pid}/snapshots/diff", params={"from_id": init_snap_id}).json()
        assert any(c["path"] == "sections/01_intro.tex" and "+% Modified line" in c["diff"] for c in diff_res["changes"])

        restored = client.post(f"/api/plugins/forx-latex/projects/{pid}/snapshots/{init_snap_id}/restore")
        assert restored.status_code == 200
        restored_intro = client.get(f"/api/plugins/forx-latex/projects/{pid}/file", params={"path": "sections/01_intro.tex"}).json()["content"]
        assert "% Modified line" not in restored_intro

        # Path traversal blocked
        bad_read = client.get(f"/api/plugins/forx-latex/projects/{pid}/file", params={"path": "../../config.yaml"})
        assert bad_read.status_code == 422

        # Materials upload & list
        mat_post = client.post(
            f"/api/plugins/forx-latex/projects/{pid}/materials",
            json={"rel_path": "experiments/eval.csv", "content": "Metric,Score\nTPS,2500\nLatency,12ms"}
        )
        assert mat_post.status_code == 200 and mat_post.json()["ok"] is True
        mat_list = client.get(f"/api/plugins/forx-latex/projects/{pid}/materials")
        assert mat_list.status_code == 200 and any("eval.csv" in m["path"] for m in mat_list.json()["materials"])

        # Chat history initial empty & project chat
        chat_hist = client.get(f"/api/plugins/forx-latex/projects/{pid}/chat/history")
        assert chat_hist.status_code == 200 and chat_hist.json()["messages"] == []

        # Offline CSV -> booktabs generation & preflight check & ZIP export
        gen = client.post(
            f"/api/plugins/forx-latex/projects/{pid}/ai/generate",
            json={"kind": "table", "input": "Algo,TPS\nPBFT,100\nOurs,500"},
        )
        assert gen.status_code == 200 and "\\toprule" in gen.json()["code"]

        chk = client.post(f"/api/plugins/forx-latex/projects/{pid}/check", json={})
        assert chk.status_code == 200 and chk.json()["word_count"]["en_words"] > 10

        z = client.post(f"/api/plugins/forx-latex/projects/{pid}/export-zip")
        assert z.status_code == 200 and len(base64.b64decode(z.json()["data"])) > 100

        # Switch to Profile B -> must NOT see Profile A's project
        monkeypatch.setenv("HERMES_HOME", str(home_b))
        monkeypatch.setenv("FORX_HOME", str(home_b))
        projs_b = client.get("/api/plugins/forx-latex/projects").json()["projects"]
        assert projs_b == []

        # Switch back to Profile A -> Profile A's project still intact
        monkeypatch.setenv("HERMES_HOME", str(home_a))
        monkeypatch.setenv("FORX_HOME", str(home_a))
        projs_a = client.get("/api/plugins/forx-latex/projects").json()["projects"]
        assert len(projs_a) == 1 and projs_a[0]["id"] == pid

        # Disabled plugin gate
        (home_a / "config.yaml").write_text("plugins:\n  enabled: []\n  disabled: [forx-latex]\n", encoding="utf-8")
        forbidden = client.get("/api/plugins/forx-latex/projects")
        assert forbidden.status_code == 403


def test_cli_workflow(tmp_path, monkeypatch, capsys):
    home = tmp_path / "cli_home"
    _install_into_home(home)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setenv("FORX_HOME", str(home))

    import argparse
    spec = importlib.util.spec_from_file_location("forx_latex_cli_pkg", PLUGIN_SRC / "__init__.py", submodule_search_locations=[str(PLUGIN_SRC)])
    pkg = importlib.util.module_from_spec(spec)
    sys.modules["forx_latex_cli_pkg"] = pkg
    spec.loader.exec_module(pkg)
    cli_mod = __import__("forx_latex_cli_pkg.cli", fromlist=["setup", "run"])

    def invoke(argv):
        parser = argparse.ArgumentParser()
        cli_mod.setup(parser)
        args = parser.parse_args(argv)
        rc = cli_mod.run(args)
        out = capsys.readouterr().out
        return rc, out

    rc, out = invoke(["init", "--template", "cn-blockchain-journal", "--name", "区块链共识研究"])
    assert rc == 0 and "sections/01_intro.tex" in out

    import json
    pid = json.loads(out)["project"]["id"]
    rc_chk, out_chk = invoke(["check", "--project", pid])
    assert rc_chk == 0 and json.loads(out_chk)["word_count"]["cjk_chars"] > 20
