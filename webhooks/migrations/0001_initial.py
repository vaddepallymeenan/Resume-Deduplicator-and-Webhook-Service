from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="WebhookEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("event_type", models.CharField(db_index=True, max_length=120)),
                ("payload", models.JSONField()),
                ("source_ip", models.GenericIPAddressField(blank=True, null=True)),
                ("status", models.CharField(
                    choices=[("received", "Received"), ("processed", "Processed"), ("failed", "Failed")],
                    default="received",
                    max_length=20,
                )),
                ("error_message", models.TextField(blank=True)),
                ("received_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("processed_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={"ordering": ["-received_at"]},
        ),
    ]
