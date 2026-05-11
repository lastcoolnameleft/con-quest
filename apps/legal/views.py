from django.http import HttpRequest, HttpResponse
from django.shortcuts import render


def terms(request: HttpRequest) -> HttpResponse:
    return render(request, "legal/terms.html")


def privacy(request: HttpRequest) -> HttpResponse:
    return render(request, "legal/privacy.html")
