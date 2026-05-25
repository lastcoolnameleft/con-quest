import os

from django.http import JsonResponse


def health(request):
    """HTTP health check endpoint returning app status and git SHA."""
    return JsonResponse({
        "status": "ok",
        "sha": os.environ.get("GIT_SHA", "dev"),
    })
