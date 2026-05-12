from datetime import timezone as dt_timezone

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.db import IntegrityError
from django.db.models import Q
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.utils import timezone

from apps.seasons.forms import SeasonJoinForm
from apps.seasons.forms import SeasonForm
from apps.seasons.models import Season
from apps.seasons.models import SeasonParticipant
from apps.seasons.session import bind_session_participant
from apps.seasons.session import get_session_participant
from apps.quests.models import QuestAssignment
from apps.quests.models import Quest
from apps.quests.models import SeasonQuest
from apps.common.rate_limit import check_rate_limit
from apps.common.rate_limit import client_identifier
from apps.common.rate_limit import add_rate_limit_headers
from apps.common.rate_limit import rate_limited_json_response
from apps.quests.permissions import can_access_control_center
from apps.quests.permissions import can_manage_season
from apps.quests.permissions import can_create_quests
from apps.quests.permissions import manageable_seasons_queryset


def index(request: HttpRequest) -> HttpResponse:
    prefill_code = (
        request.GET.get("code")
        or request.GET.get("join_code")
        or request.GET.get("access_code")
        or ""
    ).strip().upper()
    join_form = SeasonJoinForm(initial={"join_code": prefill_code} if prefill_code else None)

    session_participant_ids = [
        int(value)
        for key, value in request.session.items()
        if key.startswith("season_participant_") and str(value).isdigit()
    ]
    participant_filter = Q(id__in=session_participant_ids)
    if request.user.is_authenticated:
        participant_filter |= Q(account=request.user)

    joined_participants = list(
        SeasonParticipant.objects.filter(participant_filter)
        .select_related("season")
        .order_by("-joined_at")
        .distinct()
    )
    assignments_by_participant: dict[int, list[QuestAssignment]] = {}
    if joined_participants:
        assignments = (
            QuestAssignment.objects.filter(participant__in=joined_participants)
            .select_related("season_quest__quest")
            .order_by("season_quest__created_at", "season_quest__id")
        )
        for assignment in assignments:
            assignments_by_participant.setdefault(assignment.participant_id, []).append(assignment)

    joined_seasons = [
        {
            "participant": participant,
            "season": participant.season,
            "assignments": assignments_by_participant.get(participant.id, []),
        }
        for participant in joined_participants
    ]

    return render(
        request,
        "seasons/index.html",
        {
            "join_form": join_form,
            "joined_seasons": joined_seasons,
            "can_create_quests": can_create_quests(request),
        },
    )


def season_detail(request: HttpRequest, slug: str) -> HttpResponse:
    season = get_object_or_404(Season, slug=slug)
    participant = get_session_participant(request, season)
    if not participant and request.user.is_authenticated:
        participant = (
            SeasonParticipant.objects.filter(season=season, account=request.user)
            .order_by("joined_at")
            .first()
        )
        if participant:
            bind_session_participant(request, season, participant)
    can_manage_quests = can_manage_season(request, season)
    visible_statuses = [SeasonQuest.Status.PENDING, SeasonQuest.Status.ACTIVE, SeasonQuest.Status.COMPLETE]
    quests = list(
        season.quests.filter(status__in=visible_statuses)
        .select_related("quest")
        .order_by("-created_at", "-id")
    )
    assignment_map: dict[int, QuestAssignment] = {}
    if participant:
        assignments = (
            QuestAssignment.objects.filter(participant=participant, season_quest__season=season)
            .select_related("submission", "season_quest")
            .all()
        )
        assignment_map = {assignment.season_quest_id: assignment for assignment in assignments}

    for quest in quests:
        quest.participant_assignment = assignment_map.get(quest.id)

    submitted_assignment_count = sum(
        1
        for assignment in assignment_map.values()
        if assignment.status in {QuestAssignment.Status.SUBMITTED, QuestAssignment.Status.SCORED}
    )

    return render(
        request,
        "seasons/detail.html",
        {
            "season": season,
            "participant": participant,
            "can_manage_quests": can_manage_quests,
            "join_form": SeasonJoinForm(),
            "quests": quests,
            "submitted_assignment_count": submitted_assignment_count,
            "can_access_control": can_access_control_center(request),
        },
    )


