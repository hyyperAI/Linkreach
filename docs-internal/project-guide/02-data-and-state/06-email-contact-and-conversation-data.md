# Email, Contact, And Conversation Data

> **Purpose:** Explain how sensitive contact and communication records are stored and routed.
> **Read this before:** Changing enrichment, email status, SMTP, contact contribution, messages, or summaries.
> **Source files:** `linkreach/crm/models/lead.py:23`, `linkreach/crm/models/deal.py:82`, `linkreach/emails/models.py:30`, `linkreach/chat/models.py:9`

## Contact sources

- `Lead.contact_info` is the raw LinkedIn contact overlay captured after connection.
- `Lead.api_email` is one work email from contacts hub, BetterContact, or import.
- the UI derives a single display email without fabricating data.

## Email route

Email enrichment runs only when at least one Mailbox exists. A hit routes the Deal
to Ready to Email. The email task selects a mailbox below its daily cap, generates
one opener, sends it through SMTP, records mailbox/subject/time/Message-ID, and moves
the Deal to Emailed.

## LinkedIn conversation route

Chat synchronization upserts `ChatMessage` records by `(deal, linkedin_urn)`.
Incoming messages may update `Deal.chat_summary`; outgoing seller messages are
excluded from fact extraction. The follow-up agent receives summaries plus a small
verbatim message window.

## Privacy and display

Do not expose contact overlays or secrets merely because they are stored. Display
only operator-useful fields. Exports contain personal data and must honor active
filters. Logs must avoid email bodies, credentials, cookies, and raw contacts.

