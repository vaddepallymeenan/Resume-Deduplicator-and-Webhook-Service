from django.db import models


class WebhookEvent(models.Model):
    """Stores every incoming webhook payload."""

    class Status(models.TextChoices):
        RECEIVED   = "received",   "Received"
        PROCESSED  = "processed",  "Processed"
        FAILED     = "failed",     "Failed"

    event_type  = models.CharField(max_length=120, db_index=True)
    payload     = models.JSONField()
    source_ip   = models.GenericIPAddressField(null=True, blank=True)
    status      = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.RECEIVED,
    )
    error_message = models.TextField(blank=True)
    received_at   = models.DateTimeField(auto_now_add=True, db_index=True)
    processed_at  = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-received_at"]

    def __str__(self):
        return f"[{self.event_type}] {self.received_at:%Y-%m-%d %H:%M:%S}"
