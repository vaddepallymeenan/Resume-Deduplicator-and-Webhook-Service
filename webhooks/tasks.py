"""
tasks.py
========
Processing logic for webhook events.

Currently runs synchronously.
To switch to Celery, uncomment the @shared_task decorator and
call  process_webhook_event.delay(event.id)  from views.py.
"""

import logging
from django.utils import timezone

log = logging.getLogger(__name__)

# Uncomment when using Celery:
# from celery import shared_task


# @shared_task
def process_webhook_event(event) -> None:
    """
    Main processing hook. Dispatches to specific handlers by event_type.
    Marks the event as processed (or failed) when done.
    """
    try:
        _dispatch(event)
        event.status = "processed"
        event.processed_at = timezone.now()
        event.save(update_fields=["status", "processed_at"])
        log.info("Event %s processed successfully.", event.id)
    except Exception as exc:
        event.status = "failed"
        event.error_message = str(exc)
        event.save(update_fields=["status", "error_message"])
        log.exception("Event %s processing failed: %s", event.id, exc)


# ---------------------------------------------------------------------------
# Event-type dispatch table
# ---------------------------------------------------------------------------

def _dispatch(event) -> None:
    handlers = {
        "user.created":     _handle_user_created,
        "payment.success":  _handle_payment_success,
        "payment.failed":   _handle_payment_failed,
        "order.placed":     _handle_order_placed,
    }
    handler = handlers.get(event.event_type, _handle_unknown)
    handler(event)


def _handle_user_created(event) -> None:
    data = event.payload.get("data", {})
    log.info(
        "New user registered: email=%s name=%s",
        data.get("email", "—"),
        data.get("name", "—"),
    )


def _handle_payment_success(event) -> None:
    data = event.payload.get("data", {})
    log.info(
        "Payment SUCCESS: order=%s amount=%s",
        data.get("order_id", "—"),
        data.get("amount", "—"),
    )


def _handle_payment_failed(event) -> None:
    data = event.payload.get("data", {})
    log.warning(
        "Payment FAILED: order=%s reason=%s",
        data.get("order_id", "—"),
        data.get("reason", "—"),
    )


def _handle_order_placed(event) -> None:
    data = event.payload.get("data", {})
    log.info(
        "Order placed: order_id=%s items=%s",
        data.get("order_id", "—"),
        data.get("item_count", "—"),
    )


def _handle_unknown(event) -> None:
    log.warning("Unknown event_type received: %s", event.event_type)
