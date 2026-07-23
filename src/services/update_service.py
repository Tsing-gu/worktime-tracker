# -*- coding: utf-8 -*-
"""
update_service - 纯 Python 自动更新服务
==========================================

零原生依赖的自动更新实现：拉取 appcast.xml → 对比版本 → 下载 DMG →
外部脚本替换 .app → 重启。

版本: 0.8.0
"""

import os
import sys
import tempfile
import subprocess
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Callable
from urllib.request import urlopen, Request
from xml.etree import ElementTree

from src.config import (
    UPDATE_FEED_URL,
    UPDATE_FEED_FALLBACK_URL,
    SETTING_AUTO_UPDATE,
    SETTING_LAST_UPDATE_CHECK,
)
from src.data.settings_repo import SettingsRepository
from src.utils.version import get_version
from src.utils.text import strip_html
from src.utils.net import encode_url


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
        self._cancelled = False
        self._settings = settings_repo

    def cancel_download(self):
        """取消正在进行的下载。"""
        self._cancelled = True

    def reset_cancel(self):
        """重置取消标志。"""
        self._cancelled = False

    # ─── 版本检查 ──────────────────────────────────────────

    def check_for_updates(self) -> Optional[UpdateInfo]:
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

    def _fetch_feed(self) -> Optional[str]:
        """拉取 appcast.xml，主 URL 失败则用 jsDelivr 备用。"""
        import ssl
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        for url in (UPDATE_FEED_URL, UPDATE_FEED_FALLBACK_URL):
            try:
                req = Request(url, headers={"User-Agent": "worktime-tracker"})
                with urlopen(req, timeout=15, context=ctx) as resp:
                    return resp.read().decode("utf-8")
            except Exception as e:
                print(f"[Update] 拉取失败 {url}：{e}")
                continue
        return None

    def _parse_appcast(self, xml_content: str) -> Optional[UpdateInfo]:
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
            length = int(enclosure.get("length", "0"))
            return UpdateInfo(
                version=version,
                short_version=short,
                description=desc,
                dmg_url=dmg_url,
                length=length,
            )
        except Exception as e:
            print(f"[Update] 解析 appcast 失败：{e}")
            return None

    def _is_newer(self, remote_version: str) -> bool:
        """对比版本号，remote > local 返回 True。"""
        try:
            local = get_version()
            r = [int(x) for x in remote_version.split(".")]
            l = [int(x) for x in local.split(".")]
            while len(r) < 3:
                r.append(0)
            while len(l) < 3:
                l.append(0)
            return r > l
        except Exception:
            return False

    # ─── 下载 ─────────────────────────────────────────────

    def download_update(
        self,
        dmg_url: str,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> Optional[str]:
        """下载 DMG 到临时目录。"""
        try:
            import ssl
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

            url = encode_url(dmg_url)
            req = Request(url, headers={"User-Agent": "worktime-tracker"})
            with urlopen(req, timeout=300, context=ctx) as resp:
                total = int(resp.headers.get("Content-Length", 0))
                dmg_path = os.path.join(self._temp_dir, "worktime_update.dmg")
                downloaded = 0
                chunk = 512 * 1024
                with open(dmg_path, "wb") as f:
                    while True:
                        if self._cancelled:
                            f.close()
                            try:
                                os.remove(dmg_path)
                            except OSError:
                                pass
                            return None
                        buf = resp.read(chunk)
                        if not buf:
                            break
                        f.write(buf)
                        downloaded += len(buf)
                        if progress_callback:
                            progress_callback(downloaded, total)
            return dmg_path
        except Exception as e:
            print(f"[Update] 下载失败：{e}")
            return None

    def verify_update(self, dmg_path: str, expected_length: int) -> bool:
        """校验下载文件大小。"""
        try:
            actual = os.path.getsize(dmg_path)
            if expected_length > 0 and actual != expected_length:
                print(f"[Update] 大小不匹配：期望 {expected_length}，实际 {actual}")
                return False
            return actual > 0
        except Exception:
            return False

    # ─── 安装 + 重启 ──────────────────────────────────────

    def install_and_restart(self, dmg_path: str) -> bool:
        """写外部 updater 脚本 → 退出主进程 → 脚本挂载 DMG → 替换 .app → 重启。"""
        app_path = self._get_app_path()
        if not app_path:
            print("[Update] 无法获取 .app 路径，开发环境不自动更新")
            return False

        app_name = os.path.basename(app_path)
        mount_point = "/tmp/wt_update_mount"
        updater_script = os.path.join(self._temp_dir, "worktime_updater.sh")

        with open(updater_script, "w") as f:
            f.write(f"""#!/bin/bash
# 等待主进程完全退出
sleep 2
# 挂载 DMG
hdiutil attach "{dmg_path}" -nobrowse -mountpoint "{mount_point}"
# 等待挂载完成
sleep 1
# 替换 .app（重试 3 次）
for i in 1 2 3; do
  rm -rf "{app_path}" && break
  sleep 1
done
cp -R "{mount_point}/{app_name}" "{app_path}"
hdiutil detach "{mount_point}" -force
rm -f "{dmg_path}"
open "{app_path}"
rm -f "{updater_script}"
""")
        os.chmod(updater_script, 0o755)

        subprocess.Popen(["bash", updater_script],
                         stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
        return True

    def _get_app_path(self) -> Optional[str]:
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

    def set_auto_update(self, enabled: bool):
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

    def mark_checked(self):
        self._settings.set(SETTING_LAST_UPDATE_CHECK, datetime.now().isoformat())
