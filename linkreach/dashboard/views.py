"""Dashboard views — additive, read-mostly.

Writes are limited to: Campaign create/edit/delete (standard ModelForm, same as the
Admin already allows) and adding seed URLs via the existing ``create_seed_leads``.
"""
from __future__ import annotations

import csv
import io
import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db.models import Count, Q
from django.http import HttpResponse
from django.urls import reverse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from linkreach.chat.models import ConversationEvent
from linkedin_cli.url_utils import public_id_to_url, url_to_public_id
from linkreach.core.models import Campaign, SiteConfig, Task
from linkreach.crm.models import Deal, DealState, Lead
from linkreach.dashboard import services
from linkreach.dashboard.forms import AISettingsForm, CampaignForm, LinkedInAccountForm
from linkreach.linkedin.models import LinkedInProfile
from linkreach.dashboard.linkedin_account_service import (
    account_context,
    request_verification,
    verification_in_progress,
)
from linkreach.linkedin.setup.seeds import create_seed_leads, parse_seed_urls


def _crumbs(*items):
    root = {"label": "Dashboard", "url": reverse("dashboard:overview")}
    return [root, *items]


def _user_campaigns(user):
    """Campaigns visible to the signed-in operator."""
    return Campaign.objects.filter(users=user)


def _user_deals(user):
    """Deals visible to the signed-in operator through campaign ownership."""
    return Deal.objects.filter(campaign__users=user)


def _owned_campaign_or_404(request, pk):
    return get_object_or_404(_user_campaigns(request.user), pk=pk)


def _owned_deal_or_404(request, pk):
    return get_object_or_404(
        _user_deals(request.user).select_related("lead", "campaign"),
        pk=pk,
    )


@login_required
def overview(request):
    labels, data = services.connects_last_30_days(request.user)
    current = sum(data[-7:])
    previous = sum(data[-14:-7])
    if previous:
        chart_trend = round(((current - previous) / previous) * 100, 1)
    elif current:
        chart_trend = 100
    else:
        chart_trend = 0
    return render(request, "dashboard/overview.html", {
        "active": "overview",
        "breadcrumbs": [{"label": "Dashboard"}],
        "page_title": "Overview",
        "page_description": "Campaign performance, lead quality, and active conversations in one place.",
        "stats": services.overview_stats(request.user),
        "chart_labels": json.dumps(labels),
        "chart_data": json.dumps(data),
        "chart_trend": chart_trend,
        "chart_trend_abs": abs(chart_trend),
        "chart_range": f"{labels[0]} - {labels[-1]}" if labels else "",
    })

@login_required
def linkedin_account(request):
    context = account_context(request.user)
    context.update({"active": "linkedin_account", "breadcrumbs": _crumbs({"label": "LinkedIn Account"}), "page_title": "LinkedIn Account", "page_description": "Connect and monitor the LinkedIn sender account used for outreach."})
    context["form"] = LinkedInAccountForm(instance=context["profile"])
    site_config = SiteConfig.load()
    context["api_form"] = AISettingsForm(site_config=site_config)
    context["api_key_saved"] = bool(site_config.llm_api_key)
    return render(request, "dashboard/linkedin_account.html", context)

@login_required
def linkedin_account_status(request):
    """HTMX fragment: status card only (polled while verifying)."""
    context = account_context(request.user)
    return render(request, "dashboard/_linkedin_status.html", context)

@login_required
def linkedin_account_save(request):
    profile = getattr(request.user, "linkedin_profile", None)
    password_changed = bool(request.POST.get("linkedin_password", "").strip())
    username_changed = bool(profile) and profile.linkedin_username != request.POST.get("linkedin_username", "").strip()
    credentials_changed = password_changed or username_changed or not profile
    form = LinkedInAccountForm(request.POST, instance=profile)
    if form.is_valid():
        obj = form.save(commit=False)
        obj.user = request.user
        if credentials_changed:
            obj.cookie_data = None
            obj.checkpoint_url = ""
            obj.last_error_code = ""
            obj.last_error_message = ""
            obj.connection_status = LinkedInProfile.ConnectionStatus.CREDENTIALS_SAVED if obj.legal_accepted else LinkedInProfile.ConnectionStatus.NOT_CONNECTED
            obj.last_connection_attempt_at = timezone.now()
        elif not obj.legal_accepted:
            obj.connection_status = LinkedInProfile.ConnectionStatus.NOT_CONNECTED
        obj.save()
        if credentials_changed:
            messages.success(request, 'LinkedIn account saved. Click "Start verification" below to connect it.')
        else:
            messages.success(request, "Account settings updated.")
    else: messages.error(request, "Please check the highlighted fields and try again.")
    return redirect("dashboard:linkedin_account")

@login_required
def linkedin_api_save(request):
    site_config = SiteConfig.load()
    if request.method == "POST":
        form = AISettingsForm(request.POST, site_config=site_config)
        if form.is_valid():
            form.save()
            messages.success(request, "AI API settings updated.")
        else:
            for field, errors in form.errors.items():
                label = form.fields[field].label if field in form.fields else "AI settings"
                messages.error(request, f"{label}: {' '.join(errors)}")
    return redirect("dashboard:linkedin_account")

