# -*- coding: utf-8 -*-
"""
text - 文本处理工具
====================

纯文本工具函数，无状态无依赖。

版本: 0.8.0
"""

import re


def strip_html(text: str) -> str:
    """去除 HTML 标签，保留纯文本（换行符替代 <li>/<br>）。"""
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</li>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    lines = [ln.strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]
    return "\n".join(lines)
