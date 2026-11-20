from datetime import datetime, timezone

from dronemap.scraper import parse_channel_html
from dronemap.store import RawMessage, Store

PAGE = """
<html><body><section class="tgme_channel_history js-message_history">
 <div class="tgme_widget_message_wrap"><div class="tgme_widget_message text_not_supported_wrap js-widget_message" data-post="PoltavaRadar/1201">
  <div class="tgme_widget_message_text js-message_text" dir="auto"><i class="emoji"><b>🛵</b></i> Шахед в районі Карлівки,<br/>курсом на Полтаву</div>
  <div class="tgme_widget_message_footer"><a class="tgme_widget_message_date" href="https://t.me/PoltavaRadar/1201">
   <time datetime="2026-11-20T03:12:44+00:00" class="time">05:12</time></a></div></div></div>
 <div class="tgme_widget_message_wrap"><div class="tgme_widget_message js-widget_message" data-post="PoltavaRadar/1202">
  <div class="tgme_widget_message_photo_wrap"></div>
  <div class="tgme_widget_message_footer"><a class="tgme_widget_message_date"><time datetime="2026-11-20T03:13:00+00:00">05:13</time></a></div></div></div>
 <div class="tgme_widget_message_wrap"><div class="tgme_widget_message service_message js-widget_message" data-post="PoltavaRadar/1203">
  <div class="tgme_widget_message_text">Channel photo updated</div>
  <div class="tgme_widget_message_footer"><a class="tgme_widget_message_date"><time datetime="2026-11-20T03:14:00+00:00">05:14</time></a></div></div></div>
</section></body></html>
"""


def test_parse_channel_page():
    msgs, ok = parse_channel_html(PAGE, "PoltavaRadar")
    assert ok
    assert len(msgs) == 1                                   # photo-only and service posts are skipped
    m = msgs[0]
    assert m.msg_id == 1201 and m.channel == "PoltavaRadar"
    assert m.text == "🛵 Шахед в районі Карлівки,\nкурсом на Полтаву"
    assert m.ts == datetime(2026, 11, 20, 3, 12, 44, tzinfo=timezone.utc).timestamp()


def test_detects_disabled_preview():
    msgs, ok = parse_channel_html("<html><div class='tgme_page'>Join channel</div></html>", "x")
    assert not ok and msgs == []


def test_store_upsert_and_edits():
    s = Store()
    assert s.upsert([RawMessage("a", 1, 10.0, "hi")]) == 1
    assert s.upsert([RawMessage("a", 1, 10.0, "hi")]) == 0
    assert s.upsert([RawMessage("a", 1, 10.0, "edited")]) == 1
    assert [m.text for m in s.since(0)] == ["edited"]
    assert s.last_id("a") == 1
