# linkreach/linkedin/tasks/connect.py
"""Connect task — resolves one candidate from the campaign pool and acts.

Lazy: the task payload carries only ``campaign_id``. The handler picks
its candidate at execution time via the campaign's ``ConnectStrategy``.
No self-rescheduling — pacing is owned by ``tasks/scheduler.py``.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable

from termcolor import colored

from linkreach.core.db.deals import increment_connect_attempts, set_profile_state
from linkreach.crm.models import DealState
from linkreach.linkedin.db.leads import disqualify_lead
from linkreach.linkedin.ml.qualifier import BayesianQualifier
from linkreach.linkedin.models import ActionLog
from linkedin_cli.exceptions import ProfileInaccessibleError, ReachedConnectionLimit, SkipProfile

logger = logging.getLogger(__name__)

MAX_CONNECT_ATTEMPTS = 3


@dataclass
class ConnectStrategy:
    find_candidate: Callable
    pre_connect: Callable | None
    qualifier: object


def strategy_for(campaign, qualifiers):
    """Build the right ConnectStrategy based on campaign type."""
    if campaign.outreach_mode == campaign.OutreachMode.CSV_PERSONALIZED:
        from linkreach.core.db.deals import get_ready_to_connect_profiles

        return ConnectStrategy(
            find_candidate=lambda s: next(iter(get_ready_to_connect_profiles(s)), None),
            pre_connect=None,
            qualifier=None,
        )

    qualifier = qualifiers.get(campaign.pk)
    if qualifier is None and not campaign.is_freemium:
        # Task belongs to a campaign that wasn't in the session's cached
        # campaign list (typically: user not attached to that campaign, or the
        # campaign was added mid-run). Build a qualifier on the fly from
        # whatever labelled data exists so the connect handler can still make
        # a decision — the GP falls back to prior-only (unfitted) when the
        # campaign has no labels, so this is safe even on cold start. Freemium
        # campaigns without a kit qualifier are still a real skip: they have
        # no local training data path.
        from linkreach.core.conf import CAMPAIGN_CONFIG
        from linkreach.crm.models import Lead

        qualifier = BayesianQualifier(
            seed=42,
            n_mc_samples=CAMPAIGN_CONFIG["qualification_n_mc_samples"],
            campaign=campaign,
        )
        X, y = Lead.get_labeled_arrays(campaign)
        if len(X) > 0:
            qualifier.warm_start(X, y)
        qualifiers[campaign.pk] = qualifier
        logger.warning(
            "Qualifier missing for campaign %s (%s) — built on demand from %d labelled samples. "
            "Attach the operator user to this campaign to avoid this on next daemon startup.",
            campaign.pk, campaign, len(X),
        )

    if campaign.is_freemium:
        from linkreach.core.db.deals import create_freemium_deal
        from linkreach.linkedin.pipeline.freemium_pool import find_freemium_candidate

        return ConnectStrategy(
            find_candidate=lambda s: find_freemium_candidate(s, qualifier),
            pre_connect=lambda s, pid: create_freemium_deal(s, pid),
            qualifier=qualifier,
        )

    from linkreach.linkedin.pipeline.pools import find_candidate

    return ConnectStrategy(
        find_candidate=lambda s: find_candidate(s, qualifier),
        pre_connect=None,
        qualifier=qualifier,
    )


def handle_connect(task, session, qualifiers):
    from linkedin_cli.actions.connect import send_connection_request
    from linkedin_cli.actions.status import get_connection_status

    campaign = session.campaign
    strategy = strategy_for(campaign, qualifiers)

    if not session.linkedin_profile.can_execute(ActionLog.ActionType.CONNECT):
        logger.info("[%s] connect: daily limit reached — slot skipped", campaign)
        return

    candidate = strategy.find_candidate(session)
    if candidate is None:
        logger.info("[%s] connect: no candidate available — slot skipped", campaign)
        return

    public_id = candidate["public_identifier"]
    profile = candidate.get("profile") or candidate

    # Freemium campaigns need a Deal before set_profile_state
    if strategy.pre_connect:
        strategy.pre_connect(session, public_id)

    from linkreach.crm.models import Deal

    deal = Deal.objects.filter(
        lead__public_identifier=public_id,
        campaign=session.campaign,
    ).first()
    reason = deal.reason if deal else ""
    stats = strategy.qualifier.explain(candidate, session) if strategy.qualifier else ""
    logger.info("[%s] %s", campaign, colored("▶ connect", "cyan", attrs=["bold"]))
    logger.info("[%s] %s (%s) — %s", campaign, public_id, stats, reason or "")

    try:
        # The library observes a UI state and returns it as a str; lift it into
        # our funnel enum at the boundary.
        status = DealState(get_connection_status(session, profile).value)

        if status in (DealState.CONNECTED, DealState.PENDING):
            # set_profile_state fires on_deal_state_entered, which stamps
            # next_check_pending_at on PENDING and no-ops on CONNECTED.
            set_profile_state(session, public_id, status.value)
            return

        # get_connection_status already navigated to the profile page
        new_state = DealState(send_connection_request(session=session, profile=profile).value)

        if new_state == DealState.QUALIFIED:
            # No Connect button found — track attempt, disqualify after MAX_CONNECT_ATTEMPTS
            attempts = increment_connect_attempts(session, public_id)
            if attempts >= MAX_CONNECT_ATTEMPTS:
                reason = f"Unreachable: no Connect button after {attempts} attempts"
                if campaign.outreach_mode != campaign.OutreachMode.CSV_PERSONALIZED:
                    disqualify_lead(public_id)
                set_profile_state(session, public_id, DealState.FAILED.value, reason=reason)
                logger.warning("Disqualified %s — %s", public_id, reason)
            else:
                set_profile_state(session, public_id, new_state.value)
                logger.debug("%s: connect attempt %d/%d — no button found", public_id, attempts, MAX_CONNECT_ATTEMPTS)
        else:
            set_profile_state(session, public_id, new_state.value)
            session.linkedin_profile.record_action(
                ActionLog.ActionType.CONNECT, session.campaign,
            )

    except ReachedConnectionLimit as e:
        logger.warning("Rate limited: %s", e)
        session.linkedin_profile.mark_exhausted(ActionLog.ActionType.CONNECT)
    except ProfileInaccessibleError as e:
        logger.warning("Profile inaccessible — marking FAILED: %s", e)
        set_profile_state(session, public_id, DealState.FAILED.value,
                          reason=f"Profile inaccessible: {e}")
    except SkipProfile as e:
        logger.warning("Skipping %s: %s", public_id, e)
        reason = f"Profile unavailable: {e}"
        set_profile_state(session, public_id, DealState.FAILED.value, reason=reason)
