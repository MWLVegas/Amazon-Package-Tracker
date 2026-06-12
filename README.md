# Amazon Order Tracker for Home Assistant

Personal HACS custom integration for tracking Amazon order status emails from Gmail.

This integration connects to Gmail over IMAP, scans Amazon order emails, stores order state locally in Home Assistant, and exposes sensors for active orders by status.

## Features

- Tracks Amazon order messages from Gmail over IMAP.
- Groups messages by order number.
- Tracks statuses:
  - Pending shipping
  - Shipped
  - Out for delivery
  - Delivered
  - Delayed
- Archives delivered orders after a configurable number of hours.
- Keeps pharmacy orders in a separate bucket with medication and user names.

## Installation

1. Add this repository to HACS as a custom repository with category `Integration`.
2. Install **Amazon Order Tracker**.
3. Restart Home Assistant.
4. Go to **Settings > Devices & services > Add Integration** and search for **Amazon Order Tracker**.

## Gmail Setup

Use IMAP, not SMTP. SMTP is for sending mail.

For a personal Gmail account, create a Google app password and use:

- IMAP server: `imap.gmail.com`
- Port: `993`
- Username: your Gmail address
- Password: your app password

## Privacy

This integration stores order metadata locally in Home Assistant storage. Pharmacy tracking is personal-only and intentionally isolated in the code so it can be removed before any public release.

## Notes

Amazon email formats can vary. The parser is deliberately conservative and can be extended as your real messages reveal more patterns.