@login_required
def linkedin_account_action(request, action):
    profile = get_object_or_404(LinkedInProfile, user=request.user)
    if request.method == "POST":
        if action == "pause":
            profile.active = False; profile.save(update_fields=["active"])
            messages.success(request, "Automation paused.")
        elif action == "resume":
            profile.active = True; profile.save(update_fields=["active"])
            messages.success(request, "Automation resumed.")
        elif action in ("verify", "reconnect"):
            if not profile.linkedin_username or not profile.linkedin_password:
                messages.error(request, "Add your LinkedIn email and password before verifying.")
            elif not profile.legal_accepted:
                messages.error(request, "Accept the safety and legal guidelines before verifying.")
            elif verification_in_progress(profile.pk):
                messages.info(request, "Verification is already running — a browser window is open on this machine.")
            else:
                if action == "reconnect":
                    profile.cookie_data = None
                profile.connection_status = LinkedInProfile.ConnectionStatus.VERIFYING
                profile.verification_requested_at = timezone.now()
                profile.last_connection_attempt_at = timezone.now()
                profile.checkpoint_url = ""
                profile.last_error_code = ""
                profile.last_error_message = ""
                profile.save(update_fields=["cookie_data", "connection_status", "verification_requested_at", "last_connection_attempt_at", "checkpoint_url", "last_error_code", "last_error_message"])
                request_verification(profile.pk)
                messages.success(request, "Verification started. LinkedFlow is opening a browser to sign in — this can take a minute, longer if LinkedIn asks for a verification code.")
        elif action == "disconnect":
            profile.cookie_data = None; profile.active = False; profile.connection_status = LinkedInProfile.ConnectionStatus.NOT_CONNECTED
            profile.save(update_fields=["cookie_data", "active", "connection_status"])
            messages.success(request, "LinkedIn account disconnected.")
        else:
            messages.error(request, "Unknown action.")
    return redirect("dashboard:linkedin_account")


@login_required
def campaigns_list(request):
    campaigns = (
        _user_campaigns(request.user).annotate(num_deals=Count("deals"))
        .prefetch_related("users")
        .order_by("-id")
    )
    return render(request, "dashboard/campaigns.html", {
        "active": "campaigns",
        "breadcrumbs": _crumbs({"label": "Campaigns"}),
        "page_title": "Campaigns",
        "page_description": "Create, edit, and manage your LinkedIn outreach campaigns.",
        "campaigns": campaigns,
    })


@login_required
def campaign_create(request):
    if request.method == "POST":
        form = CampaignForm(request.POST)
        if form.is_valid():
            campaign = form.save()
            campaign.users.add(request.user)
            messages.success(request, f"Campaign “{campaign.name}” created.")
            return redirect("dashboard:campaign_detail", pk=campaign.pk)
    else:
        form = CampaignForm()
    return render(request, "dashboard/campaign_form.html", {
        "active": "campaigns",
        "breadcrumbs": _crumbs(
            {"label": "Campaigns", "url": reverse("dashboard:campaigns")},
            {"label": "New campaign"},
        ),
        "page_title": "New campaign",
        "page_description": "Set the campaign name, product context, AI instructions, and booking link.",
        "form": form,
        "title": "New campaign",
    })


@login_required
def campaign_edit(request, pk):
    campaign = _owned_campaign_or_404(request, pk)
    if request.method == "POST":
        form = CampaignForm(request.POST, instance=campaign)
        if form.is_valid():
            form.save()
            messages.success(request, "Campaign updated.")
            return redirect("dashboard:campaign_detail", pk=campaign.pk)
    else:
        form = CampaignForm(instance=campaign)
    return render(request, "dashboard/campaign_form.html", {
        "active": "campaigns",
        "breadcrumbs": _crumbs(
            {"label": "Campaigns", "url": reverse("dashboard:campaigns")},
            {"label": campaign.name, "url": reverse("dashboard:campaign_detail", args=[campaign.pk])},
            {"label": "Edit"},
        ),
        "page_title": f"Edit {campaign.name}",
        "page_description": "Update the product context, AI instructions, and booking link.",
        "form": form,
        "title": f"Edit {campaign.name}",
    })


@login_required
def campaign_delete(request, pk):
    campaign = _owned_campaign_or_404(request, pk)
    if request.method == "POST":
        name = campaign.name
        Task.objects.filter(payload__campaign_id=campaign.pk).delete()
        campaign.delete()  # cascades to its Deals
        messages.success(request, f"Campaign “{name}” deleted.")
        return redirect("dashboard:campaigns")
    return redirect("dashboard:campaign_detail", pk=pk)


@login_required
def campaign_rename(request, pk):
    campaign = _owned_campaign_or_404(request, pk)
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        if not name:
            messages.error(request, "Campaign name cannot be empty.")
        elif Campaign.objects.exclude(pk=campaign.pk).filter(name=name).exists():
            messages.error(request, "Another campaign already uses that name.")
        else:
            campaign.name = name
            campaign.save(update_fields=["name"])
            messages.success(request, "Campaign name updated.")
    return redirect("dashboard:campaign_detail", pk=pk)


def _campaign_has_actionable_leads(campaign) -> bool:
    return Deal.objects.filter(
        campaign=campaign,
        state__in=[
            DealState.QUALIFIED,
            DealState.READY_TO_EMAIL,
            DealState.READY_TO_CONNECT,
            DealState.PENDING,
            DealState.CONNECTED,
        ],
    ).exists()


def _campaign_needs_ai_now(campaign) -> bool:
    qs = Deal.objects.filter(
        campaign=campaign,
        state=DealState.CONNECTED,
        reply_mode=Deal.ReplyMode.AUTO,
        outcome="",
    )
    if campaign.outreach_mode == Campaign.OutreachMode.CSV_PERSONALIZED:
        qs = qs.filter(custom_message_status=Deal.CustomMessageStatus.SENT)
    return qs.exists()


def _validate_campaign_start(request, campaign) -> bool:
    profile = getattr(request.user, "linkedin_profile", None)
    if not profile or not profile.active or profile.connection_status != LinkedInProfile.ConnectionStatus.CONNECTED:
        messages.error(request, "Connect and activate your LinkedIn account before starting this campaign.")
        return False
    if not _campaign_has_actionable_leads(campaign):
        messages.error(request, "Add or approve at least one actionable lead before starting this campaign.")
        return False
    if campaign.outreach_mode == Campaign.OutreachMode.CSV_PERSONALIZED:
        missing_messages = Deal.objects.filter(
            campaign=campaign,
            state__in=[
                DealState.QUALIFIED,
                DealState.READY_TO_CONNECT,
                DealState.PENDING,
                DealState.CONNECTED,
            ],
            custom_first_message="",
        ).exists()
        if missing_messages:
            messages.error(request, "Every CSV-personalized lead needs a customized first message before the campaign can start.")
            return False
    if _campaign_needs_ai_now(campaign):
        config = SiteConfig.load()
        if not config.ai_model or not config.llm_api_key:
            messages.error(request, "Configure an AI provider and API key before starting follow-up automation.")
            return False
        if not campaign.product_docs.strip() or not campaign.campaign_objective.strip():
            messages.error(request, "Add product context and AI follow-up instructions before starting follow-up automation.")
            return False
    return True