def control_dashboard(request: HttpRequest) -> HttpResponse:
    if not can_access_control_center(request):
        messages.error(request, "Host or admin access required.")
        return redirect("season-index")

    seasons = manageable_seasons_queryset(request).prefetch_related("quests__quest")
    quests = Quest.objects.order_by("title")[:100]
    return render(
        request,
        "control/dashboard.html",
        {
            "seasons": seasons,
            "quests": quests,
        },
    )


def season_create(request: HttpRequest) -> HttpResponse:
    if not can_access_control_center(request):
        messages.error(request, "Host or admin access required.")
        return redirect("season-index")

    if request.method == "POST":
        form = SeasonForm(request.POST)
        if form.is_valid():
            season = form.save()
            if not (getattr(request.user, "is_authenticated", False) and (request.user.is_staff or request.user.is_superuser)):
                participant_ids = [
                    int(value)
                    for key, value in request.session.items()
                    if key.startswith("season_participant_") and str(value).isdigit()
                ]
                source_participant = (
                    SeasonParticipant.objects.filter(
                        id__in=participant_ids,
                        role__in=[SeasonParticipant.Role.HOST, SeasonParticipant.Role.ADMIN],
                    )
                    .order_by("joined_at")
                    .first()
                )
                if source_participant:
                    participant, _ = SeasonParticipant.objects.get_or_create(
                        season=season,
                        handle=source_participant.handle,
                        defaults={
                            "role": SeasonParticipant.Role.HOST,
                            "account": source_participant.account,
                            "is_guest": source_participant.is_guest,
                        },
                    )
                    bind_session_participant(request, season, participant)
            messages.success(request, "Season created.")
            return redirect("control-dashboard")
    else:
        form = SeasonForm()

    return render(request, "control/season_form.html", {"form": form, "season": None})


def season_edit(request: HttpRequest, slug: str) -> HttpResponse:
    season = get_object_or_404(Season, slug=slug)
    if not can_manage_season(request, season):
        messages.error(request, "Host or admin access required.")
        return redirect("season-index")

    if request.method == "POST":
        form = SeasonForm(request.POST, instance=season)
        if form.is_valid():
            form.save()
            messages.success(request, "Season updated.")
            return redirect("control-dashboard")
    else:
        form = SeasonForm(instance=season)

    return render(request, "control/season_form.html", {"form": form, "season": season})


def season_delete(request: HttpRequest, slug: str) -> HttpResponse:
    season = get_object_or_404(Season, slug=slug)
    if not can_manage_season(request, season):
        messages.error(request, "Host or admin access required.")
        return redirect("season-index")

    if request.method == "POST":
        season.delete()
        messages.success(request, "Season deleted.")
        return redirect("control-dashboard")

    return render(request, "control/season_confirm_delete.html", {"season": season})


@require_POST
def join_season(request: HttpRequest, slug: str) -> HttpResponse:
    season = get_object_or_404(Season, slug=slug)
    limit = 5
    window_seconds = 60
    allowed, retry_after, current_count = check_rate_limit(
        key=f"join:{slug}:{client_identifier(request)}",
        limit=limit,
        window_seconds=window_seconds,
    )
    if not allowed:
        messages.error(request, f"Too many join attempts. Try again in about {retry_after} seconds.")
        response = redirect("season-detail", slug=slug)
        return add_rate_limit_headers(
            response,
            limit=limit,
            window_seconds=window_seconds,
            remaining=0,
            retry_after=retry_after,
        )

    form = SeasonJoinForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Please provide a valid join code and display name.")
        return redirect("season-detail", slug=slug)

    join_code = (form.cleaned_data.get("join_code") or "").strip().upper()
    if season.join_code and join_code != season.join_code:
        messages.error(request, "Invalid season join code.")
        return redirect("season-detail", slug=slug)

    handle = form.cleaned_data["handle"].strip()
    try:
        participant, _ = SeasonParticipant.objects.get_or_create(
            season=season,
            handle=handle,
            defaults={"is_guest": True},
        )
    except IntegrityError:
        messages.error(request, "Handle is already taken in this season.")
        return redirect("season-detail", slug=slug)

    bind_session_participant(request, season, participant)
    messages.success(request, f"Joined {season.title} as {participant.handle}.")
    return redirect("season-detail", slug=slug)


