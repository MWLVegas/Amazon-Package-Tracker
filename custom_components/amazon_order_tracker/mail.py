"""IMAP helpers for Amazon Order Tracker."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from email import message_from_bytes
from email.message import Message
from email.policy import default
from email.utils import parsedate_to_datetime
import imaplib
import logging
import socket
from typing import NamedTuple

LOGGER = logging.getLogger(__name__)
IMAP_TIMEOUT_SECONDS = 30
MAX_MESSAGES_PER_PASS = 25
MAX_UNKNOWN_MESSAGES_PER_PASS = 10
MAX_FETCH_BYTES = 65536
MAX_BODY_CHARS = 30000


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


class SearchResult(NamedTuple):
    """Message identifiers returned by a scan-pass search."""

    message_nums: list[bytes]
    use_uid: bool


SCAN_PASSES: tuple[str, ...] = (
    "ordered",
    "delivered",
    "problem",
    "shipped",
    "unknown",
)

GMAIL_RAW_QUERIES = {
    "ordered": '("your order" OR "you ordered" OR "order confirmation") -refund -return -review',
    "delivered": '("delivered" OR "was delivered")',
    "problem": '("delayed" OR "running late" OR "arriving late" OR "cancelled" OR "canceled" OR "unable to deliver" OR "delivery attempted")',
    "shipped": '("has shipped" OR "shipped" OR "out for delivery" OR "on the way")',
    "unknown": '("order #" OR "order number" OR "order:")',
}

IMAP_PASS_SEARCH_TERMS = {
    "ordered": (
        ("SUBJECT", "your order"),
        ("SUBJECT", "you ordered"),
        ("SUBJECT", "order confirmation"),
    ),
    "delivered": (
        ("SUBJECT", "delivered"),
        ("BODY", "was delivered"),
    ),
    "problem": (
        ("SUBJECT", "delayed"),
        ("SUBJECT", "running late"),
        ("SUBJECT", "arriving late"),
        ("SUBJECT", "cancelled"),
        ("SUBJECT", "canceled"),
        ("SUBJECT", "unable to deliver"),
        ("SUBJECT", "delivery attempted"),
    ),
    "shipped": (
        ("SUBJECT", "has shipped"),
        ("SUBJECT", "shipped"),
        ("SUBJECT", "out for delivery"),
        ("SUBJECT", "on the way"),
    ),
    "unknown": (
        ("BODY", "order #"),
        ("BODY", "order number"),
    ),
}


def test_imap_login(settings: ImapSettings) -> ImapLoginTestResult:
    """Test connection, login, and mailbox access separately."""
    try:
        client = imaplib.IMAP4_SSL(
            settings.server, settings.port, timeout=IMAP_TIMEOUT_SECONDS
        )
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


def fetch_messages_by_pass(
    settings: ImapSettings, scan_from: datetime
) -> dict[str, list[MailMessage]]:
    """Fetch likely Amazon order messages from IMAP grouped by scan pass."""
    since = scan_from.strftime("%d-%b-%Y")

    with imaplib.IMAP4_SSL(
        settings.server, settings.port, timeout=IMAP_TIMEOUT_SECONDS
    ) as client:
        client.login(settings.username, _normalize_password(settings.password))
        client.select(settings.mailbox, readonly=True)
        use_gmail_search = _is_gmail_server(settings.server)
        messages_by_pass: dict[str, list[MailMessage]] = {}

        for pass_name in SCAN_PASSES:
            search_result = _search_pass(client, pass_name, since, use_gmail_search)
            messages_by_pass[pass_name] = _fetch_messages(
                client, search_result.message_nums, search_result.use_uid
            )

        return messages_by_pass


def _search_pass(
    client: imaplib.IMAP4_SSL,
    pass_name: str,
    since: str,
    use_gmail_search: bool,
) -> SearchResult:
    """Search message ids for one targeted pass."""
    if use_gmail_search:
        message_nums = _gmail_raw_search(client, pass_name, since)
        if message_nums:
            return SearchResult(_limit_message_nums(pass_name, message_nums), True)

    found: set[bytes] = set()
    for field, term in IMAP_PASS_SEARCH_TERMS[pass_name]:
        status, data = client.search(None, "SINCE", since, field, f'"{term}"')
        if status != "OK" or not data:
            continue
        found.update(data[0].split())
    return SearchResult(
        _limit_message_nums(pass_name, sorted(found, key=lambda value: int(value))),
        False,
    )


def _gmail_raw_search(
    client: imaplib.IMAP4_SSL, pass_name: str, since: str
) -> list[bytes]:
    """Use Gmail's raw search when available."""
    raw_since = datetime.strptime(since, "%d-%b-%Y").strftime("%Y/%m/%d")
    query = f'after:{raw_since} {GMAIL_RAW_QUERIES[pass_name]}'
    quoted_query = query.replace('"', r"\"")
    try:
        status, data = client.uid("SEARCH", "X-GM-RAW", f'"{quoted_query}"')
    except imaplib.IMAP4.error:
        return []
    if status != "OK" or not data:
        return []
    return data[0].split()


