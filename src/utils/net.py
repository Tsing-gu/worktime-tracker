# -*- coding: utf-8 -*-
"""
net - 网络工具
================

URL 编码等网络相关工具函数。

版本: 0.8.0
"""

from urllib.parse import quote, urlsplit, urlunsplit


def encode_url(url: str) -> str:
    """对 URL 中的非 ASCII 字符（如中文文件名）进行百分号编码。"""
    parts = urlsplit(url)
    path = quote(parts.path, safe="/")
    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))
