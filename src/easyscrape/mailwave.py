"""mailwave.dev üzerinden geçici e-posta adresi alır ve gelen kutusunu okur."""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import unquote, urljoin

import httpx

BASE_URL = "https://mailwave.dev/"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
_CSRF_RE = re.compile(r'name="csrf-token"\s+content="([^"]+)"')
_IFRAME_RE = re.compile(r"<iframe[^>]*id=[\"']myContent[\"'][^>]*>", re.I)
_ATTR_RE = r"""{name}\s*=\s*(?:"([^"]*)"|'([^']*)')"""


class MailwaveError(RuntimeError):
    pass


@dataclass(frozen=True)
class Message:
    id: str
    sender: str
    sender_email: str
    subject: str
    received_at: str
    code: str | None

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> Message:
        return cls(
            id=str(raw.get("id", "")),
            sender=str(raw.get("from") or ""),
            sender_email=str(raw.get("from_email") or ""),
            subject=str(raw.get("subject") or ""),
            received_at=str(raw.get("receivedAt") or ""),
            code=str(raw["code"]) if raw.get("code") else None,
        )


def html_to_text(markup: str) -> str:
    markup = re.sub(r"(?is)<(script|style|head)\b.*?</\1>", "", markup)
    markup = re.sub(r"(?i)<br\s*/?>|</(p|div|tr|li|h\d)>", "\n", markup)
    text = html.unescape(re.sub(r"<[^>]+>", "", markup))
    lines = (re.sub(r"[ \t\xa0]+", " ", line).strip() for line in text.splitlines())
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def _attr(tag: str, name: str) -> str | None:
    match = re.search(_ATTR_RE.format(name=name), tag, re.I)
    if not match:
        return None
    return html.unescape(match.group(1) if match.group(1) is not None else match.group(2))


class Mailwave:
    """Tek bir geçici posta kutusunu (oturum çerezine bağlı) yönetir."""

    def __init__(self, lang: str = "tr", timeout: float = 30.0) -> None:
        self._lang = lang
        self._client = httpx.Client(
            headers={"User-Agent": USER_AGENT, "Accept-Language": lang},
            follow_redirects=True,
            timeout=timeout,
        )
        self._csrf = ""
        self.address = ""

    def __enter__(self) -> Mailwave:
        self.open()
        return self

    def __exit__(self, *exc: object) -> None:
        self._client.close()

    def open(self) -> str:
        page = self._client.get(urljoin(BASE_URL, self._lang))
        match = _CSRF_RE.search(page.text)
        if page.status_code != 200 or not match:
            raise MailwaveError(f"Mailwave açılamadı (HTTP {page.status_code}).")
        self._csrf = match.group(1)
        self.address = str(self._post("get_messages", captcha="")["mailbox"])
        return self.address

    def _post(self, path: str, **fields: str) -> dict[str, Any]:
        xsrf = self._client.cookies.get("XSRF-TOKEN") or ""
        response = self._client.post(
            urljoin(BASE_URL, path),
            json={"_token": self._csrf, **fields},
            headers={
                "X-XSRF-TOKEN": unquote(xsrf),
                "X-Requested-With": "XMLHttpRequest",
                "Referer": urljoin(BASE_URL, self._lang),
                "Accept": "application/json",
            },
        )
        if response.status_code == 429:
            raise MailwaveError("Çok fazla istek (HTTP 429); biraz bekleyin.")
        try:
            data = response.json()
        except ValueError:
            data = None
        if response.status_code != 200 or not isinstance(data, dict):
            raise MailwaveError(f"{path} başarısız (HTTP {response.status_code}).")
        if data.get("status") is False:
            raise MailwaveError(str(data.get("message") or f"{path} reddedildi."))
        return data

    def messages(self) -> list[Message]:
        data = self._post("get_messages", captcha="")
        self.address = str(data.get("mailbox") or self.address)
        return [Message.from_api(m) for m in data.get("messages", [])]

    def read(self, message_id: str) -> str:
        view = self._client.get(urljoin(BASE_URL, f"view/{message_id}"))
        if view.status_code != 200:
            raise MailwaveError(f"Mesaj açılamadı (HTTP {view.status_code}).")
        tag = _IFRAME_RE.search(view.text)
        if not tag:
            return html_to_text(view.text)
        srcdoc = _attr(tag.group(0), "srcdoc")
        if srcdoc is not None:
            return html_to_text(srcdoc)
        src = _attr(tag.group(0), "src")
        if src:
            return html_to_text(self._client.get(urljoin(str(view.url), src)).text)
        return html_to_text(view.text)

    def wait_for_message(self, timeout: float, interval: float = 5.0) -> Message | None:
        deadline = time.monotonic() + timeout
        while True:
            inbox = self.messages()
            if inbox:
                return inbox[0]
            if time.monotonic() >= deadline:
                return None
            time.sleep(interval)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="easyscrape-mail", description="mailwave.dev'den geçici e-posta adresi alır."
    )
    parser.add_argument("--wait", type=float, metavar="SN", help="Bu kadar saniye mail bekle")
    parser.add_argument("--read", action="store_true", help="Gelen mailin metnini de yazdır")
    parser.add_argument("--json", action="store_true", help="Çıktıyı JSON olarak ver")
    args = parser.parse_args(argv)

    try:
        with Mailwave() as box:
            result: dict[str, Any] = {"address": box.address, "messages": []}
            if args.wait:
                print(f"Adres: {box.address} — mail bekleniyor...", file=sys.stderr)
                first = box.wait_for_message(args.wait)
                inbox = box.messages() if first else []
            else:
                inbox = box.messages()
            for msg in inbox:
                item: dict[str, Any] = {
                    "id": msg.id,
                    "from": msg.sender_email,
                    "subject": msg.subject,
                    "received_at": msg.received_at,
                    "code": msg.code,
                }
                if args.read:
                    item["body"] = box.read(msg.id)
                result["messages"].append(item)
    except (MailwaveError, httpx.HTTPError) as exc:
        print(f"Hata: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(result["address"])
        for item in result["messages"]:
            code = f" [kod: {item['code']}]" if item["code"] else ""
            print(f"- {item['from']}: {item['subject']}{code}")
            if "body" in item:
                print(item["body"], end="\n\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
