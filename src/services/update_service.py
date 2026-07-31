"""
update_service - 纯 Python 自动更新服务
==========================================

零原生依赖的自动更新实现：拉取 appcast.xml → 对比版本 → 下载 DMG →
外部脚本替换 .app → 重启。

版本: 0.8.0
"""

import logging
import os
import shlex
import subprocess
import sys
import tempfile
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from src.config import (
    SETTING_AUTO_UPDATE,
    SETTING_LAST_UPDATE_CHECK,
    UPDATE_FEED_FALLBACK_URL,
    UPDATE_FEED_URL,
)
from src.data.settings_repo import SettingsRepository
from src.utils.net import encode_url
from src.utils.text import strip_html
from src.utils.version import get_version

logger = logging.getLogger(__name__)


@dataclass
class UpdateInfo:
    """更新信息。"""

    version: str
    short_version: str
    description: str
    dmg_url: str
    length: int


class UpdateService:
    """纯 Python 自动更新服务。

    Args:
        settings_repo: SettingsRepository 实例
    """

    def __init__(self, settings_repo: SettingsRepository):
        self._temp_dir = tempfile.gettempdir()
        self._cancel_event = threading.Event()
        self._settings = settings_repo

    def cancel_download(self) -> None:
        """取消正在进行的下载。"""
        self._cancel_event.set()

    def reset_cancel(self) -> None:
        """重置取消标志。"""
        self._cancel_event.clear()

    # ─── 版本检查 ──────────────────────────────────────────

    def check_for_updates(self) -> UpdateInfo | None:
        """拉取 appcast.xml，解析最新版本，与本地 VERSION 对比。

        Returns:
            UpdateInfo: 有新版本
            None:       已是最新版本

        Raises:
            RuntimeError: 拉取或解析 appcast 失败（网络问题等）
        """
        xml_content = self._fetch_feed()
        if not xml_content:
            raise RuntimeError("无法连接更新服务器，请检查网络")

        info = self._parse_appcast(xml_content)
        if not info:
            raise RuntimeError("解析更新信息失败")

        if self._is_newer(info.short_version):
            return info
        return None

    def _fetch_feed(self) -> str | None:
        """拉取 appcast.xml，主 URL 失败则用 jsDelivr 备用。"""
        import ssl

        ctx = ssl.create_default_context()
        for url in (UPDATE_FEED_URL, UPDATE_FEED_FALLBACK_URL):
            try:
                parsed = urlparse(url)
                if parsed.scheme != "https" or not parsed.netloc:
                    logger.warning("[Update] 忽略不安全更新地址：%s", url)
                    continue
                req = Request(url, headers={"User-Agent": "worktime-tracker"})
                with urlopen(req, timeout=15, context=ctx) as resp:
                    return resp.read().decode("utf-8")
            except Exception as e:
                logger.warning("[Update] 拉取失败 %s：%s", url, e)
                continue
        return None

    def _parse_appcast(self, xml_content: str) -> UpdateInfo | None:
        """解析 appcast.xml，取第一个 item 作为最新版本。"""
        try:
            root = ElementTree.fromstring(xml_content)
            ns = {"sparkle": "http://www.andymatuschak.org/xml-namespaces/sparkle"}
            item = root.find(".//item")
            if item is None:
                return None

            version = item.findtext("sparkle:version", default="", namespaces=ns)
            short = item.findtext("sparkle:shortVersionString", default="", namespaces=ns)
            desc = item.findtext("description", default="")
            desc = strip_html(desc)
            enclosure = item.find("enclosure")
            if enclosure is None:
                return None

            dmg_url = enclosure.get("url", "")
            parsed_url = urlparse(dmg_url)
            if parsed_url.scheme != "https" or not parsed_url.netloc:
                return None
            if not version or not short:
                return None
            length = int(enclosure.get("length", "0"))
            if length < 0:
                return None
            return UpdateInfo(
                version=version,
                short_version=short,
                description=desc,
                dmg_url=dmg_url,
                length=length,
            )
        except Exception as e:
            logger.warning("[Update] 解析 appcast 失败：%s", e)
            return None

    def _is_newer(self, remote_version: str) -> bool:
        """对比版本号，remote > local 返回 True。"""
        try:
            local_version = get_version()
            remote_parts = [int(x) for x in remote_version.split(".")]
            local_parts = [int(x) for x in local_version.split(".")]
            while len(remote_parts) < 3:
                remote_parts.append(0)
            while len(local_parts) < 3:
                local_parts.append(0)
            return remote_parts > local_parts
        except Exception:
            return False

    # ─── 下载 ─────────────────────────────────────────────

    def download_update(
        self,
        dmg_url: str,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> str | None:
        """下载 DMG 到临时目录。"""
        if self._cancel_event.is_set():
            return None
        try:
            import ssl

            ctx = ssl.create_default_context()

            url = encode_url(dmg_url)
            parsed_url = urlparse(url)
            if parsed_url.scheme != "https" or not parsed_url.netloc:
                raise ValueError("更新下载地址必须使用 HTTPS")
            req = Request(url, headers={"User-Agent": "worktime-tracker"})
            with urlopen(req, timeout=10, context=ctx) as resp:
                total = int(resp.headers.get("Content-Length", 0))
                dmg_path = os.path.join(self._temp_dir, "worktime_update.dmg")
                downloaded = 0
                chunk = 512 * 1024
                max_timeout_retries = 5
                timeout_count = 0
                with open(dmg_path, "wb") as f:
                    while True:
                        if self._cancel_event.is_set():
                            f.close()
                            try:
                                os.remove(dmg_path)
                            except OSError:
                                pass
                            return None
                        try:
                            buf = resp.read(chunk)
                        except TimeoutError:
                            if self._cancel_event.is_set():
                                f.close()
                                try:
                                    os.remove(dmg_path)
                                except OSError:
                                    pass
                                return None
                            timeout_count += 1
                            if timeout_count > max_timeout_retries:
                                logger.warning(
                                    "[Update] 下载超时次数过多(%s)，放弃下载", max_timeout_retries
                                )
                                f.close()
                                try:
                                    os.remove(dmg_path)
                                except OSError:
                                    pass
                                return None
                            continue
                        timeout_count = 0
                        if not buf:
                            break
                        f.write(buf)
                        downloaded += len(buf)
                        if progress_callback:
                            progress_callback(downloaded, total)
            return dmg_path
        except Exception as e:
            if self._cancel_event.is_set():
                return None
            logger.warning("[Update] 下载失败：%s", e)
            return None

    def verify_update(self, dmg_path: str, expected_length: int) -> bool:
        """校验下载文件大小。"""
        try:
            actual = os.path.getsize(dmg_path)
            if expected_length > 0 and actual != expected_length:
                logger.warning("[Update] 大小不匹配：期望 %s，实际 %s", expected_length, actual)
                return False
            return actual > 0
        except Exception:
            return False

    # ─── 安装 + 重启 ──────────────────────────────────────

    def install_and_restart(self, dmg_path: str) -> bool:
        """写外部 updater 脚本 → 退出主进程 → 脚本挂载 DMG → 替换 .app → 重启。"""
        app_path = self._get_app_path()
        if not app_path or not os.path.isdir(app_path) or not os.path.isfile(dmg_path):
            logger.warning("[Update] 无法获取 .app 路径，开发环境不自动更新")
            return False

        app_name = os.path.basename(app_path)
        mount_point = tempfile.mkdtemp(prefix="worktime_update_mount_")
        updater_script = os.path.join(self._temp_dir, "worktime_updater.sh")
        q_dmg = shlex.quote(dmg_path)
        q_mount = shlex.quote(mount_point)
        q_app = shlex.quote(app_path)
        q_app_name = shlex.quote(app_name)
        q_script = shlex.quote(updater_script)

        try:
            with open(updater_script, "w", encoding="utf-8") as f:
                f.write(
                    f"""#!/bin/bash
set -euo pipefail
mounted=0
staged_app={q_mount}/staged.app
backup_app={q_app}.backup.$$
cleanup() {{
  if [ "$mounted" -eq 1 ]; then hdiutil detach {q_mount} -force >/dev/null 2>&1 || true; fi
  rm -rf {q_mount} "$staged_app"
  rm -f {q_dmg} {q_script}
}}
trap cleanup EXIT

sleep 2
hdiutil attach {q_dmg} -nobrowse -mountpoint {q_mount}
mounted=1
source_app={q_mount}/{q_app_name}
if [ ! -d "$source_app" ]; then
  echo "更新镜像中未找到应用" >&2
  exit 1
fi
cp -R "$source_app" "$staged_app"
if [ ! -d "$staged_app" ]; then
  echo "应用暂存失败" >&2
  exit 1
fi
mv {q_app} "$backup_app"
if ! mv "$staged_app" {q_app}; then
  mv "$backup_app" {q_app}
  exit 1
fi
rm -rf "$backup_app"
open {q_app}
"""
                )
            os.chmod(updater_script, 0o755)
            subprocess.Popen(
                ["bash", updater_script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            return True
        except OSError as e:
            logger.warning("[Update] 创建更新脚本失败：%s", e)
            try:
                os.remove(updater_script)
            except OSError:
                pass
            return False

    def _get_app_path(self) -> str | None:
        """获取当前 .app 的完整路径。"""
        try:
            if not getattr(sys, "frozen", False):
                return None
            exe = sys.executable
            contents = os.path.dirname(os.path.dirname(exe))
            app_path = os.path.dirname(contents)
            if app_path.endswith(".app"):
                return app_path
            return None
        except Exception:
            return None

    # ─── 设置读写 ─────────────────────────────────────────

    def is_auto_update_enabled(self) -> bool:
        return self._settings.get(SETTING_AUTO_UPDATE, "0") == "1"

    def set_auto_update(self, enabled: bool) -> None:
        self._settings.set(SETTING_AUTO_UPDATE, "1" if enabled else "0")

    def should_check_now(self, interval: int) -> bool:
        """判断是否到检查时间（基于上次检查时间戳）。"""
        last = self._settings.get(SETTING_LAST_UPDATE_CHECK, "")
        if not last:
            return True
        try:
            last_dt = datetime.fromisoformat(last)
            return (datetime.now() - last_dt).total_seconds() >= interval
        except Exception:
            return True

    def mark_checked(self) -> None:
        self._settings.set(SETTING_LAST_UPDATE_CHECK, datetime.now().isoformat())
