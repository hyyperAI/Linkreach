# linkreach/chat/admin.py
from django.contrib import admin

from linkreach.chat.models import ChatMessage, ConversationEvent


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ("deal", "is_outgoing", "source", "owner", "initiated_by", "creation_date")
    list_filter = ("is_outgoing", "source", "owner")
    raw_id_fields = ("deal", "owner", "initiated_by", "answer_to", "topic")
    date_hierarchy = "creation_date"
    readonly_fields = ("deal", "content", "owner", "initiated_by", "creation_date")


@admin.register(ConversationEvent)
class ConversationEventAdmin(admin.ModelAdmin):
    list_display = ("deal", "event_type", "created_by", "created_at")
    list_filter = ("event_type",)
    raw_id_fields = ("deal", "created_by")
    date_hierarchy = "created_at"
