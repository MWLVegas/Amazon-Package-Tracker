# Changelog

## 0.1.6

- Re-evaluate parsed messages during each scan so state fixes can correct existing stored orders.
- Prevent lower-priority shipment updates from regressing delivered or archived orders.
- Add diagnostics for status emails that do not include a parseable order number.

## 0.1.5

- Add diagnostic sensors for stored, archived, scanned, parsed, and newly archived records.
- Track how many delivered orders are archived during each scan.

## 0.1.4

- Load the integration before the first mailbox scan completes so slow Gmail folders do not cancel setup.
- Add an IMAP connection timeout.

## 0.1.3

- Add setup guidance explaining that Gmail requires a Google App Password, not the normal Google account password.
- Clarify the Gmail authentication error message.

## 0.1.2

- Normalize copied Google app passwords by removing spaces before IMAP login.
- Log Gmail's IMAP authentication rejection text for troubleshooting.

## 0.1.1

- Preserve setup form values after failed IMAP validation.
- Add specific setup errors for server/port, Gmail authentication, and mailbox failures.

## 0.1.0

- Initial personal Amazon order tracker integration.
