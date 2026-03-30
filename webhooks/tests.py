"""
Tests for Django Webhook Service
"""

import hashlib
import hmac
import json

from django.test import TestCase, Client
from django.urls import reverse
from django.conf import settings

from webhooks.models import WebhookEvent


def _make_signature(body: bytes) -> str:
    secret = settings.WEBHOOK_SECRET.encode()
    digest = hmac.new(secret, body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


class WebhookReceiveTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.url = "/webhook/receive/"

    # ── Happy path ────────────────────────────────────────────────────────

    def test_valid_payload_returns_200(self):
        payload = {"event_type": "user.created", "data": {"email": "a@b.com"}}
        body = json.dumps(payload).encode()
        resp = self.client.post(
            self.url,
            data=body,
            content_type="application/json",
            HTTP_X_WEBHOOK_SIGNATURE=_make_signature(body),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("event_id", resp.json())

    def test_event_stored_in_db(self):
        payload = {"event_type": "payment.success", "data": {"order_id": "ORD123"}}
        body = json.dumps(payload).encode()
        self.client.post(
            self.url,
            data=body,
            content_type="application/json",
            HTTP_X_WEBHOOK_SIGNATURE=_make_signature(body),
        )
        self.assertEqual(WebhookEvent.objects.count(), 1)
        event = WebhookEvent.objects.first()
        self.assertEqual(event.event_type, "payment.success")

    def test_event_status_becomes_processed(self):
        payload = {"event_type": "order.placed", "data": {"order_id": "ORD456"}}
        body = json.dumps(payload).encode()
        resp = self.client.post(
            self.url,
            data=body,
            content_type="application/json",
            HTTP_X_WEBHOOK_SIGNATURE=_make_signature(body),
        )
        event = WebhookEvent.objects.get(pk=resp.json()["event_id"])
        self.assertEqual(event.status, "processed")

    # ── Validation errors ─────────────────────────────────────────────────

    def test_missing_event_type_returns_400(self):
        payload = {"data": {"foo": "bar"}}
        body = json.dumps(payload).encode()
        resp = self.client.post(
            self.url,
            data=body,
            content_type="application/json",
            HTTP_X_WEBHOOK_SIGNATURE=_make_signature(body),
        )
        self.assertEqual(resp.status_code, 400)

    def test_non_json_body_returns_400(self):
        resp = self.client.post(
            self.url,
            data="not-json",
            content_type="text/plain",
        )
        self.assertIn(resp.status_code, [400, 403])

    # ── Security ──────────────────────────────────────────────────────────

    def test_invalid_signature_returns_403(self):
        payload = {"event_type": "user.created", "data": {}}
        body = json.dumps(payload).encode()
        resp = self.client.post(
            self.url,
            data=body,
            content_type="application/json",
            HTTP_X_WEBHOOK_SIGNATURE="sha256=badsignature",
        )
        self.assertEqual(resp.status_code, 403)

    def test_missing_signature_returns_403(self):
        payload = {"event_type": "user.created", "data": {}}
        resp = self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 403)


class WebhookListTests(TestCase):
    def setUp(self):
        WebhookEvent.objects.create(
            event_type="user.created",
            payload={"event_type": "user.created", "data": {}},
        )
        WebhookEvent.objects.create(
            event_type="payment.success",
            payload={"event_type": "payment.success", "data": {}},
        )

    def test_list_returns_all_events(self):
        resp = self.client.get("/webhook/events/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 2)

    def test_filter_by_event_type(self):
        resp = self.client.get("/webhook/events/?event_type=user.created")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(all(e["event_type"] == "user.created" for e in data))

    def test_detail_returns_single_event(self):
        event = WebhookEvent.objects.first()
        resp = self.client.get(f"/webhook/events/{event.pk}/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["id"], event.pk)

    def test_detail_404_for_missing(self):
        resp = self.client.get("/webhook/events/99999/")
        self.assertEqual(resp.status_code, 404)