@require_POST
def join_season_by_code(request: HttpRequest) -> HttpResponse:
    limit = 5
    window_seconds = 60
    allowed, retry_after, current_count = check_rate_limit(
        key=f"join-by-code:{client_identifier(request)}",
        limit=limit,
        window_seconds=window_seconds,
    )
    if not allowed:
        messages.error(request, f"Too many join attempts. Try again in about {retry_after} seconds.")
        response = redirect("season-index")
        return add_rate_limit_headers(
            response,
            limit=limit,
            window_seconds=window_seconds,
            remaining=0,
            retry_after=retry_after,
        )

    form = SeasonJoinForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Please provide a valid join code and display name.")
        return redirect("season-index")

    join_code = (form.cleaned_data.get("join_code") or "").strip().upper()
    season = Season.objects.filter(join_code__iexact=join_code).order_by("-created_at").first()
    if not season:
        messages.error(request, "Invalid season join code.")
        return redirect("season-index")

    handle = form.cleaned_data["handle"].strip()
    try:
        participant, _ = SeasonParticipant.objects.get_or_create(
            season=season,
            handle=handle,
            defaults={"is_guest": True},
        )
    except IntegrityError:
        messages.error(request, "Handle is already taken in this season.")
        return redirect("season-index")

    bind_session_participant(request, season, participant)
    messages.success(request, f"Joined {season.title} as {participant.handle}.")
    return redirect("season-detail", slug=season.slug)


@login_required
@require_POST
def claim_participation(request: HttpRequest, slug: str) -> HttpResponse:
    season = get_object_or_404(Season, slug=slug)
    participant = get_session_participant(request, season)
    if not participant:
        messages.error(request, "Join the season first before claiming participation.")
        return redirect("season-detail", slug=slug)

    existing = SeasonParticipant.objects.filter(season=season, account=request.user).exclude(id=participant.id).first()
    if existing:
        messages.error(request, "Your account is already linked to a different participant in this season.")
        return redirect("season-detail", slug=slug)

    participant.account = request.user
    participant.is_guest = False
    participant.claimed_at = timezone.now()
    participant.save(update_fields=["account", "is_guest", "claimed_at"])
    messages.success(request, "Participation is now linked to your account.")
    return redirect("season-detail", slug=slug)


def connection_test(request: HttpRequest, slug: str) -> JsonResponse:
    season = get_object_or_404(Season, slug=slug)
    limit = 20
    window_seconds = 60
    allowed, retry_after, current_count = check_rate_limit(
        key=f"connection-test:{slug}:{client_identifier(request)}",
        limit=limit,
        window_seconds=window_seconds,
    )
    if not allowed:
        return rate_limited_json_response(
            limit=limit,
            window_seconds=window_seconds,
            retry_after=retry_after,
            message="Too many connection tests in a short time.",
            extra_payload={
                "status": "Not Ready",
                "guidance": "Too many connection tests in a short time.",
            },
        )

    websocket_url = f"/ws/season/{season.id}/"
    redis_configured = bool(settings.REDIS_URL)
    status = "Ready" if redis_configured else "Risky"
    guidance = (
        "WebSocket transport should be available. Poll fallback remains enabled."
        if redis_configured
        else "Redis is not configured; use polling fallback."
    )

    client_time_ms = request.GET.get("client_time_ms")
    server_time = timezone.now()
    clock_offset_ms = None
    if client_time_ms:
        try:
            client_ts = int(client_time_ms) / 1000
            client_time = timezone.datetime.fromtimestamp(client_ts, tz=dt_timezone.utc)
            clock_offset_ms = int((server_time - client_time).total_seconds() * 1000)
        except (ValueError, OSError):
            clock_offset_ms = None

    response = JsonResponse(
        {
            "status": status,
            "guidance": guidance,
            "server_time": server_time.isoformat(),
            "clock_offset_ms": clock_offset_ms,
            "recommended_latency_ms": 400,
            "recommended_clock_offset_ms": 1000,
            "websocket_url": websocket_url,
            "poll_fallback_interval_seconds": 2,
            "redis_configured": redis_configured,
        }
    )
    return add_rate_limit_headers(
        response,
        limit=limit,
        window_seconds=window_seconds,
        remaining=limit - current_count,
    )


