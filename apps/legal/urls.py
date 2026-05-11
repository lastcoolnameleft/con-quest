from django.urls import path

from apps.legal.views import terms, privacy

urlpatterns = [
    path("terms/", terms, name="legal-terms"),
    path("privacy/", privacy, name="legal-privacy"),
]
