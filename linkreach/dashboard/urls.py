from django.urls import path

from linkreach.dashboard import views

app_name = "dashboard"

urlpatterns = [
    path("", views.overview, name="overview"),
    path("campaigns/", views.campaigns_list, name="campaigns"),
    path("campaigns/new/", views.campaign_create, name="campaign_create"),
    path("campaigns/<int:pk>/", views.campaign_detail, name="campaign_detail"),
    path("campaigns/<int:pk>/edit/", views.campaign_edit, name="campaign_edit"),
    path("campaigns/<int:pk>/rename/", views.campaign_rename, name="campaign_rename"),
    path("campaigns/<int:pk>/status/", views.campaign_status, name="campaign_status"),
    path("campaigns/<int:pk>/import-csv/", views.campaign_import_csv, name="campaign_import_csv"),
    path("campaigns/<int:pk>/start-csv-outreach/", views.campaign_start_csv_outreach, name="campaign_start_csv_outreach"),
    path("campaigns/<int:pk>/messages/<int:deal_id>/", views.campaign_custom_message, name="campaign_custom_message"),
    path("campaigns/<int:pk>/delete/", views.campaign_delete, name="campaign_delete"),
    path("campaigns/<int:pk>/queue-selected/", views.queue_selected, name="queue_selected"),
    path("campaigns/<int:pk>/export/", views.campaign_export, name="campaign_export"),
    path("leads/", views.leads, name="leads"),
    path("leads/export/", views.leads_export, name="leads_export"),
    path("deals/<int:pk>/", views.deal_modal, name="deal_modal"),
    path("conversations/", views.conversations, name="conversations"),
    path("conversations/<int:deal_id>/", views.conversation_detail, name="conversation_detail"),
    path("conversations/<int:deal_id>/reply-mode/", views.conversation_reply_mode, name="conversation_reply_mode"),
    path("conversations/<int:deal_id>/send/", views.conversation_send_manual, name="conversation_send_manual"),
    path("monitor/", views.monitor, name="monitor"),
    path("monitor/status/", views.monitor_status, name="monitor_status"),
    path("monitor/bot/<slug:action>/", views.bot_action, name="bot_action"),
    path("monitor/feed/", views.monitor_feed, name="monitor_feed"),
    path("monitor/log/", views.monitor_log, name="monitor_log"),
    path("linkedin-account/", views.linkedin_account, name="linkedin_account"),
    path("linkedin-account/save/", views.linkedin_account_save, name="linkedin_account_save"),
    path("linkedin-account/api/save/", views.linkedin_api_save, name="linkedin_api_save"),
    path("linkedin-account/status/", views.linkedin_account_status, name="linkedin_account_status"),
    path("linkedin-account/<slug:action>/", views.linkedin_account_action, name="linkedin_account_action"),
]