@login_required
def campaign_status(request, pk):
    campaign = _owned_campaign_or_404(request, pk)
    if request.method != "POST":
        return redirect("dashboard:campaign_detail", pk=pk)

    status = request.POST.get("status")
    if status == Campaign.Status.ACTIVE:
        if not _validate_campaign_start(request, campaign):
            return redirect("dashboard:campaign_detail", pk=pk)
        campaign.status = Campaign.Status.ACTIVE
        campaign.users.add(request.user)
        campaign.save(update_fields=["status"])
        messages.success(request, f"Campaign “{campaign.name}” started.")
    elif status == Campaign.Status.PAUSED:
        campaign.status = Campaign.Status.PAUSED
        campaign.save(update_fields=["status"])
        from linkreach.core.scheduler import cleanup_inactive_pending_tasks

        cleanup_inactive_pending_tasks()
        messages.success(request, f"Campaign “{campaign.name}” paused. Queued work is preserved.")
    else:
        messages.error(request, "Unknown campaign status action.")
    return redirect("dashboard:campaign_detail", pk=pk)


COUNTRY_TO_CODE = {
    "united states": "us",
    "usa": "us",
    "us": "us",
    "united kingdom": "gb",
    "uk": "gb",
    "canada": "ca",
    "australia": "au",
    "pakistan": "pk",
    "india": "in",
}

IMPORT_CORE_FIELDS = [
    ("email", "Email"),
    ("linkedin", "LinkedIn"),
    ("first_name", "First Name"),
    ("last_name", "Last Name"),
    ("company", "Company"),
    ("industry", "Industry"),
    ("country", "Country"),
    ("website", "Company website"),
    ("job_title", "Job title"),
    ("custom_message", "Customized first message"),
]

IMPORT_ALIASES = {
    "email": ["email", "work_email", "api_email"],
    "linkedin": ["linkedin", "linkedin_url", "linkedinurl", "profile_url", "url"],
    "first_name": ["firstname", "first_name", "first"],
    "last_name": ["lastname", "last_name", "last"],
    "company": ["companyname", "company_name", "company", "organization"],
    "industry": ["industry", "sector"],
    "country": ["country", "country_code"],
    "website": ["companywebsite", "company_website", "website", "company_url"],
    "job_title": ["title", "job_title", "position"],
    "custom_message": ["custom_message", "personalized_message", "first_message", "message", "icebreaker"],
}


def _normalize_header(value):
    return "".join(ch for ch in str(value or "").strip().lower() if ch.isalnum())


def _auto_import_mapping(headers):
    by_normalized = {_normalize_header(header): header for header in headers}
    mapping = {}
    for field, aliases in IMPORT_ALIASES.items():
        mapping[field] = ""
        for alias in aliases:
            header = by_normalized.get(_normalize_header(alias))
            if header:
                mapping[field] = header
                break
    return mapping


def _parse_import_csv(uploaded_file):
    decoded = uploaded_file.read().decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(decoded))
    headers = reader.fieldnames or []
    rows = []
    for row in reader:
        rows.append({str(k or "").strip(): (v or "") for k, v in row.items()})
    return headers, rows


def _row_value(row, *names):
    normalized = {str(k).strip().lower(): (v or "").strip() for k, v in row.items()}
    for name in names:
        value = normalized.get(name.lower())
        if value:
            return value
    return ""


def _normalize_linkedin_url(value):
    value = (value or "").strip()
    if not value:
        return ""
    if value.startswith("linkedin.com/"):
        return f"https://www.{value}"
    if value.startswith("www.linkedin.com/"):
        return f"https://{value}"
    return value


def _country_code(value):
    value = (value or "").strip()
    if not value:
        return ""
    if len(value) == 2:
        return value.lower()
    return COUNTRY_TO_CODE.get(value.lower(), "")


def _clean_email(value):
    value = (value or "").strip()
    if not value:
        return ""
    try:
        validate_email(value)
    except ValidationError:
        return ""
    return value


def _mapped_value(row, mapping, field):
    column = (mapping.get(field) or "").strip()
    return (row.get(column) or "").strip() if column else ""


def _mapped_raw_value(row, mapping, field):
    """Return a mapped value without changing the CSV message body."""
    column = (mapping.get(field) or "").strip()
    return (row.get(column) or "") if column else ""


def _csv_context(row, mapping, custom_fields):
    first = _mapped_value(row, mapping, "first_name")
    last = _mapped_value(row, mapping, "last_name")
    full_name = " ".join(part for part in [first, last] if part).strip()
    title = _row_value(row, "title", "job_title", "position")
    company = _mapped_value(row, mapping, "company")
    industry = _mapped_value(row, mapping, "industry")
    sub_industry = _row_value(row, "subIndustry", "sub_industry")
    headcount = _row_value(row, "companyHeadCount", "company_head_count")
    revenue = _row_value(row, "companyRevenue", "company_revenue")
    city = _row_value(row, "city")
    state = _row_value(row, "state")
    country = _mapped_value(row, mapping, "country")
    website = _row_value(row, "companyWebsite", "company_website", "website")
    status = _row_value(row, "status")
    verification = _row_value(row, "verificationStatus", "verification_status")

    lead_line = ", ".join(part for part in [full_name, title, company and f"at {company}"] if part)
    details = []
    if industry or sub_industry:
        details.append("Industry: " + " / ".join(part for part in [industry, sub_industry] if part))
    if headcount:
        details.append(f"Company size: {headcount}")
    if revenue:
        details.append(f"Revenue: {revenue}")
    location = ", ".join(part for part in [city, state, country] if part)
    if location:
        details.append(f"Location: {location}")
    if website:
        details.append(f"Company website: {website}")
    if status or verification:
        details.append("Email source: " + ", ".join(part for part in [status, verification] if part))

    for field_name, column in custom_fields:
        value = (row.get(column) or "").strip()
        if value:
            details.append(f"{field_name}: {value}")

    prefix = f"Imported CSV lead: {lead_line}." if lead_line else "Imported CSV lead."
    return f"{prefix} " + ". ".join(details) + "." if details else prefix


