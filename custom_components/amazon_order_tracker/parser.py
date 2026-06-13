"""Email parsers for Amazon order states."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re

from .const import (
    STATUS_CANCELLED,
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
class ParsedOrderEvent:
    """An order event parsed from an email scan pass."""

    order_id: str
    source: str
    event_type: str
    status: str
    message_id: str
    subject: str
    updated_at: datetime | None
    origin: str | None = None
    diagnostic_reason: str | None = None
    medication_name: str | None = None
    user_name: str | None = None


def parse_message_event(
    message: MailMessage, event_type: str, include_pharmacy: bool
) -> ParsedOrderEvent | None:
    """Parse a message into an order event for a targeted scan pass."""
    raw_text = _strip_html(f"{message.subject}\n{message.body}")
    text = _clean_text(raw_text)
    sender = message.sender.lower()
    subject = _clean_text(message.subject)
    lowered_subject = subject.lower()
    lowered_preview = _message_preview(message).lower()

    amazon_order = AMAZON_ORDER_RE.search(text)
    if amazon_order:
        status = _status_for_event_type(event_type, lowered_subject, lowered_preview)
        if status is None:
            return _diagnostic_event(
                message,
                amazon_order.group(1),
                event_type,
                "ignored_message_type",
            )
        if _is_obvious_non_order_message(lowered_subject, lowered_preview):
            return _diagnostic_event(
                message,
                amazon_order.group(1),
                event_type,
                "obvious_non_order_message",
            )
        return ParsedOrderEvent(
            order_id=amazon_order.group(1),
            source="amazon",
            event_type=event_type,
            status=status,
            message_id=message.message_id,
            subject=message.subject,
            updated_at=message.date,
            origin=_origin_for_event_type(event_type),
        )

    if include_pharmacy and _looks_like_pharmacy_message(sender, text.lower()):
        pharmacy_order = PHARMACY_ORDER_RE.search(text)
        if pharmacy_order:
            medication = _first_match(MEDICATION_RE, raw_text)
            user_name = _first_match(USER_RE, raw_text)
            return ParsedOrderEvent(
                order_id=pharmacy_order.group(1),
                source="pharmacy",
                event_type=event_type,
                status=_status_for_event_type(
                    event_type, lowered_subject, lowered_preview
                )
                or STATUS_PENDING,
                message_id=message.message_id,
                subject=message.subject,
                updated_at=message.date,
                origin=_origin_for_event_type(event_type),
                medication_name=medication,
                user_name=user_name,
            )

    return None


def parse_unknown_order_event(message: MailMessage) -> ParsedOrderEvent | None:
    """Parse an unknown-pass message without creating an active order."""
    raw_text = _strip_html(f"{message.subject}\n{message.body}")
    text = _clean_text(raw_text)
    amazon_order = AMAZON_ORDER_RE.search(text)
    if amazon_order is None:
        return None
    return _diagnostic_event(
        message,
        amazon_order.group(1),
        "unknown",
        "unknown_order_message",
    )


def _diagnostic_event(
    message: MailMessage, order_id: str, event_type: str, reason: str
) -> ParsedOrderEvent:
    """Build a non-active diagnostic event for known order-shaped messages."""
    return ParsedOrderEvent(
        order_id=order_id,
        source="amazon",
        event_type=event_type,
        status="unknown",
        message_id=message.message_id,
        subject=message.subject,
        updated_at=message.date,
        diagnostic_reason=reason,
    )


def _status_for_event_type(
    event_type: str, lowered_subject: str, lowered_preview: str
) -> str | None:
    """Return the status implied by a scan pass."""
    text = f"{lowered_subject} {lowered_preview}"
    if event_type == "ordered":
        return STATUS_PENDING
    if event_type == "delivered":
        return STATUS_DELIVERED
    if event_type == "problem":
        if "cancelled" in text or "canceled" in text:
            return STATUS_CANCELLED
        return STATUS_DELAYED
    if event_type == "shipped":
        if "out for delivery" in text:
            return STATUS_OUT_FOR_DELIVERY
        return STATUS_SHIPPED
    return None


def _origin_for_event_type(event_type: str) -> str | None:
    """Return a storage origin note for events that may lack order-created email."""
    if event_type == "delivered":
        return "delivered_without_order_created"
    if event_type == "shipped":
        return "shipment_without_order_created"
    if event_type == "problem":
        return "problem_without_order_created"
    return None


def _is_obvious_non_order_message(subject: str, preview: str) -> bool:
    """Return true for Amazon messages that should not create active orders."""
    text = f"{subject} {preview}"
    blocked_terms = (
        "refund",
        "return received",
        "return started",
        "write a review",
        "review your purchase",
        "customer service",
        "support",
    )
    return any(term in text for term in blocked_terms)


def _message_preview(message: MailMessage) -> str:
    """Return a small cleaned body prefix for subject-adjacent classification."""
    return _clean_text(message.body[:2000])


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
