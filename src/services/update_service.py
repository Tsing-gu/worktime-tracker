# -*- coding: utf-8 -*-
"""
update_service - 纯 Python 自动更新服务
==========================================

零原生依赖的自动更新实现：拉取 appcast.xml → 对比版本 → 下载 DMG →
外部脚本替换 .app → 重启。

设计原则:
    - 不依赖 Sparkle/objc 等原生框架，规避 PyInstaller 兼容问题
    - 校验用文件大小 length（HTTPS 已防中间人，未签名场景下 EdDSA 增益有限）
    - 安装由外部 bash 脚本完成，主进程先退出再替换，避免运行中 .app 被覆盖

版本: 0.5.3
"""

import os
import sys
import tempfile
import subprocess
import shutil
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Callable
from urllib.request import urlopen, Request
from urllib.parse import quote, urlsplit, urlunsplit
from xml.etree import ElementTree

from src.config import (
    UPDATE_FEED_URL,
    UPDATE_FEED_FALLBACK_URL,
    SETTING_AUTO_UPDATE,
    SETTING_LAST_UPDATE_CHECK,
)
from src.data import database
from src.utils.version import get_version


@dataclass
class UpdateInfo:
    """更新信息。"""
    version: str
    short_version: str
    description: str
    dmg_url: str
    length: int


class UpdateService:
    """
    纯 Python 自动更新服务。

    使用方式:
        svc = UpdateService()
        info = svc.check_for_updates()
        if info:
            svc.download_and_install(info, progress_callback)
    """

    def __init__(self):
        self._temp_dir = tempfile.gettempdir()

    # ─── 版本检查 ──────────────────────────────────────────

    def check_for_updates(self) -> Optional[UpdateInfo]:
        """
        拉取 appcast.xml，解析最新版本，与本地 VERSION 对比。

        Returns:
            UpdateInfo（有新版时），或 None（无新版/网络错误）
        """
        try:
            xml_content = self._fetch_feed()
            if not xml_content:
                return None

            info = self._parse_appcast(xml_content)
            if not info:
                return None

            if self._is_newer(info.short_version):
                return info
            return None
        except Exception as e:
            print(f"[Update] 检查更新失败：{e}")
            return None

    def _fetch_feed(self) -> Optional[str]:
        """拉取 appcast.xml，主 URL 失败则用 jsDelivr 备用。"""
        for url in (UPDATE_FEED_URL, UPDATE_FEED_FALLBACK_URL):
            try:
                req = Request(url, headers={"User-Agent": "worktime-tracker"})
                with urlopen(req, timeout=15) as resp:
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
            desc = self._strip_html(desc)
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

    @staticmethod
    def _strip_html(text: str) -> str:
        """去除 HTML 标签，保留纯文本（换行符替代 <li>/<br>）。"""
        import re
        text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
        text = re.sub(r"</li>", "\n", text, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", "", text)
        lines = [ln.strip() for ln in text.splitlines()]
        lines = [ln for ln in lines if ln]
        return "\n".join(lines)

    @staticmethod
    def _encode_url(url: str) -> str:
        """对 URL 中的非 ASCII 字符（如中文文件名）进行百分号编码。"""
        parts = urlsplit(url)
        path = quote(parts.path, safe="/")
        return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))

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
        """
        下载 DMG 到临时目录。

        Args:
            dmg_url:           DMG 下载 URL
            progress_callback: 回调(downloaded_bytes, total_bytes)，None 表示不回调

        Returns:
            下载后的 DMG 本地路径，或 None（失败）
        """
        try:
            url = self._encode_url(dmg_url)
            req = Request(url, headers={"User-Agent": "worktime-tracker"})
            with urlopen(req, timeout=60) as resp:
                total = int(resp.headers.get("Content-Length", 0))
                dmg_path = os.path.join(self._temp_dir, "worktime_update.dmg")
                downloaded = 0
                chunk = 64 * 1024
                with open(dmg_path, "wb") as f:
                    while True:
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
        """
        写外部 updater 脚本 → 退出主进程 → 脚本挂载 DMG → 替换 .app → 重启。

        Returns:
            True（脚本已启动），False（无法获取 app 路径）
        """
        app_path = self._get_app_path()
        if not app_path:
            print("[Update] 无法获取 .app 路径，开发环境不自动更新")
            return False

        app_name = os.path.basename(app_path)
        mount_point = "/tmp/wt_update_mount"
        updater_script = os.path.join(self._temp_dir, "worktime_updater.sh")

        with open(updater_script, "w") as f:
            f.write(f"""#!/bin/bash
sleep 1
hdiutil attach "{dmg_path}" -nobrowse -mountpoint "{mount_point}"
rm -rf "{app_path}"
cp -R "{mount_point}/{app_name}" "{app_path}"
hdiutil detach "{mount_point}" -force
rm -f "{dmg_path}"
open "{app_path}"
rm -f "{updater_script}"
""")
        os.chmod(updater_script, 0o755)

        subprocess.Popen(["bash", updater_script])
        return True

    def _get_app_path(self) -> Optional[str]:
        """
        获取当前 .app 的完整路径。

        打包后通过 sys.executable 回溯 .app；
        开发环境返回 None。
        """
        try:
            if not getattr(sys, "frozen", False):
                return None
            exe = sys.executable
            # exe = xxx.app/Contents/MacOS/可执行名
            # 回溯到 xxx.app
            contents = os.path.dirname(os.path.dirname(exe))
            app_path = os.path.dirname(contents)
            if app_path.endswith(".app"):
                return app_path
            return None
        except Exception:
            return None

    # ─── 设置读写 ─────────────────────────────────────────

    def is_auto_update_enabled(self) -> bool:
        return database.get_setting(SETTING_AUTO_UPDATE, "0") == "1"

    def set_auto_update(self, enabled: bool):
        database.set_setting(SETTING_AUTO_UPDATE, "1" if enabled else "0")

    def should_check_now(self, interval: int) -> bool:
        """判断是否到检查时间（基于上次检查时间戳）。"""
        last = database.get_setting(SETTING_LAST_UPDATE_CHECK, "")
        if not last:
            return True
        try:
            last_dt = datetime.fromisoformat(last)
            return (datetime.now() - last_dt).total_seconds() >= interval
        except Exception:
            return True

    def mark_checked(self):
        database.set_setting(SETTING_LAST_UPDATE_CHECK, datetime.now().isoformat())
