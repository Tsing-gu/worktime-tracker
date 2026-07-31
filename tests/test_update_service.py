"""自动更新服务的安全边界测试。"""

from __future__ import annotations

import ssl
from pathlib import Path
from unittest.mock import MagicMock

from src.services.update_service import UpdateService


def _service() -> UpdateService:
    return UpdateService(MagicMock())


def test_parse_appcast_rejects_non_https_download() -> None:
    service = _service()
    xml = """<?xml version="1.0"?>
    <rss xmlns:sparkle="http://www.andymatuschak.org/xml-namespaces/sparkle">
      <channel><item>
        <sparkle:version>42</sparkle:version>
        <sparkle:shortVersionString>0.18.0</sparkle:shortVersionString>
        <description><![CDATA[<p>更新</p>]]></description>
        <enclosure url="http://example.com/app.dmg" length="10" />
      </item></channel>
    </rss>"""

    assert service._parse_appcast(xml) is None


def test_parse_appcast_rejects_missing_required_fields() -> None:
    service = _service()
    xml = """<rss xmlns:sparkle="http://www.andymatuschak.org/xml-namespaces/sparkle">
      <channel><item>
        <sparkle:version>42</sparkle:version>
        <enclosure url="https://example.com/app.dmg" length="10" />
      </item></channel>
    </rss>"""

    assert service._parse_appcast(xml) is None


def test_download_cancelled_before_start_does_not_open_url(monkeypatch) -> None:
    service = _service()
    service.cancel_download()
    opened = False

    def fail_open(*args, **kwargs):
        nonlocal opened
        opened = True
        raise AssertionError("cancelled download should not open a connection")

    monkeypatch.setattr("src.services.update_service.urlopen", fail_open)

    assert service.download_update("https://example.com/app.dmg") is None
    assert opened is False


def test_download_uses_verified_ssl_context(monkeypatch, tmp_path: Path) -> None:
    service = _service()
    downloaded = tmp_path / "worktime_update.dmg"
    service._temp_dir = str(tmp_path)

    class Response:
        headers = {"Content-Length": "3"}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, size):
            return b"abc" if not downloaded.exists() else b""

    contexts = []
    monkeypatch.setattr(
        "src.services.update_service.urlopen",
        lambda request, timeout, context: contexts.append(context) or Response(),
    )

    result = service.download_update("https://example.com/app.dmg")

    assert result == str(downloaded)
    assert contexts
    assert contexts[0].verify_mode == ssl.CERT_REQUIRED


def test_install_script_stages_before_replacing_app(monkeypatch, tmp_path: Path) -> None:
    service = _service()
    app_path = tmp_path / "WorkTimeTracker.app"
    app_path.mkdir()
    dmg_path = tmp_path / "update.dmg"
    dmg_path.write_bytes(b"dmg")
    service._temp_dir = str(tmp_path)
    monkeypatch.setattr(service, "_get_app_path", lambda: str(app_path))
    popen = MagicMock()
    monkeypatch.setattr("src.services.update_service.subprocess.Popen", popen)

    assert service.install_and_restart(str(dmg_path)) is True

    script = (tmp_path / "worktime_updater.sh").read_text(encoding="utf-8")
    assert "set -euo pipefail" in script
    assert "staged.app" in script
    assert "backup_app" in script
    assert "trap cleanup EXIT" in script
    assert f"rm -rf {app_path}" not in script
