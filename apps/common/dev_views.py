"""Dev-only persona switcher for testing multiple participants.

This module is gated behind DEBUG=True at both the URL and view level.
It will never be accessible in staging or production.
"""

from __future__ import annotations

from django.conf import settings
from django.contrib import messages
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from apps.seasons.models import Season, SeasonParticipant
from apps.seasons.session import bind_session_participant


def _require_debug_admin(request: HttpRequest) -> None:
    if not settings.DEBUG:
        raise Http404
    if not request.user.is_authenticated or not request.user.is_staff:
        raise Http404


def switch_persona(request: HttpRequest, slug: str) -> HttpResponse:
    _require_debug_admin(request)

    season = get_object_or_404(Season, slug=slug)
    participants = SeasonParticipant.objects.filter(season=season).order_by("handle")

    if request.method == "POST":
        participant_id = request.POST.get("participant_id")
        participant = get_object_or_404(SeasonParticipant, id=participant_id, season=season)
        bind_session_participant(request, season, participant)
        messages.success(request, f'Switched to "{participant.handle}".')
        return redirect("season-detail", slug=season.slug)

    current_key = f"season_participant_{season.id}"
    current_id = request.session.get(current_key)

    return render(
        request,
        "dev/switch_persona.html",
        {
            "season": season,
            "participants": participants,
            "current_participant_id": current_id,
        },
    )
