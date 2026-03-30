"""
Webhook views
=============
POST /webhook/receive/   – receive & store a webhook
GET  /webhook/events/    – list all stored events
GET  /webhook/events/<id>/  – retrieve a single event
"""

import hashlib
import hmac
import json
import logging
from datetime import timezone

from django.conf import settings
from django.utils import timezone as dj_tz
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import WebhookEvent
from .serializers import WebhookEventSerializer
from .tasks import process_webhook_event   # sync task runner (see tasks.py)

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_client_ip(request: Request) -> str:
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


def _verify_signature(request: Request) -> bool:
    """
    Optional HMAC-SHA256 signature verification.
    The sender should include the header:
        X-Webhook-Signature: sha256=<hex_digest>
    computed over the raw request body using the shared WEBHOOK_SECRET.
    """
    secret = getattr(settings, "WEBHOOK_SECRET", "")
    if not secret:
        return True  # skip verification if no secret configured

    sig_header = request.META.get("HTTP_X_WEBHOOK_SIGNATURE", "")
    if not sig_header.startswith("sha256="):
        log.warning("Missing or malformed X-Webhook-Signature header.")
        return False

    expected = hmac.new(
        secret.encode(),
        request.body,
        hashlib.sha256,
    ).hexdigest()

    received = sig_header[len("sha256="):]
    return hmac.compare_digest(expected, received)


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------

class WebhookReceiveView(APIView):
    """
    POST /webhook/receive/

    Accepts a JSON body with at minimum:
        { "event_type": "...", "data": { ... } }

    Returns 200 on success, 400 on validation failure, 403 on auth failure.
    """

    def post(self, request: Request) -> Response:
        # ── 1. Signature verification (optional but recommended) ─────────
        if not _verify_signature(request):
            return Response(
                {"error": "Invalid signature."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # ── 2. Payload validation ─────────────────────────────────────────
        payload = request.data
        if not isinstance(payload, dict):
            return Response(
                {"error": "Payload must be a JSON object."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        event_type = payload.get("event_type", "").strip()
        if not event_type:
            return Response(
                {"error": "'event_type' is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ── 3. Store the event ────────────────────────────────────────────
        event = WebhookEvent.objects.create(
            event_type=event_type,
            payload=payload,
            source_ip=_get_client_ip(request),
            status=WebhookEvent.Status.RECEIVED,
        )
        log.info("Webhook received: id=%s type=%s", event.id, event_type)

        # ── 4. Process (sync; swap for Celery task in production) ─────────
        process_webhook_event(event)

        return Response(
            {
                "message": "Webhook received successfully.",
                "event_id": event.id,
                "status": event.status,
            },
            status=status.HTTP_200_OK,
        )


class WebhookEventListView(APIView):
    """GET /webhook/events/ — list recent webhook events (latest 100)."""

    def get(self, request: Request) -> Response:
        event_type = request.query_params.get("event_type")
        qs = WebhookEvent.objects.all()[:100]
        if event_type:
            qs = WebhookEvent.objects.filter(event_type=event_type)[:100]
        serializer = WebhookEventSerializer(qs, many=True)
        return Response(serializer.data)


class WebhookEventDetailView(APIView):
    """GET /webhook/events/<id>/ — retrieve a single event."""

    def get(self, request: Request, pk: int) -> Response:
        try:
            event = WebhookEvent.objects.get(pk=pk)
        except WebhookEvent.DoesNotExist:
            return Response(
                {"error": "Event not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(WebhookEventSerializer(event).data)
