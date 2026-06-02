"""Custom error handler views with Sentry reporting."""

import sentry_sdk
from django.shortcuts import render


def handler400(request, exception=None):
    return render(request, "errors/400.html", status=400)


def handler403(request, exception=None):
    with sentry_sdk.push_scope() as scope:
        scope.set_extra("path", request.path)
        scope.set_extra("method", request.method)
        sentry_sdk.capture_message(f"403 Forbidden: {request.path}", level="warning")
    return render(request, "errors/403.html", status=403)


def handler404(request, exception=None):
    with sentry_sdk.push_scope() as scope:
        scope.set_extra("path", request.path)
        scope.set_extra("method", request.method)
        sentry_sdk.capture_message(f"404 Not Found: {request.path}", level="info")
    return render(request, "errors/404.html", status=404)


def handler500(request):
    return render(request, "errors/500.html", status=500)
