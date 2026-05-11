from django.http import HttpRequest
from django.db.models import QuerySet

from apps.seasons.models import Season
from apps.seasons.models import SeasonParticipant


def _session_participant_ids(request: HttpRequest) -> list[int]:
    participant_ids: list[int] = []
    for key, value in request.session.items():
        if not key.startswith("season_participant_"):
            continue
        try:
            participant_ids.append(int(value))
        except (TypeError, ValueError):
            continue
    return participant_ids


def can_access_control_center(request: HttpRequest) -> bool:
    user = request.user
    if getattr(user, "is_authenticated", False):
        if user.is_staff or user.is_superuser:
            return True
        if SeasonParticipant.objects.filter(
            account=user,
            role__in=[SeasonParticipant.Role.HOST, SeasonParticipant.Role.ADMIN],
        ).exists():
            return True

    participant_ids = _session_participant_ids(request)
    if not participant_ids:
        return False

    return SeasonParticipant.objects.filter(
        id__in=participant_ids,
        role__in=[SeasonParticipant.Role.HOST, SeasonParticipant.Role.ADMIN],
    ).exists()


def manageable_seasons_queryset(request: HttpRequest) -> QuerySet[Season]:
    user = request.user
    if getattr(user, "is_authenticated", False) and (user.is_staff or user.is_superuser):
        return Season.objects.order_by("-created_at")

    by_account = Season.objects.none()
    if getattr(user, "is_authenticated", False):
        by_account = Season.objects.filter(
            participants__account=user,
            participants__role__in=[SeasonParticipant.Role.HOST, SeasonParticipant.Role.ADMIN],
        )

    participant_ids = _session_participant_ids(request)
    by_session = Season.objects.none()
    if participant_ids:
        by_session = Season.objects.filter(
            participants__id__in=participant_ids,
            participants__role__in=[SeasonParticipant.Role.HOST, SeasonParticipant.Role.ADMIN],
        )

    return (by_account | by_session).distinct().order_by("-created_at")


def can_manage_season(request: HttpRequest, season: Season) -> bool:
    user = request.user
    if getattr(user, "is_authenticated", False) and (user.is_staff or user.is_superuser):
        return True

    if getattr(user, "is_authenticated", False):
        if SeasonParticipant.objects.filter(
            season=season,
            account=user,
            role__in=[SeasonParticipant.Role.HOST, SeasonParticipant.Role.ADMIN],
        ).exists():
            return True

    participant_id = request.session.get(f"season_participant_{season.id}")
    if not participant_id:
        return False

    return SeasonParticipant.objects.filter(
        id=participant_id,
        season=season,
        role__in=[SeasonParticipant.Role.HOST, SeasonParticipant.Role.ADMIN],
    ).exists()


def can_create_quests(request: HttpRequest) -> bool:
    return can_access_control_center(request)
