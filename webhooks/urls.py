from django.urls import path
from . import views

urlpatterns = [
    path("webhook/receive/",       views.WebhookReceiveView.as_view(),      name="webhook-receive"),
    path("webhook/events/",        views.WebhookEventListView.as_view(),    name="webhook-events"),
    path("webhook/events/<int:pk>/", views.WebhookEventDetailView.as_view(), name="webhook-event-detail"),
]