def _fetch_messages(
    client: imaplib.IMAP4_SSL, message_nums: list[bytes], use_uid: bool
) -> list[MailMessage]:
    """Fetch and parse message payloads for IMAP message ids or UIDs."""
    messages: list[MailMessage] = []
    fetch_parts = f"(BODY.PEEK[]<0.{MAX_FETCH_BYTES}>)"
    for message_num in message_nums:
        try:
            if use_uid:
                status, fetched = client.uid("FETCH", message_num, fetch_parts)
            else:
                status, fetched = client.fetch(message_num, fetch_parts)
        except imaplib.IMAP4.error as err:
            LOGGER.warning("Skipping IMAP message fetch after server error: %s", err)
            continue
        if status != "OK":
            continue
        for part in fetched:
            if not isinstance(part, tuple):
                continue
            parsed = _parse_message(part[1])
            if parsed is not None:
                messages.append(parsed)
    return messages


def _limit_message_nums(pass_name: str, message_nums: list[bytes]) -> list[bytes]:
    """Limit downloads to the newest likely matches so scans stay bounded."""
    limit = (
        MAX_UNKNOWN_MESSAGES_PER_PASS
        if pass_name == "unknown"
        else MAX_MESSAGES_PER_PASS
    )
    if len(message_nums) > limit:
        LOGGER.warning(
            "Amazon Order Tracker %s scan matched %s messages; fetching newest %s",
            pass_name,
            len(message_nums),
            limit,
        )
    return message_nums[-limit:]


def _is_gmail_server(server: str) -> bool:
    """Return whether Gmail-specific IMAP extensions are likely available."""
    return "gmail" in server.lower()


def _parse_message(raw_message: bytes) -> MailMessage | None:
    raw_message = raw_message[:MAX_FETCH_BYTES]
    msg = message_from_bytes(raw_message, policy=default)
    message_id = str(msg.get("Message-ID") or "")
    subject = str(msg.get("Subject") or "")
    sender = str(msg.get("From") or "")
    parsed_date = _parse_message_date(str(msg.get("Date") or ""))
    body = _message_text(msg)

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


def _message_text(msg: Message) -> str:
    """Return bounded text from useful message parts."""
    chunks: list[str] = []
    remaining = MAX_BODY_CHARS

    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            disposition = str(part.get("Content-Disposition") or "")
            if "attachment" in disposition:
                continue
            if content_type in {"text/plain", "text/html"}:
                text = _decode_part(part, remaining)
                if text:
                    chunks.append(text)
                    remaining -= len(text)
                if remaining <= 0:
                    break
        return "\n".join(chunks)[:MAX_BODY_CHARS]

    return _decode_part(msg, remaining)[:MAX_BODY_CHARS]


def _decode_part(part: Message, limit: int) -> str:
    if limit <= 0:
        return ""
    payload = part.get_payload(decode=True)
    if payload is None:
        return str(part.get_payload() or "")[:limit]
    charset = part.get_content_charset() or "utf-8"
    return payload[:MAX_FETCH_BYTES].decode(charset, errors="replace")[:limit]


def _normalize_password(password: str) -> str:
    """Normalize Google app passwords copied in grouped format."""
    return "".join(password.split())
