"""Runtime compatibility patches for the bundled LinkedIn automation package."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def apply_linkedin_cli_runtime_patches() -> None:
    """Make profile controls discoverable when LinkedIn changes top-card markup."""
    from linkedin_cli.browser import nav
    from linkedin_cli.exceptions import SkipProfile

    fallback_selectors = [
        'main section:has(button[aria-label*="Invite"][aria-label*="to connect"])',
        'main section:has(button:has(span:text-is("Connect")))',
        'main section:has(button[aria-label*="Pending"])',
        'main section:has(button[aria-label*="More actions"])',
    ]
    for selector in fallback_selectors:
        if selector not in nav.TOP_CARD_SELECTORS:
            nav.TOP_CARD_SELECTORS.append(selector)

    def find_top_card(session):
        top_card = nav.find_first_visible(session.page, nav.TOP_CARD_SELECTORS)
        if top_card is not None:
            return top_card
        if "/in/" in session.page.url:
            logger.warning(
                "Top card wrapper not found on %s; falling back to main profile content",
                session.page.url,
            )
            return session.page.locator("main").first
        logger.warning("Top card not found on %s", session.page.url)
        raise SkipProfile("Top Card section not found")

    nav.find_top_card = find_top_card