def _import_profile_summary(existing, import_fields, custom_import_fields):
    existing = existing if isinstance(existing, dict) else {}
    facts = services.summary_facts(existing)
    if not facts:
        name = " ".join(part for part in [import_fields.get("first_name"), import_fields.get("last_name")] if part).strip()
        line = ", ".join(part for part in [name, import_fields.get("company"), import_fields.get("industry")] if part)
        if line:
            facts = [f"Imported lead context: {line}"]
    merged = dict(existing)
    merged["facts"] = facts
    merged["import_fields"] = {k: v for k, v in import_fields.items() if v}
    merged["custom_import_fields"] = {k: v for k, v in custom_import_fields.items() if v}
    return merged


def _import_campaign_rows(campaign, rows, mapping, custom_fields):
    summary = {
        "total": len(rows),
        "created": 0,
        "existing": 0,
        "duplicates": 0,
        "invalid": 0,
        "emails": 0,
        "missing_messages": 0,
        "oversized_messages": 0,
    }
    seen_public_ids = set()
    imported_public_ids = set()

    for row in rows:
        linkedin_url = _normalize_linkedin_url(_mapped_value(row, mapping, "linkedin"))
        public_id = url_to_public_id(linkedin_url)
        if not public_id:
            summary["invalid"] += 1
            continue
        if public_id in seen_public_ids:
            summary["duplicates"] += 1
            continue
        seen_public_ids.add(public_id)

        custom_message = _mapped_raw_value(row, mapping, "custom_message")
        if campaign.outreach_mode == Campaign.OutreachMode.CSV_PERSONALIZED:
            if not custom_message.strip():
                summary["missing_messages"] += 1
                continue
            if len(custom_message) > 3000:
                summary["oversized_messages"] += 1
                continue

        email = _clean_email(_mapped_value(row, mapping, "email"))
        country = _country_code(_mapped_value(row, mapping, "country"))
        lead, _lead_created = Lead.objects.get_or_create(
            public_identifier=public_id,
            defaults={"linkedin_url": public_id_to_url(public_id)},
        )
        update_fields = []
        if not lead.linkedin_url:
            lead.linkedin_url = public_id_to_url(public_id)
            update_fields.append("linkedin_url")
        if country and not lead.country_code:
            lead.country_code = country
            update_fields.append("country_code")
        if email and not lead.api_email:
            lead.api_email = email
            update_fields.append("api_email")
            summary["emails"] += 1
        if update_fields:
            lead.save(update_fields=update_fields)

        deal, created = Deal.objects.get_or_create(
            lead=lead,
            campaign=campaign,
            defaults={"state": DealState.QUALIFIED},
        )
        import_fields = {
            "email": email,
            "linkedin": public_id_to_url(public_id),
            "first_name": _mapped_value(row, mapping, "first_name"),
            "last_name": _mapped_value(row, mapping, "last_name"),
            "company": _mapped_value(row, mapping, "company"),
            "industry": _mapped_value(row, mapping, "industry"),
            "country": country,
            "website": _mapped_value(row, mapping, "website"),
            "job_title": _mapped_value(row, mapping, "job_title"),
        }
        custom_import_fields = {
            field_name: (row.get(column) or "").strip()
            for field_name, column in custom_fields
            if field_name and column
        }
        deal.profile_summary = _import_profile_summary(
            deal.profile_summary,
            import_fields,
            custom_import_fields,
        )
        update_fields = ["profile_summary"]
        if campaign.outreach_mode == Campaign.OutreachMode.CSV_PERSONALIZED:
            if not deal.outreach_approved_at and deal.custom_message_status != Deal.CustomMessageStatus.SENT:
                deal.custom_first_message = custom_message
                deal.custom_message_status = Deal.CustomMessageStatus.PENDING
                deal.custom_message_error = ""
                update_fields.extend(["custom_first_message", "custom_message_status", "custom_message_error"])
        deal.save(update_fields=update_fields)
        imported_public_ids.add(public_id)

        context = _csv_context(row, mapping, custom_fields)
        if context and not deal.reason:
            deal.reason = context
            deal.save(update_fields=["reason"])

        if created:
            summary["created"] += 1
        else:
            summary["existing"] += 1

    campaign.seed_public_ids = list(set(campaign.seed_public_ids or []) | imported_public_ids)
    campaign.save(update_fields=["seed_public_ids"])
    return summary


