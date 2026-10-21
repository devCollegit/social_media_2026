import os

import settings


def test_krx_env_loads_only_allowed_keys_without_interpolation(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "ROOT", tmp_path)
    monkeypatch.delenv("KRX_ID", raising=False)
    monkeypatch.delenv("KRX_PW", raising=False)
    monkeypatch.delenv("UNRELATED_TEST_KEY", raising=False)
    (tmp_path / ".env").write_text(
        "KRX_ID='dummy-user'\nKRX_PW='dummy-${KRX_ID}#value'\n"
        "UNRELATED_TEST_KEY=ignored\n", encoding="utf-8"
    )
    settings.load_krx_env()
    assert os.environ["KRX_ID"] == "dummy-user"
    assert os.environ["KRX_PW"] == "dummy-${KRX_ID}#value"
    assert "UNRELATED_TEST_KEY" not in os.environ


def test_krx_env_preserves_shell_and_handles_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "ROOT", tmp_path)
    monkeypatch.setenv("KRX_ID", "shell-user")
    monkeypatch.delenv("KRX_PW", raising=False)
    settings.load_krx_env()
    assert "KRX_PW" not in os.environ
    (tmp_path / ".env").write_text("KRX_ID=file-user\nKRX_PW=''\n", encoding="utf-8")
    settings.load_krx_env()
    assert os.environ["KRX_ID"] == "shell-user"
    assert "KRX_PW" not in os.environ
