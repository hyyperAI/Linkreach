# Models And Schema Names

> **Purpose:** Map schema names to their actual ownership and responsibilities.
> **Read this before:** Writing queries, migrations, imports, exports, or deletion logic.
> **Source files:** `linkreach/core/models.py`, `linkreach/crm/models/`, `linkreach/linkedin/models.py`, `linkreach/emails/models.py`, `linkreach/chat/models.py`

| Model | App | Meaning | Important relation |
|---|---|---|---|
| `SiteConfig` | `core` | Global singleton for LLM and contact-service configuration | Always saved as `pk=1` |
| `BotProcess` | `core` | Global singleton describing the current or last daemon process | Optional `started_by` Django user |
| `Campaign` | `core` | Targeting, product context, objective, booking link, and ML data | M2M to users; parent of Deals |
| `Task` | `core` | Persistent scheduled work | Carries campaign id in JSON payload |
| `Lead` | `crm` | Cross-campaign LinkedIn identity | Parent of Deals; unique URL and public id |
| `Deal` | `crm` | Campaign-specific outreach state | Unique `(lead, campaign)` pair |
| `LinkedInProfile` | `linkedin` | Sender credentials, cookies, limits, and connection status | One-to-one with Django user |
| `SearchKeyword` | `linkedin` | Generated/discovered search input | Belongs to Campaign |
| `ActionLog` | `linkedin` | Connect/follow-up rate-limit ledger | Belongs to profile and Campaign |
| `Mailbox` | `emails` | SMTP sender and daily limit | Referenced by sent Deals using `SET_NULL` |
| `ChatMessage` | `chat` | Incoming or outgoing LinkedIn message | Belongs to Deal; URN unique per Deal |

Schema ownership was moved over time. Always use current imports from
`linkreach.core.models` and `linkreach.crm.models`; do not infer ownership
from old migration filenames.

