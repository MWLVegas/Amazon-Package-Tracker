"""Email parsers for Amazon order states."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re

from .const import (
    STATUS_DELAYED,
    STATUS_DELIVERED,
    STATUS_OUT_FOR_DELIVERY,
    STATUS_PENDING,
    STATUS_SHIPPED,
)
from .mail import MailMessage

AMAZON_ORDER_RE = re.compile(r"\b(?:order|order\s*#|order number)[:\s#-]*([0-9]{3}-[0-9]{7}-[0-9]{7})\b", re.I)
PHARMACY_ORDER_RE = re.compile(r"\b(?:rx|pharmacy|order)[:\s#-]*([A-Z0-9-]{6,})\b", re.I)
MEDICATION_RE = re.compile(r"\b(?:medication|medicine|prescription|rx)[:\s-]+([^\n\r<,;]+)", re.I)
USER_RE = re.compile(r"\b(?:patient|recipient|user)[:\s-]+([A-Z][A-Za-z .'-]{1,60})", re.I)


@dataclass(frozen=True)
class ParsedOrder:
    """An order update parsed from an email."""

    order_id: str
    source: str
    status: str
    message_id: str
    subject: str
    updated_at: datetime | None
    medication_name: str | None = None
    user_name: str | None = None


def parse_message(message: MailMessage, include_pharmacy: bool) -> ParsedOrder | None:
    """Parse a message into an order update."""
    raw_text = _strip_html(f"{message.subject}\n{message.body}")
    text = _clean_text(raw_text)
    sender = message.sender.lower()
    lowered = text.lower()

    amazon_order = AMAZON_ORDER_RE.search(text)
    if amazon_order:
        return ParsedOrder(
            order_id=amazon_order.group(1),
            source="amazon",
            status=_amazon_status(lowered),
            message_id=message.message_id,
            subject=message.subject,
            updated_at=message.date,
        )

    if include_pharmacy and _looks_like_pharmacy_message(sender, lowered):
        pharmacy_order = PHARMACY_ORDER_RE.search(text)
        if pharmacy_order:
            medication = _first_match(MEDICATION_RE, raw_text)
            user_name = _first_match(USER_RE, raw_text)
            return ParsedOrder(
                order_id=pharmacy_order.group(1),
                source="pharmacy",
                status=_amazon_status(lowered),
                message_id=message.message_id,
                subject=message.subject,
                updated_at=message.date,
                medication_name=medication,
                user_name=user_name,
            )

    return None


def _amazon_status(text: str) -> str:
    if "out for delivery" in text:
        return STATUS_OUT_FOR_DELIVERY
    if "delivered" in text or "was delivered" in text:
        return STATUS_DELIVERED
    if "delayed" in text or "running late" in text or "arriving late" in text:
        return STATUS_DELAYED
    if "shipped" in text or "on the way" in text:
        return STATUS_SHIPPED
    return STATUS_PENDING


def _looks_like_pharmacy_message(sender: str, text: str) -> bool:
    return "pharmacy" in sender or "pharmacy" in text or "prescription" in text


def _first_match(pattern: re.Pattern[str], text: str) -> str | None:
    match = pattern.search(text)
    if match is None:
        return None
    return match.group(1).strip(" .:-")


def _clean_text(text: str) -> str:
    text = _strip_html(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text)
