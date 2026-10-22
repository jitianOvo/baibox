# -*- coding: utf-8 -*-
import html as _html
import re


def _escape(text):
    return _html.escape(text, quote=False)


def _inline(text):
    """行内格式：代码、粗体、斜体、链接"""
    # 先保护行内代码
    code_spans = []
    def _code_repl(m):
        code_spans.append(_escape(m.group(1)))
        return "\x00CODE%d\x00" % (len(code_spans) - 1)
    text = re.sub(r"`([^`]+)`", _code_repl, text)

    # 链接 [text](url)
    text = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)",
                  r'<a href="\2" style="color:#2563eb;">\1</a>', text)

    # 粗体 bold
    text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)
    # 斜体（单个 *，避免误伤已生成的 <b>）
    text = re.sub(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])", r"<i>\1</i>", text)

    # 还原行内代码
    for i, code in enumerate(code_spans):
        text = text.replace("\x00CODE%d\x00" % i,
                            '<span style="background:#eef2f7;border-radius:4px;'
                            'padding:1px 5px;font-family:Consolas,monospace;'
                            'color:#b91c1c;">' + code + "</span>")
    return text


def render_md(text):
    """轻量 Markdown → HTML（标题/列表/代码块/粗斜体/链接）"""
    parts = []
    # 拆分代码块
    segments = re.split(r"```", text)
    for idx, seg in enumerate(segments):
        if idx % 2 == 1:
            # 代码块
            lang_line = seg.split("\n", 1)
            body = lang_line[1] if len(lang_line) > 1 else lang_line[0]
            parts.append(
                '<pre style="background:#0f172a;color:#e2e8f0;border-radius:8px;'
                'padding:10px;font-family:Consolas,monospace;font-size:12px;">'
                + _escape(body) + "</pre>")
            continue
        # 普通文本段：按行渲染
        lines = seg.split("\n")
        in_list = False
        for line in lines:
            line = line.rstrip()
            if not line.strip():
                if in_list:
                    parts.append("</ul>")
                    in_list = False
                continue
            m = re.match(r"^(#{1,4})\s+(.*)$", line)
            if m:
                if in_list:
                    parts.append("</ul>")
                    in_list = False
                lvl = len(m.group(1))
                size = {1: 20, 2: 17, 3: 15, 4: 13}.get(lvl, 13)
                parts.append(
                    f'<p style="font-size:{size}px;font-weight:700;margin:6px 0 2px;">'
                    + _inline(m.group(2)) + "</p>")
                continue
            m = re.match(r"^\s*[-*+]\s+(.*)$", line)
            if m:
                if not in_list:
                    parts.append("<ul>")
                    in_list = True
                parts.append("<li>" + _inline(m.group(1)) + "</li>")
                continue
            m = re.match(r"^\s*\d+[.)]\s+(.*)$", line)
            if m:
                if not in_list:
                    parts.append("<ol>")
                    in_list = True
                parts.append("<li>" + _inline(m.group(1)) + "</li>")
                continue
            if in_list:
                parts.append("</ul>")
                in_list = False
            parts.append("<p>" + _inline(line) + "</p>")
        if in_list:
            parts.append("</ul>")
    return "".join(parts)
