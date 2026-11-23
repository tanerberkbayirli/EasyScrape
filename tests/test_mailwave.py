from __future__ import annotations

import httpx
import pytest

from easyscrape import mailwave
from easyscrape.mailwave import Mailwave, MailwaveError, Message, html_to_text


def _make_box(handler: httpx.MockTransport) -> Mailwave:
    box = Mailwave()
    box._client = httpx.Client(transport=handler, follow_redirects=True)
    return box


def test_html_to_text_strips_markup() -> None:
    markup = "<style>x{}</style><p>Merhaba&nbsp;d&uuml;nya</p><div>Kod: <b>123456</b></div>"
    assert html_to_text(markup) == "Merhaba dünya\nKod: 123456"


def test_message_from_api() -> None:
    msg = Message.from_api(
        {"id": 7, "from": "A", "from_email": "a@x.com", "subject": "Hi", "code": "4242"}
    )
    assert (msg.id, msg.sender_email, msg.code) == ("7", "a@x.com", "4242")


def test_open_and_messages() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, text='<meta name="csrf-token" content="tok">')
        assert request.read() == b'{"_token":"tok","captcha":""}'
        return httpx.Response(
            200,
            json={
                "status": True,
                "mailbox": "abc@radeshop.com",
                "messages": [{"id": 1, "from_email": "a@x.com", "subject": "S"}],
            },
        )

    box = _make_box(httpx.MockTransport(handler))
    assert box.open() == "abc@radeshop.com"
    assert [m.subject for m in box.messages()] == ["S"]


def test_read_follows_iframe_src() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/view/1":
            return httpx.Response(200, text='<iframe id="myContent" src="/raw/1"></iframe>')
        return httpx.Response(200, text="<p>Doğrulama kodu 999</p>")

    box = _make_box(httpx.MockTransport(handler))
    assert box.read("1") == "Doğrulama kodu 999"


def test_rate_limit_raises() -> None:
    box = _make_box(httpx.MockTransport(lambda r: httpx.Response(429)))
    with pytest.raises(MailwaveError):
        box._post("get_messages", captcha="")


def test_main_reports_errors(capsys: pytest.CaptureFixture[str]) -> None:
    def boom(self: Mailwave) -> str:
        raise MailwaveError("kapalı")

    original = Mailwave.open
    Mailwave.open = boom  # type: ignore[method-assign]
    try:
        assert mailwave.main([]) == 1
    finally:
        Mailwave.open = original  # type: ignore[method-assign]
    assert "kapalı" in capsys.readouterr().err
