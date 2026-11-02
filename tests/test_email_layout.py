"""Unit tests ของการแปลง body อีเมลเป็น HTML layout กลาง"""

from email import message_from_string

from kampan.utils import email_layout, email_utils


def test_link_line_becomes_button():
    html = email_layout.body_to_html("ระบบขอซื้อพัสดุ\nLink: https://example.test/approve?id=1&x=2")

    assert "เปิดในระบบ" in html
    assert 'href="https://example.test/approve?id=1&amp;x=2"' in html


def test_body_text_is_escaped():
    html = email_layout.body_to_html("เหตุผล: <script>alert(1)</script>")

    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_label_is_bold_and_blank_lines_collapse():
    html = email_layout.body_to_html("\n\n    ใบขอซื้อเลขที่: PR-001\n\n\n\nเวลา 10:30")

    assert "<strong" in html and "ใบขอซื้อเลขที่:</strong> PR-001" in html
    assert html.count('<div style="margin:0 0 16px;">') == 2
    assert "เวลา 10:30" in html


def test_render_email_html_wraps_subject_in_layout():
    html = email_layout.render_email_html("[แจ้งเตือน] ทดสอบ", "เรียน ผู้บริหาร")

    assert "<!DOCTYPE html>" in html
    assert "[แจ้งเตือน] ทดสอบ" in html
    assert "เรียน ผู้บริหาร" in html


def send_and_capture(monkeypatch, **kwargs):
    sent = {}

    class FakeSMTP:
        def __init__(self, host, port):
            pass

        def sendmail(self, sender, receivers, raw):
            sent["raw"] = raw

    monkeypatch.setattr(email_utils.smtplib, "SMTP", FakeSMTP)
    smtp = email_utils.PSUSMTP({"KAMPAN_EMAIL_USER": "bot@example.test"})

    assert smtp.send_email(
        "a@example.test", "หัวข้อ", "เนื้อหา\nLink: https://example.test", **kwargs
    )
    return message_from_string(sent["raw"]).get_payload()


def test_send_email_with_html_attaches_plain_and_html(monkeypatch):
    parts = send_and_capture(monkeypatch, html=True)

    assert [p.get_content_type() for p in parts] == ["text/plain", "text/html"]
    assert "เปิดในระบบ" in parts[1].get_payload(decode=True).decode("utf-8")


def test_send_email_defaults_to_plain_text_only(monkeypatch):
    parts = send_and_capture(monkeypatch)

    assert [p.get_content_type() for p in parts] == ["text/plain"]


def test_list_items_separated_by_blank_lines_stay_in_one_paragraph():
    html = email_layout.body_to_html("รายการขอซื้อ:\n\n  - ปากกา\n\n\n  - ดินสอ\n\nเหตุผล: ใช้งาน")

    assert html.count('<div style="margin:0 0 16px;">') == 3
    assert "•&nbsp;ปากกา" in html and "•&nbsp;ดินสอ" in html


def test_host_url_follows_environment_config():
    assert email_utils.get_host_url({"KAMPAN_HOST_URL": "https://staging.example.test/"}) == (
        "https://staging.example.test"
    )


def test_host_url_falls_back_to_default_settings():
    from kampan import default_settings

    assert email_utils.get_host_url({}) == default_settings.KAMPAN_HOST_URL
    assert email_utils.get_host_url(None) == default_settings.KAMPAN_HOST_URL


def test_steps_render_above_content_only_when_given():
    steps = [
        {"label": "ยื่นคำขอ", "state": "done"},
        {"label": "พัสดุ", "state": "denied"},
        {"label": "อนุมัติ", "state": "upcoming"},
    ]
    with_steps = email_layout.render_email_html("s", "เนื้อหา", steps)
    without = email_layout.render_email_html("s", "เนื้อหา")

    assert "✓" in with_steps and "✕" in with_steps and ">3</td>" in with_steps
    assert with_steps.index("พัสดุ") < with_steps.index('<div style="margin:0 0 16px;">เนื้อหา')
    assert "✓" not in without


def test_steps_avoid_div_boxes_that_outlook_ignores():
    html = email_layout.render_steps(
        [{"label": "ยื่นคำขอ", "state": "done"}, {"label": "อนุมัติ", "state": "upcoming"}]
    )

    assert "<div" not in html
    assert "transparent" not in html
    assert 'bgcolor="#003c71"' in html
