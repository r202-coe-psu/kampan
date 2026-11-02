"""แปลง body อีเมลแบบข้อความธรรมดาให้เป็น HTML ที่ห่อด้วย layout กลางของระบบ"""

import pathlib
import re

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup, escape

from kampan import default_settings

_TEMPLATE_DIR = pathlib.Path(__file__).resolve().parent.parent / "web" / "templates" / "email"
_env = Environment(
    loader=FileSystemLoader(_TEMPLATE_DIR),
    autoescape=select_autoescape(["html"]),
)

_URL = re.compile(r"https?://[^\s<>\"]+")
_LINK_LINE = re.compile(r"^(?:link|ลิงก์|ลิงค์)?\s*:?\s*(https?://\S+)$", re.IGNORECASE)
_LABEL_LINE = re.compile(r"^([^:]{1,40}):\s+(.+)$")
_LIST_ITEM = re.compile(r"^(?:[-*•]|\d+\.)\s+")

PRIMARY_COLOR = "#003c71"  # navy blue ม.อ.

_LINK_STYLE = f"color:{PRIMARY_COLOR}; text-decoration:underline; word-break:break-all;"


def _linkify(text):
    parts = []
    last = 0
    for match in _URL.finditer(text):
        parts.append(escape(text[last : match.start()]))
        url = match.group(0)
        parts.append(Markup('<a href="{0}" style="{1}">{0}</a>').format(url, _LINK_STYLE))
        last = match.end()
    parts.append(escape(text[last:]))
    return Markup("").join(parts)


def _button(url):
    return Markup(
        '<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:8px 0 4px;">'
        '<tr><td style="border-radius:8px; background-color:{2};">'
        '<a href="{0}" style="display:inline-block; padding:12px 24px; font-weight:bold; '
        'color:#ffffff; text-decoration:none; border-radius:8px;">เปิดในระบบ</a>'
        "</td></tr></table>"
        '<div style="font-size:12px; color:#64748b; margin-bottom:8px;">'
        'หรือเปิดลิงก์: <a href="{0}" style="{1}">{0}</a></div>'
    ).format(url, _LINK_STYLE, PRIMARY_COLOR)


def _render_line(line):
    if _LIST_ITEM.match(line):
        item = _LIST_ITEM.sub("", line)
        marker = "•" if line[0] in "-*•" else line.split(None, 1)[0]
        return (
            Markup('<span style="padding-left:12px;">{}&nbsp;{}</span>').format(
                marker, _linkify(item)
            ),
            False,
        )

    link = _LINK_LINE.match(line)
    if link:
        return _button(link.group(1)), True

    label = _LABEL_LINE.match(line)
    if label:
        return (
            Markup('<strong style="color:#0f172a;">{}:</strong> {}').format(
                label.group(1), _linkify(label.group(2))
            ),
            False,
        )
    return _linkify(line), False


def _neighbour_is_list_item(neighbours):
    for line in neighbours:
        if line:
            return bool(_LIST_ITEM.match(line))
    return False


def body_to_html(body):
    """ตัดช่องว่างหัวบรรทัด รวมบรรทัดว่างที่ติดกันเป็นย่อหน้า และแปลงบรรทัดลิงก์เป็นปุ่ม"""
    lines = [raw.strip() for raw in (body or "").splitlines()]
    # loop ใน template ทิ้งบรรทัดว่างคั่นรายการไว้ ไม่ให้แตกเป็นคนละย่อหน้า
    lines = [
        line
        for i, line in enumerate(lines)
        if line
        or not (
            _neighbour_is_list_item(reversed(lines[:i]))
            and _neighbour_is_list_item(lines[i + 1 :])
        )
    ]

    paragraphs = []
    current = []
    for line in lines:
        if not line:
            if current:
                paragraphs.append(current)
                current = []
            continue
        current.append(_render_line(line))
    if current:
        paragraphs.append(current)

    blocks = []
    for lines in paragraphs:
        html = Markup("")
        for index, (content, is_block) in enumerate(lines):
            if index and not is_block and not lines[index - 1][1]:
                html += Markup("<br>")
            html += content
        blocks.append(Markup('<div style="margin:0 0 16px;">{}</div>').format(html))
    return Markup("").join(blocks)


_STEP_STYLES = {
    # state: (พื้นวงกลม, ขอบ, สีสัญลักษณ์, สัญลักษณ์แทนเลขขั้น หรือ None, สีป้าย)
    "done": (PRIMARY_COLOR, PRIMARY_COLOR, "#ffffff", "✓", "#0f172a"),
    "current": ("#ffffff", PRIMARY_COLOR, PRIMARY_COLOR, None, PRIMARY_COLOR),
    "denied": ("#dc2626", "#dc2626", "#ffffff", "✕", "#dc2626"),
    "upcoming": ("#ffffff", "#cbd5e1", "#94a3b8", None, "#94a3b8"),
}


def _step_line(color):
    return Markup(
        '<td width="50%" style="padding:0;"><div style="height:2px; line-height:2px; '
        'font-size:0; background-color:{};">&nbsp;</div></td>'
    ).format(color)


def render_steps(steps):
    """steps: list ของ dict {"label", "state"} โดย state เป็น done/current/denied/upcoming"""
    if not steps:
        return Markup("")

    cells = []
    for index, step in enumerate(steps):
        fill, border, fg, symbol, label_color = _STEP_STYLES[step["state"]]
        reached = step["state"] in ("done", "current", "denied")
        left = "transparent" if index == 0 else (PRIMARY_COLOR if reached else "#e2e8f0")
        right_done = step["state"] == "done" and index + 1 < len(steps)
        right = "transparent" if index == len(steps) - 1 else (PRIMARY_COLOR if right_done else "#e2e8f0")
        weight = "bold" if step["state"] in ("current", "denied") else "normal"

        cells.append(
            Markup(
                '<td align="center" valign="top" width="{width}%" style="padding:0;">'
                '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>'
                "{left}"
                '<td style="padding:0;"><div style="width:28px; height:28px; line-height:26px; '
                "border-radius:50%; border:2px solid {border}; background-color:{fill}; color:{fg}; "
                'font-size:14px; font-weight:bold; text-align:center; box-sizing:border-box;">{symbol}</div></td>'
                "{right}"
                "</tr></table>"
                '<div style="margin-top:6px; padding:0 2px; font-size:12px; line-height:1.4; '
                'color:{label_color}; font-weight:{weight};">{label}</div>'
                "</td>"
            ).format(
                width=100 // len(steps),
                left=_step_line(left),
                right=_step_line(right),
                border=border,
                fill=fill,
                fg=fg,
                symbol=symbol or str(index + 1),
                label_color=label_color,
                weight=weight,
                label=step["label"],
            )
        )

    return Markup(
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">'
        "<tr>{}</tr></table>"
    ).format(Markup("").join(cells))


def render_email_html(subject, body, steps=None):
    preheader = next((line.strip() for line in (body or "").splitlines() if line.strip()), "")
    return _env.get_template("layout.html").render(
        subject=subject,
        preheader=preheader,
        content=body_to_html(body),
        steps=render_steps(steps),
        primary_color=PRIMARY_COLOR,
        app_name=default_settings.KAMPAN_EMAIL_SENDER_NAME or default_settings.APP_TITLE,
    )
