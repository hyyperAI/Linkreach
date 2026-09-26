# External Services

> **Purpose:** Inventory external systems, their configuration, and failure behavior.
> **Read this before:** Adding or changing APIs, network calls, credentials, retries, or provider options.
> **Source files:** `linkreach/core/llm.py`, `linkreach/contacts/service.py`, `linkreach/emails/bettercontact.py`, `linkreach/emails/smtp.py`, `linkreach/linkedin/ml/hub.py`

| Service | Purpose | Configuration | Failure policy |
|---|---|---|---|
| LinkedIn / Voyager | login, profiles, status, messages, actions | LinkedInProfile credentials/cookies | auth errors trigger reauthentication; checkpoints stop work |
| AI provider | qualification, summaries, drafts, follow-up decisions | SiteConfig model/key/base URL | validation before save; runtime errors normally fail work |
| BetterContact | work-email lookup | SiteConfig BetterContact key | unavailable returns retryable `None`; miss returns `False` |
| Contacts hub | free resolve and contribution | SiteConfig token/URL and profile contribution flag | best effort; outages do not fail core workflow |
| SMTP mailbox | one-shot outbound email | Mailbox rows | auth checked on import; send failure fails Task |
| Hugging Face | freemium campaign kit download | repository constant/cache | optional; failed load returns no kit |
| Google Fonts/CDNs | fonts, Tailwind runtime, HTMX, Lucide, Chart.js | URLs in base template | dashboard styling/behavior degrades when offline |

AI provider IDs use `provider:model`. Native OpenAI and Anthropic builders ignore
custom base URLs; `openai_compatible:*` requires `llm_api_base`. The dashboard maps
Grok and MiniMax/custom providers into that compatible path.

The contacts contribution client geo-filters locally, but the remote service is the
authoritative privacy gate. Raw profile text is not contributed; a cached embedding
may be attached.

