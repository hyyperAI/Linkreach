# Data Models

> **Purpose:** Describe durable fields and relationships without mixing in change instructions.
> **Read this before:** Writing ORM queries, serializers, imports, exports, or migrations.
> **Source files:** `linkreach/core/models.py:9`, `linkreach/crm/models/lead.py:11`, `linkreach/crm/models/deal.py:55`, `linkreach/linkedin/models.py:22`

## Core

`SiteConfig` stores one global AI model id, AI key/base URL, BetterContact key,
contacts token, and contacts URL. `BotProcess` stores one process record. `Campaign`
stores name, user membership, product docs, campaign objective, booking link,
freemium controls, seed ids, and serialized model data. `Task` stores type, status,
schedule, payload, and timestamps.

## CRM

`Lead` stores LinkedIn URL, public identifier, URN, country, embedding, raw contact
overlay, API email, permanent disqualification, and timestamps. It deliberately
does not store a permanent raw profile document; `get_profile()` reads live data.

`Deal` joins Lead and Campaign. It stores workflow state/outcome, reason, attempts,
pending-check timing, email sender metadata, profile/chat summaries, and timestamps.

## LinkedIn and communication

`LinkedInProfile` stores one user's sender credentials, cookies, rate limits, legal
and contribution flags, and connection status details. `ActionLog` is the daily
rate-limit ledger. `SearchKeyword` records campaign search inputs.

`Mailbox` stores SMTP credentials and a daily send cap. `ChatMessage` stores
campaign-specific LinkedIn conversation messages and direction.

## Invariants

- Lead identity is global; Deal state is campaign-specific.
- `contact_info is None` means contact capture has not succeeded yet.
- `contact_info={...empty...}` means capture succeeded but exposed no contact.
- `api_email` is one enrichment result, not all possible addresses.
- Task payloads should remain lazy and normally contain only `campaign_id`.
- Deal email timestamps and Message-ID are audit and future reply-correlation data.