@login_required
def campaign_import_csv(request, pk):
    campaign = _owned_campaign_or_404(request, pk)
    if request.method != "POST":
        return redirect("dashboard:campaign_detail", pk=pk)

    step = request.POST.get("step", "preview")
    session_key = f"campaign_import_{campaign.pk}"

    if step == "preview":
        uploaded_file = request.FILES.get("csv_file")
        if not uploaded_file:
            messages.error(request, "Choose a CSV file to import.")
            return redirect("dashboard:campaign_detail", pk=pk)
        try:
            headers, rows = _parse_import_csv(uploaded_file)
        except csv.Error:
            messages.error(request, "The CSV could not be read. Please check the file format.")
            return redirect("dashboard:campaign_detail", pk=pk)
        request.session[session_key] = {"headers": headers, "rows": rows}
        request.session.modified = True
        mapping = _auto_import_mapping(headers)
        return render(request, "dashboard/campaign_import_map.html", {
            "active": "campaigns",
            "breadcrumbs": _crumbs(
                {"label": "Campaigns", "url": reverse("dashboard:campaigns")},
                {"label": campaign.name, "url": reverse("dashboard:campaign_detail", args=[campaign.pk])},
                {"label": "Add profiles"},
            ),
            "page_title": "Add profiles",
            "page_description": "Map CSV columns into profile fields, review a sample, then add them to this campaign.",
            "campaign": campaign,
            "headers": headers,
            "rows": rows,
            "preview_rows": rows[:5],
            "mapping": mapping,
            "core_fields": IMPORT_CORE_FIELDS,
            "requires_custom_message": campaign.outreach_mode == Campaign.OutreachMode.CSV_PERSONALIZED,
        })

    data = request.session.get(session_key)
    if not data:
        messages.error(request, "Upload a CSV before importing leads.")
        return redirect("dashboard:campaign_detail", pk=pk)

    mapping = {field: request.POST.get(f"map_{field}", "") for field, _label in IMPORT_CORE_FIELDS}
    if campaign.outreach_mode == Campaign.OutreachMode.CSV_PERSONALIZED and not mapping.get("custom_message"):
        messages.error(request, "Map a CSV column to Customized first message before importing.")
        return redirect("dashboard:campaign_detail", pk=pk)
    custom_names = request.POST.getlist("custom_name")
    custom_columns = request.POST.getlist("custom_column")
    custom_fields = [
        (name.strip(), column.strip())
        for name, column in zip(custom_names, custom_columns)
        if name.strip() and column.strip()
    ]
    summary = _import_campaign_rows(campaign, data.get("rows", []), mapping, custom_fields)
    request.session.pop(session_key, None)
    request.session.modified = True

    skipped_messages = summary["missing_messages"] + summary["oversized_messages"]
    if summary["created"] or summary["existing"]:
        messages.success(
            request,
            f"Imported {summary['created']} new lead(s). "
            f"{summary['existing']} already existed, {summary['duplicates']} duplicate row(s), "
            f"{summary['invalid']} invalid LinkedIn URL(s), {summary['emails']} email(s) added"
            + (f", {skipped_messages} row(s) skipped for missing or oversized messages." if skipped_messages else "."),
        )
    else:
        messages.error(
            request,
            f"No new leads imported. {summary['existing']} already existed, "
            f"{summary['duplicates']} duplicate row(s), {summary['invalid']} invalid LinkedIn URL(s), "
            f"{skipped_messages} missing or oversized message(s).",
        )
    return redirect("dashboard:campaign_detail", pk=pk)


@login_required
def campaign_start_csv_outreach(request, pk):
    campaign = _owned_campaign_or_404(request, pk)
    if request.method != "POST":
        return redirect("dashboard:campaign_detail", pk=pk)
    if campaign.outreach_mode != Campaign.OutreachMode.CSV_PERSONALIZED:
        messages.error(request, "This action is only available for CSV personalized campaigns.")
        return redirect("dashboard:campaign_detail", pk=pk)
    profile = getattr(request.user, "linkedin_profile", None)
    if not profile or not profile.active or profile.connection_status != LinkedInProfile.ConnectionStatus.CONNECTED:
        messages.error(request, "Connect and activate your LinkedIn account before starting outreach.")
        return redirect("dashboard:campaign_detail", pk=pk)
    config = SiteConfig.load()
    if not config.ai_model or not config.llm_api_key:
        messages.error(request, "Configure an AI provider and API key before starting outreach.")
        return redirect("dashboard:campaign_detail", pk=pk)
    if not campaign.product_docs.strip() or not campaign.campaign_objective.strip():
        messages.error(request, "Add product context and AI follow-up instructions before starting outreach.")
        return redirect("dashboard:campaign_detail", pk=pk)

    now = timezone.now()
    eligible = Deal.objects.filter(
        campaign=campaign,
        state=DealState.QUALIFIED,
        outreach_approved_at__isnull=True,
        custom_message_status=Deal.CustomMessageStatus.PENDING,
    ).exclude(custom_first_message="").exclude(messages__isnull=False).distinct()
    count = eligible.update(
        state=DealState.READY_TO_CONNECT,
        outreach_approved_at=now,
        update_date=now,
    )
    if count:
        campaign.users.add(request.user)
        messages.success(request, f"Approved {count} personalized lead(s) for outreach. Start the campaign when you are ready for the bot to process them.")
    else:
        messages.error(request, "No reviewed personalized leads are ready to start.")
    return redirect("dashboard:campaign_detail", pk=pk)


@login_required
def campaign_custom_message(request, pk, deal_id):
    campaign = get_object_or_404(
        _user_campaigns(request.user),
        pk=pk,
        outreach_mode=Campaign.OutreachMode.CSV_PERSONALIZED,
    )
    deal = get_object_or_404(Deal, pk=deal_id, campaign=campaign)
    if request.method != "POST":
        return redirect("dashboard:campaign_detail", pk=pk)
    body = (request.POST.get("custom_first_message") or "").strip()
    if not body or len(body) > 3000:
        messages.error(request, "The customized message must be between 1 and 3,000 characters.")
    elif deal.custom_message_status == Deal.CustomMessageStatus.SENT:
        messages.error(request, "A delivered campaign message cannot be edited.")
    else:
        deal.custom_first_message = body
        deal.custom_message_status = Deal.CustomMessageStatus.PENDING
        deal.custom_message_error = ""
        deal.save(update_fields=["custom_first_message", "custom_message_status", "custom_message_error"])
        if deal.state == DealState.CONNECTED and deal.outreach_approved_at:
            from linkreach.core.scheduler import enqueue_custom_first_message

            enqueue_custom_first_message(deal)
        messages.success(request, "Customized message updated.")
    return redirect("dashboard:campaign_detail", pk=pk)


