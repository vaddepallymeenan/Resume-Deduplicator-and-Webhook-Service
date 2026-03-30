from rest_framework import serializers
from .models import WebhookEvent


class WebhookEventSerializer(serializers.ModelSerializer):
    class Meta:
        model  = WebhookEvent
        fields = [
            "id", "event_type", "payload", "source_ip",
            "status", "error_message", "received_at", "processed_at",
        ]
        read_only_fields = fields
