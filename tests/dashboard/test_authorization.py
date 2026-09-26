import pytest
from django.urls import reverse

from linkreach.chat.models import ChatMessage
from linkreach.core.models import Campaign, Task
from linkreach.crm.models import Deal, Lead
from tests.factories import DealFactory, UserFactory


@pytest.fixture
def operators(db):
    owner = UserFactory(username="owner")
    stranger = UserFactory(username="stranger")
    return owner, stranger


@pytest.fixture
def owned_deal(operators):
    owner, _stranger = operators
    campaign = Campaign.objects.create(name="Private campaign")
    campaign.users.add(owner)
    deal = DealFactory(campaign=campaign)
    return campaign, deal


@pytest.mark.parametrize(
    "route_name",
    [
        "dashboard:campaign_detail",
        "dashboard:campaign_edit",
        "dashboard:campaign_export",
    ],
)
def test_foreign_campaign_get_is_not_visible(client, operators, owned_deal, route_name):
    _owner, stranger = operators
    campaign, _deal = owned_deal
    client.force_login(stranger)

    response = client.get(reverse(route_name, args=[campaign.pk]))

    assert response.status_code == 404


@pytest.mark.parametrize(
    "route_name",
    [
        "dashboard:campaign_rename",
        "dashboard:campaign_status",
        "dashboard:campaign_delete",
        "dashboard:campaign_start_csv_outreach",
        "dashboard:queue_selected",
    ],
)
def test_foreign_campaign_post_cannot_mutate(client, operators, owned_deal, route_name):
    _owner, stranger = operators
    campaign, _deal = owned_deal
    client.force_login(stranger)

    response = client.post(reverse(route_name, args=[campaign.pk]), data={"name": "Changed"})

    assert response.status_code == 404
    campaign.refresh_from_db()
    assert campaign.name == "Private campaign"


@pytest.mark.parametrize(
    "route_name",
    [
        "dashboard:deal_modal",
        "dashboard:conversation_detail",
        "dashboard:conversation_reply_mode",
        "dashboard:conversation_send_manual",
    ],
)
def test_foreign_deal_is_not_visible_or_mutable(client, operators, owned_deal, route_name):
    _owner, stranger = operators
    _campaign, deal = owned_deal
    client.force_login(stranger)

    method = client.get if route_name in {
        "dashboard:deal_modal",
        "dashboard:conversation_detail",
    } else client.post
    response = method(reverse(route_name, args=[deal.pk]))

    assert response.status_code == 404


def test_lists_and_exports_only_include_owned_campaigns(client, operators, owned_deal):
    owner, stranger = operators
    owner_campaign, owner_deal = owned_deal
    foreign_campaign = Campaign.objects.create(name="Stranger campaign")
    foreign_campaign.users.add(stranger)
    foreign_deal = DealFactory(campaign=foreign_campaign)
    client.force_login(owner)

    campaigns = client.get(reverse("dashboard:campaigns"))
    leads = client.get(reverse("dashboard:leads"))
    conversations = client.get(reverse("dashboard:conversations"))
    export = client.get(reverse("dashboard:leads_export"))

    assert owner_campaign.name.encode() in campaigns.content
    assert foreign_campaign.name.encode() not in campaigns.content
    assert owner_deal.lead.public_identifier.encode() in leads.content
    assert foreign_deal.lead.public_identifier.encode() not in leads.content
    assert foreign_campaign.name.encode() not in conversations.content
    assert owner_deal.lead.public_identifier.encode() in export.content
    assert foreign_deal.lead.public_identifier.encode() not in export.content


def test_campaign_delete_removes_tasks_and_deals_but_retains_lead(client, operators, owned_deal):
    owner, _stranger = operators
    campaign, deal = owned_deal
    lead_id = deal.lead_id
    task = Task.objects.create(
        task_type=Task.TaskType.CONNECT,
        scheduled_at=deal.creation_date,
        payload={"campaign_id": campaign.pk},
    )
    client.force_login(owner)

    response = client.post(reverse("dashboard:campaign_delete", args=[campaign.pk]))

    assert response.status_code == 302
    assert not Campaign.objects.filter(pk=campaign.pk).exists()
    assert not Deal.objects.filter(pk=deal.pk).exists()
    assert not Task.objects.filter(pk=task.pk).exists()
    assert Lead.objects.filter(pk=lead_id).exists()


def test_conversation_list_hides_foreign_messages(client, operators, owned_deal):
    owner, stranger = operators
    owner_campaign, owner_deal = owned_deal
    ChatMessage.objects.create(
        deal=owner_deal,
        linkedin_urn="urn:owner",
        content="Owner-only message",
        is_outgoing=False,
    )
    foreign_campaign = Campaign.objects.create(name="Foreign chat")
    foreign_campaign.users.add(stranger)
    foreign_deal = DealFactory(campaign=foreign_campaign)
    ChatMessage.objects.create(
        deal=foreign_deal,
        linkedin_urn="urn:foreign",
        content="Foreign-only message",
        is_outgoing=False,
    )
    client.force_login(owner)

    response = client.get(reverse("dashboard:conversations"))

    assert b"Owner-only message" in response.content
    assert b"Foreign-only message" not in response.content