@login_required
def campaign_detail(request, pk):
    campaign = _owned_campaign_or_404(request, pk)
    if request.method == "POST":
        if campaign.outreach_mode == Campaign.OutreachMode.CSV_PERSONALIZED:
            messages.error(request, "Upload a CSV with a customized message column for this campaign.")
            return redirect("dashboard:campaign_detail", pk=pk)
        ids = parse_seed_urls(request.POST.get("urls", ""))
        if not ids:
            messages.error(request, "No valid LinkedIn URLs found.")
        else:
            created = create_seed_leads(campaign, ids)
            messages.success(
                request,
                f"{created} new profile(s) added as Qualified. Select them below and "
                "click “Queue selected” to send connection requests.",
            )
        return redirect("dashboard:campaign_detail", pk=pk)

    q = request.GET.get("q", "").strip()
    state = request.GET.get("state", "").strip()
    country = request.GET.get("country", "").strip().lower()
    try:
        per_page = int(request.GET.get("per_page", 50))
    except (TypeError, ValueError):
        per_page = 50
    if per_page not in (20, 50, 100):
        per_page = 50

    deals_qs = (
        Deal.objects.filter(campaign=campaign)
        .select_related("lead")
        .order_by("-update_date")
    )
    countries = list(
        deals_qs.exclude(lead__country_code="")
        .values_list("lead__country_code", flat=True)
        .distinct()
        .order_by("lead__country_code")
    )
    if q:
        deals_qs = deals_qs.filter(lead__public_identifier__icontains=q)
    if state:
        deals_qs = deals_qs.filter(state=state)
    if country:
        deals_qs = deals_qs.filter(lead__country_code=country)

    paginator = Paginator(deals_qs, per_page)
    page = paginator.get_page(request.GET.get("page"))
    for d in page.object_list:
        d.summary_preview = services.deal_summary_preview(d)
        d.display_name = services.deal_display_name(d)
        d.import_fields = services.deal_import_fields(d)
        d.state_badge = services.deal_state_badge(d)

    csv_context = {}
    if campaign.outreach_mode == Campaign.OutreachMode.CSV_PERSONALIZED:
        all_campaign_deals = Deal.objects.filter(campaign=campaign)
        profile = getattr(request.user, "linkedin_profile", None)
        config = SiteConfig.load()
        csv_context = {
            "csv_ready_count": all_campaign_deals.filter(
                state=DealState.QUALIFIED,
                outreach_approved_at__isnull=True,
                custom_message_status=Deal.CustomMessageStatus.PENDING,
            ).exclude(custom_first_message="").exclude(messages__isnull=False).distinct().count(),
            "csv_message_counts": {
                item["custom_message_status"]: item["total"]
                for item in all_campaign_deals.values("custom_message_status").annotate(total=Count("id"))
            },
            "csv_account_ready": bool(
                profile
                and profile.active
                and profile.connection_status == LinkedInProfile.ConnectionStatus.CONNECTED
            ),
            "csv_ai_ready": bool(config.ai_model and config.llm_api_key),
            "csv_context_ready": bool(campaign.product_docs.strip() and campaign.campaign_objective.strip()),
        }

    params = request.GET.copy()
    params.pop("page", None)
    querystring = params.urlencode()

    context = {
        "active": "campaigns",
        "breadcrumbs": _crumbs(
            {"label": "Campaigns", "url": reverse("dashboard:campaigns")},
            {"label": campaign.name},
        ),
        "page_title": "",
        "page_description": "",
        "campaign": campaign,
        "campaign_status_badge": services.campaign_status_badge(campaign),
        "action_summary": services.campaign_action_summary(campaign),
        "pipeline": services.pipeline_counts(campaign),
        "page": page,
        "deals": page.object_list,
        "deal_count": paginator.count,
        "q": q,
        "state": state,
        "country": country,
        "countries": countries,
        "per_page": per_page,
        "states": DealState.choices,
        "querystring": querystring,
    }
    context.update(csv_context)
    return render(request, "dashboard/campaign_detail.html", context)


@login_required
def queue_selected(request, pk):
    """Promote the selected Qualified leads to Ready-to-Connect (one click)."""
    campaign = _owned_campaign_or_404(request, pk)
    if request.method == "POST":
        ids = request.POST.getlist("deal_ids")
        n = 0
        if ids:
            n = Deal.objects.filter(
                campaign=campaign, pk__in=ids, state=DealState.QUALIFIED
            ).update(state=DealState.READY_TO_CONNECT, update_date=timezone.now())
        if n:
            messages.success(
                request,
                f"{n} profile(s) queued for connection. The bot sends the requests on "
                "its next runs (up to your daily limit).",
            )
        else:
            messages.error(
                request,
                "Nothing queued — only Qualified leads can be queued. Select some first.",
            )
    return redirect("dashboard:campaign_detail", pk=pk)