def connection_test_global(request: HttpRequest) -> JsonResponse:
    limit = 20
    window_seconds = 60
    allowed, retry_after, current_count = check_rate_limit(
        key=f"connection-test-global:{client_identifier(request)}",
        limit=limit,
        window_seconds=window_seconds,
    )
    if not allowed:
        return rate_limited_json_response(
            limit=limit,
            window_seconds=window_seconds,
            retry_after=retry_after,
            message="Too many connection tests in a short time.",
            extra_payload={
                "status": "Not Ready",
                "guidance": "Too many connection tests in a short time.",
            },
        )

    redis_configured = bool(settings.REDIS_URL)
    status = "Ready" if redis_configured else "Risky"
    guidance = (
        "WebSocket transport should be available. Poll fallback remains enabled."
        if redis_configured
        else "Redis is not configured; use polling fallback."
    )

    client_time_ms = request.GET.get("client_time_ms")
    server_time = timezone.now()
    clock_offset_ms = None
    if client_time_ms:
        try:
            client_ts = int(client_time_ms) / 1000
            client_time = timezone.datetime.fromtimestamp(client_ts, tz=dt_timezone.utc)
            clock_offset_ms = int((server_time - client_time).total_seconds() * 1000)
        except (ValueError, OSError):
            clock_offset_ms = None

    response = JsonResponse(
        {
            "status": status,
            "guidance": guidance,
            "server_time": server_time.isoformat(),
            "clock_offset_ms": clock_offset_ms,
            "recommended_latency_ms": 400,
            "recommended_clock_offset_ms": 1000,
            "redis_configured": redis_configured,
        }
    )
    return add_rate_limit_headers(
        response,
        limit=limit,
        window_seconds=window_seconds,
        remaining=limit - current_count,
    )


def season_state(request: HttpRequest, slug: str) -> JsonResponse:
    season = get_object_or_404(Season, slug=slug)
    limit = 120
    window_seconds = 60
    allowed, retry_after, current_count = check_rate_limit(
        key=f"season-state:{slug}:{client_identifier(request)}",
        limit=limit,
        window_seconds=window_seconds,
    )
    if not allowed:
        return rate_limited_json_response(
            limit=limit,
            window_seconds=window_seconds,
            retry_after=retry_after,
            message="Rate limit exceeded.",
        )

    quests = (
        SeasonQuest.objects.filter(season=season)
        .select_related("quest")
        .order_by("-created_at", "-id")
    )
    response = JsonResponse(
        {
            "server_time": timezone.now().isoformat(),
            "quests": [
                {
                    "id": quest.id,
                    "title": quest.resolved_title,
                    "status": quest.status,
                    "quest_mode": quest.quest_mode,
                    "started_at": quest.started_at.isoformat() if quest.started_at else None,
                    "ends_at": quest.ends_at.isoformat() if quest.ends_at else None,
                }
                for quest in quests
            ],
        }
    )
    return add_rate_limit_headers(
        response,
        limit=limit,
        window_seconds=window_seconds,
        remaining=limit - current_count,
    )
