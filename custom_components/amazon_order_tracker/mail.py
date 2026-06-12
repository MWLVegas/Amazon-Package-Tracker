"""IMAP helpers for Amazon Order Tracker."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from email import message_from_bytes
from email.message import Message
from email.policy import default
from email.utils import parsedate_to_datetime
import imaplib
import logging
import socket
from typing import Iterable

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class ImapSettings:
    """IMAP connection settings."""

    server: str
    port: int
    username: str
    password: str
    mailbox: str


@dataclass(frozen=True)
class ImapLoginTestResult:
    """Result of testing IMAP settings."""

    success: bool
    error: str | None = None


@dataclass(frozen=True)
class MailMessage:
    """Minimal message payload used by parsers."""

    message_id: str
    subject: str
    sender: str
    date: datetime | None
    body: str


def test_imap_login(settings: ImapSettings) -> ImapLoginTestResult:
    """Test connection, login, and mailbox access separately."""
    try:
        client = imaplib.IMAP4_SSL(settings.server, settings.port)
    except (OSError, TimeoutError, socket.gaierror):
        return ImapLoginTestResult(False, "cannot_connect")

    try:
        try:
            client.login(settings.username, _normalize_password(settings.password))
        except imaplib.IMAP4.error as err:
            LOGGER.warning("Gmail rejected IMAP login for %s: %s", settings.username, err)
            return ImapLoginTestResult(False, "invalid_auth")

        try:
            status, _data = client.select(settings.mailbox, readonly=True)
        except imaplib.IMAP4.error:
            return ImapLoginTestResult(False, "mailbox_not_found")

        if status != "OK":
            return ImapLoginTestResult(False, "mailbox_not_found")

        return ImapLoginTestResult(True)
    finally:
        try:
            client.logout()
        except imaplib.IMAP4.error:
            pass


def fetch_candidate_messages(
    settings: ImapSettings, lookback_days: int
) -> list[MailMessage]:
    """Fetch likely Amazon order messages from IMAP."""
    since = (datetime.now() - timedelta(days=lookback_days)).strftime("%d-%b-%Y")
    criteria = f'(SINCE "{since}")'

    with imaplib.IMAP4_SSL(settings.server, settings.port) as client:
        client.login(settings.username, _normalize_password(settings.password))
        client.select(settings.mailbox, readonly=True)
        status, data = client.search(None, criteria)
        if status != "OK" or not data:
            return []

        messages: list[MailMessage] = []
        for message_num in data[0].split():
            status, fetched = client.fetch(message_num, "(RFC822)")
            if status != "OK":
                continue
            for part in fetched:
                if not isinstance(part, tuple):
                    continue
                parsed = _parse_message(part[1])
                if parsed is not None:
                    messages.append(parsed)
        return messages


def _parse_message(raw_message: bytes) -> MailMessage | None:
    msg = message_from_bytes(raw_message, policy=default)
    message_id = str(msg.get("Message-ID") or "")
    subject = str(msg.get("Subject") or "")
    sender = str(msg.get("From") or "")
    parsed_date = _parse_message_date(str(msg.get("Date") or ""))
    body = "\n".join(_message_text_parts(msg))

    if not message_id or not body:
        return None

    return MailMessage(
        message_id=message_id,
        subject=subject,
        sender=sender,
        date=parsed_date,
        body=body,
    )


def _parse_message_date(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None


def _message_text_parts(msg: Message) -> Iterable[str]:
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            disposition = str(part.get("Content-Disposition") or "")
            if "attachment" in disposition:
                continue
            if content_type in {"text/plain", "text/html"}:
                yield _decode_part(part)
        return

    yield _decode_part(msg)


def _decode_part(part: Message) -> str:
    payload = part.get_payload(decode=True)
    if payload is None:
        return str(part.get_payload() or "")
    charset = part.get_content_charset() or "utf-8"
    return payload.decode(charset, errors="replace")


def _normalize_password(password: str) -> str:
    """Normalize Google app passwords copied in grouped format."""
    return "".join(password.split())