def _deals_csv_response(deals, filename):
    resp = HttpResponse(content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    resp.write("﻿")  # BOM so Excel reads UTF-8 correctly
    w = csv.writer(resp)
    w.writerow([
        "Campaign", "Handle", "Name", "LinkedIn URL", "State", "Outcome", "Reason",
        "Country", "Email found", "Connect attempts", "Profile summary",
        "Conversation summary", "Customized first message", "Message status",
        "Message sent at", "Created", "Updated",
    ])
    rows = deals.iterator() if hasattr(deals, "iterator") else deals
    for d in rows:
        lead = d.lead
        w.writerow([
            d.campaign.name if d.campaign_id else "",
            lead.public_identifier,
            services.pretty_name(lead.public_identifier),
            lead.linkedin_url,
            d.get_state_display(),
            d.get_outcome_display() if d.outcome else "",
            (d.reason or "").replace("\n", " ").strip()[:500],
            lead.country_code,
            services.lead_email(lead),
            d.connect_attempts,
            " | ".join(services.summary_facts(d.profile_summary)),
            " | ".join(services.summary_facts(d.chat_summary)),
            d.custom_first_message,
            d.get_custom_message_status_display(),
            d.custom_message_sent_at.strftime("%Y-%m-%d %H:%M") if d.custom_message_sent_at else "",
            d.creation_date.strftime("%Y-%m-%d %H:%M"),
            d.update_date.strftime("%Y-%m-%d %H:%M"),
        ])
    return resp


@login_required
def campaign_export(request, pk):
    campaign = _owned_campaign_or_404(request, pk)
    deals = (
        Deal.objects.filter(campaign=campaign)
        .select_related("lead", "campaign")
        .order_by("-update_date")
    )
    return _deals_csv_response(deals, f"leads_campaign_{campaign.pk}.csv")


@login_required
def leads_export(request):
    deals, _filters = _filtered_leads(request)
    return _deals_csv_response(deals, "leads_export.csv")


@login_required
def deal_modal(request, pk):
    """Lead details: HTMX drawer partial, or a full page when opened directly."""
    deal = _owned_deal_or_404(request, pk)
    context = {
        "deal": deal,
        "name": services.deal_display_name(deal),
        "email": services.lead_email(deal.lead),
        "email_status": services.email_status(deal.lead),
        "keywords": services.deal_keywords(deal),
        "state_tone": services.state_tone(deal.state),
        "import_fields": services.deal_import_fields(deal),
        "custom_import_fields": (
            deal.profile_summary.get("custom_import_fields", {})
            if isinstance(deal.profile_summary, dict)
            else {}
        ),
        "profile_facts": services.summary_facts(deal.profile_summary),
        "chat_facts": services.summary_facts(deal.chat_summary),
        "messages_list": list(deal.messages.order_by("creation_date")[:30]),
        "is_drawer": bool(request.headers.get("HX-Request")),
    }
    if request.headers.get("HX-Request"):
        return render(request, "dashboard/_deal_modal.html", context)
    context.update({
        "active": "leads",
        "breadcrumbs": _crumbs(
            {"label": "Leads", "url": reverse("dashboard:leads")},
            {"label": context["name"] or deal.lead.public_identifier},
        ),
        "page_title": context["name"] or deal.lead.public_identifier,
        "page_description": f"{deal.campaign.name} · {deal.get_state_display()}",
    })
    return render(request, "dashboard/deal_detail.html", context)


def _filtered_leads(request):
    q = request.GET.get("q", "").strip()
    state = request.GET.get("state", "").strip()
    campaign = request.GET.get("campaign", "").strip()
    country = request.GET.get("country", "").strip().lower()
    has_email = request.GET.get("has_email", "").strip()

    qs = (
        _user_deals(request.user)
        .select_related("lead", "campaign")
        .distinct()
        .order_by("-update_date")
    )
    if q:
        qs = qs.filter(
            Q(lead__public_identifier__icontains=q)
            | Q(reason__icontains=q)
            | Q(campaign__name__icontains=q)
        )
    if state:
        qs = qs.filter(state=state)
    if campaign:
        qs = qs.filter(campaign_id=campaign)
    if country:
        qs = qs.filter(lead__country_code=country)

    deals = qs
    if has_email in {"yes", "no"}:
        materialized = list(qs)
        if has_email == "yes":
            deals = [d for d in materialized if services.lead_email(d.lead)]
        else:
            deals = [d for d in materialized if not services.lead_email(d.lead)]

    return deals, {
        "q": q,
        "state": state,
        "campaign": campaign,
        "country": country,
        "has_email": has_email,
    }


@login_required
def leads(request):
    deals, filters = _filtered_leads(request)

    paginator = Paginator(deals, 50)
    page = paginator.get_page(request.GET.get("page"))
    for d in page.object_list:
        d.summary_preview = services.deal_summary_preview(d)
        d.display_name = services.deal_display_name(d)
        d.keywords = services.deal_keywords(d)
        d.email_status = services.email_status(d.lead)
        d.state_tone = services.state_tone(d.state)

    # Preserve filters across pagination links.
    params = request.GET.copy()
    params.pop("page", None)
    querystring = params.urlencode()

    return render(request, "dashboard/leads.html", {
        "active": "leads",
        "breadcrumbs": _crumbs({"label": "Leads"}),
        "page_title": "Leads & Deals",
        "page_description": f"{paginator.count} profiles across all campaigns.",
        "page": page,
        "total": paginator.count,
        **filters,
        "campaigns": _user_campaigns(request.user).order_by("name"),
        "countries": (
            _user_deals(request.user).exclude(lead__country_code="")
            .values_list("lead__country_code", flat=True)
            .distinct()
            .order_by("lead__country_code")
        ),
        "states": DealState.choices,
        "querystring": querystring,
    })


@login_required
def conversations(request):
    """All deals with at least one message — the 'In conversation' list."""
    convos = services.conversations(request.user)
    awaiting = sum(1 for d in convos if d.last_incoming)
    return render(request, "dashboard/conversations.html", {
        "active": "conversations",
        "breadcrumbs": _crumbs({"label": "Conversations"}),
        "page_title": "Conversations",
        "page_description": f"{len(convos)} conversations, {awaiting} awaiting your reply.",
        "convos": convos,
        "total": len(convos),
        "awaiting": awaiting,
    })


@login_required
def conversation_detail(request, deal_id):
    deal = _owned_deal_or_404(request, deal_id)
    context = services.conversation_detail_context(deal)
    draft_key = f"conversation_draft_{deal.pk}"
    context["draft"] = request.session.pop(draft_key, "")
    context.update({
        "active": "conversations",
        "breadcrumbs": _crumbs(
            {"label": "Conversations", "url": reverse("dashboard:conversations")},
            {"label": context["name"] or deal.lead.public_identifier},
        ),
        "page_title": context["name"] or deal.lead.public_identifier,
        "page_description": f"{deal.campaign.name} · {deal.get_state_display()}",
        "bot_status": services.bot_status(),
    })
    return render(request, "dashboard/conversation_detail.html", context)


@login_required
def conversation_reply_mode(request, deal_id):
    deal = _owned_deal_or_404(request, deal_id)
    if request.method == "POST":
        mode = request.POST.get("reply_mode", "")
        if mode in {Deal.ReplyMode.AUTO, Deal.ReplyMode.MANUAL}:
            if deal.reply_mode == mode:
                messages.info(request, "Reply mode is already set.")
            else:
                deal.reply_mode = mode
                deal.save(update_fields=["reply_mode", "update_date"])
                event_type = (
                    ConversationEvent.EventType.MANUAL_MODE_STARTED
                    if mode == Deal.ReplyMode.MANUAL
                    else ConversationEvent.EventType.AI_AUTO_RESUMED
                )
                ConversationEvent.objects.create(
                    deal=deal,
                    event_type=event_type,
                    created_by=request.user,
                )
                if mode == Deal.ReplyMode.MANUAL:
                    messages.success(request, "Manual mode enabled. AI follow-ups are paused for this conversation.")
                else:
                    messages.success(request, "AI Auto enabled. This conversation is eligible for AI follow-up again.")
        else:
            messages.error(request, "Choose a valid reply mode.")
    return redirect("dashboard:conversation_detail", deal_id=deal.pk)


def _queue_manual_message(deal, body, request):
    payload = {
        "deal_id": deal.pk,
        "campaign_id": deal.campaign_id,
        "message": body,
        "queued_by_user_id": request.user.pk,
        "manual_status": "queued",
    }
    return Task.objects.create(
        task_type=Task.TaskType.MANUAL_MESSAGE,
        status=Task.Status.PENDING,
        scheduled_at=timezone.now(),
        payload=payload,
    )


@login_required
def conversation_send_manual(request, deal_id):
    deal = _owned_deal_or_404(request, deal_id)
    draft_key = f"conversation_draft_{deal.pk}"
    if request.method != "POST":
        return redirect("dashboard:conversation_detail", deal_id=deal.pk)

    body = (request.POST.get("message") or "").strip()
    request.session[draft_key] = body
    request.session.modified = True

    profile = getattr(request.user, "linkedin_profile", None)
    if not body:
        messages.error(request, "Write a message before sending.")
        return redirect("dashboard:conversation_detail", deal_id=deal.pk)
    if deal.reply_mode != Deal.ReplyMode.MANUAL:
        messages.error(request, "Switch this conversation to Manual before sending a human reply.")
        return redirect("dashboard:conversation_detail", deal_id=deal.pk)
    if not deal.lead.public_identifier and not deal.lead.linkedin_url:
        messages.error(request, "This lead is missing a usable LinkedIn profile.")
        return redirect("dashboard:conversation_detail", deal_id=deal.pk)
    if profile is None:
        messages.error(request, "Connect your LinkedIn account before sending manual replies.")
        return redirect("dashboard:conversation_detail", deal_id=deal.pk)
    if not profile.active:
        messages.error(request, "Your LinkedIn account is paused. Resume it before sending manual replies.")
        return redirect("dashboard:conversation_detail", deal_id=deal.pk)
    if profile.connection_status != LinkedInProfile.ConnectionStatus.CONNECTED:
        messages.error(request, "Your LinkedIn account is not connected. Reconnect it before sending manual replies.")
        return redirect("dashboard:conversation_detail", deal_id=deal.pk)
    if services.has_duplicate_manual_task(deal, body):
        messages.error(request, "This manual reply is already queued or sending.")
        return redirect("dashboard:conversation_detail", deal_id=deal.pk)

    _queue_manual_message(deal, body, request)
    request.session.pop(draft_key, None)
    request.session.modified = True

    status = services.bot_status()
    if status["state"] in {"running", "starting"}:
        messages.success(request, "Manual reply queued. The bot will send it through the active LinkedIn session.")
    else:
        messages.warning(request, "Manual reply queued. Start the bot from Monitor so it can send the message.")
    return redirect("dashboard:conversation_detail", deal_id=deal.pk)


@login_required
def monitor(request):
    return render(request, "dashboard/monitor.html", {
        "active": "monitor",
        "breadcrumbs": _crumbs({"label": "Monitor"}),
        "page_title": "Monitor",
        "page_description": "Live bot status, next scheduled work, and recent activity.",
        "status": services.bot_status(),
        "next_up": services.next_up(),
        "feed": services.activity_feed(user=request.user),
        "log_exists": services.log_exists(),
    })


@login_required
def monitor_status(request):
    """HTMX fragment: status banner + next-up (polled)."""
    return render(request, "dashboard/_status.html", {
        "status": services.bot_status(),
        "next_up": services.next_up(),
    })


@login_required
def bot_action(request, action):
    from linkreach.core.bot_process import force_kill, request_stop, start

    if request.method == "POST":
        if action == "start":
            ok, msg = start(request.user)
        elif action == "stop":
            ok, msg = request_stop(request.user)
        elif action == "force-stop":
            ok, msg = force_kill(request.user)
        else:
            ok, msg = False, "Unknown bot action."
        (messages.success if ok else messages.error)(request, msg)
    return redirect("dashboard:monitor")


@login_required
def monitor_feed(request):
    """HTMX fragment: activity feed (polled)."""
    return render(request, "dashboard/_feed.html", {
        "feed": services.activity_feed(user=request.user),
    })


@login_required
def monitor_log(request):
    """HTMX fragment: raw log tail (polled)."""
    return render(request, "dashboard/_log.html", {
        "log_lines": services.read_log_tail(300),
        "log_exists": services.log_exists(),
    })
