from datetime import timedelta

from django.contrib import messages
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.common.rate_limit import add_rate_limit_headers
from apps.common.rate_limit import check_rate_limit
from apps.quests.forms import QuestForm
from apps.quests.forms import SeasonQuestForm
from apps.quests.models import QuestAssignment
from apps.quests.models import Quest
from apps.quests.models import SeasonQuest
from apps.realtime.events import broadcast_season_event
from apps.quests.permissions import can_manage_season
from apps.quests.permissions import can_create_quests
from apps.seasons.models import Season
from apps.seasons.models import SeasonParticipant
from apps.seasons.session import get_session_participant


def _activate_quest_window(season_quest: SeasonQuest) -> None:
    now = timezone.now()
    fairness_buffer_seconds = 2
    season_quest.started_at = now + timedelta(seconds=fairness_buffer_seconds)
    season_quest.ends_at = season_quest.started_at + timedelta(seconds=season_quest.duration_seconds)
    season_quest.status = SeasonQuest.Status.ACTIVE
    season_quest.save(update_fields=["started_at", "ends_at", "status", "updated_at"])

    broadcast_season_event(
        season_id=season_quest.season_id,
        payload={
            "event": "quest_started",
            "season_quest_id": season_quest.id,
            "started_at": season_quest.started_at.isoformat(),
            "ends_at": season_quest.ends_at.isoformat(),
            "server_time": now.isoformat(),
        },
    )


def season_quest_create(request: HttpRequest, slug: str) -> HttpResponse:
    season = get_object_or_404(Season, slug=slug)
    participant = get_session_participant(request, season)
    if not can_manage_season(request, season):
        messages.error(request, "Host or admin access required.")
        return redirect("season-detail", slug=slug)

    quest_defaults = {
        str(quest.id): {"title": quest.title, "description": quest.description}
        for quest in Quest.objects.order_by("title")
    }

    if request.method == "POST":
        form = SeasonQuestForm(request.POST, season=season)
        if form.is_valid():
            season_quest = form.save(commit=False)
            season_quest.season = season
            season_quest.created_by_participant = participant
            season_quest.save()
            messages.success(request, "Season quest created.")
            return redirect("control-dashboard")
        form.add_error(None, "Could not save quest. Fix the highlighted fields and try again.")
    else:
        form = SeasonQuestForm(season=season)

    return render(
        request,
        "quests/season_quest_form.html",
        {"season": season, "form": form, "is_edit": False, "quest_defaults": quest_defaults},
    )


def quest_create(request: HttpRequest) -> HttpResponse:
    if not can_create_quests(request):
        messages.error(request, "Host or admin access required.")
        return redirect("season-index")

    if request.method == "POST":
        form = QuestForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Quest created.")
            return redirect("season-index")
    else:
        form = QuestForm()

    return render(request, "quests/quest_form.html", {"form": form, "is_edit": False})


def quest_edit(request: HttpRequest, quest_id: int) -> HttpResponse:
    if not can_create_quests(request):
        messages.error(request, "Host or admin access required.")
        return redirect("season-index")

    quest = get_object_or_404(Quest, id=quest_id)
    if request.method == "POST":
        form = QuestForm(request.POST, instance=quest)
        if form.is_valid():
            form.save()
            messages.success(request, "Quest updated.")
            return redirect("control-dashboard")
    else:
        form = QuestForm(instance=quest)

    return render(request, "quests/quest_form.html", {"form": form, "is_edit": True})


def quest_delete(request: HttpRequest, quest_id: int) -> HttpResponse:
    if not can_create_quests(request):
        messages.error(request, "Host or admin access required.")
        return redirect("season-index")

    quest = get_object_or_404(Quest, id=quest_id)

    if quest.season_quests.exists():
        messages.error(request, "Cannot delete a quest that is tied to one or more seasons.")
        return redirect("control-dashboard")

    if request.method == "POST":
        quest.delete()
        messages.success(request, "Quest deleted.")
        return redirect("control-dashboard")

    return render(request, "control/quest_confirm_delete.html", {"quest": quest})


def season_quest_edit(request: HttpRequest, quest_id: int) -> HttpResponse:
    season_quest = get_object_or_404(SeasonQuest.objects.select_related("season"), id=quest_id)
    if not can_manage_season(request, season_quest.season):
        messages.error(request, "Host or admin access required.")
        return redirect("season-index")

    quest_defaults = {
        str(quest.id): {"title": quest.title, "description": quest.description}
        for quest in Quest.objects.order_by("title")
    }

    if request.method == "POST":
        form = SeasonQuestForm(request.POST, instance=season_quest, season=season_quest.season)
        if form.is_valid():
            form.save()
            messages.success(request, "Season quest updated.")
            return redirect("control-dashboard")
        form.add_error(None, "Could not save quest. Fix the highlighted fields and try again.")
    else:
        form = SeasonQuestForm(instance=season_quest, season=season_quest.season)

    return render(
        request,
        "quests/season_quest_form.html",
        {"season": season_quest.season, "form": form, "is_edit": True, "quest_defaults": quest_defaults},
    )


def season_quest_delete(request: HttpRequest, quest_id: int) -> HttpResponse:
    season_quest = get_object_or_404(SeasonQuest.objects.select_related("season"), id=quest_id)
    if not can_manage_season(request, season_quest.season):
        messages.error(request, "Host or admin access required.")
        return redirect("season-index")

    if request.method == "POST":
        season_quest.delete()
        messages.success(request, "Season quest deleted.")
        return redirect("control-dashboard")

    return render(request, "control/season_quest_confirm_delete.html", {"season_quest": season_quest})


@require_POST
def start_scheduled_quest(request: HttpRequest, quest_id: int) -> HttpResponse:
    season_quest = get_object_or_404(SeasonQuest.objects.select_related("season"), id=quest_id)
    participant = get_session_participant(request, season_quest.season)
    if not can_manage_season(request, season_quest.season):
        messages.error(request, "Host or admin access required.")
        return redirect("control-dashboard")

    actor_id = participant.id if participant else f"user-{request.user.id}"

    limit = 20
    window_seconds = 60
    allowed, retry_after, current_count = check_rate_limit(
        key=f"quest-start:{season_quest.season_id}:{actor_id}",
        limit=limit,
        window_seconds=window_seconds,
    )
    if not allowed:
        messages.error(request, f"Too many start attempts. Retry in about {retry_after} seconds.")
        response = redirect("control-dashboard")
        return add_rate_limit_headers(
            response,
            limit=limit,
            window_seconds=window_seconds,
            remaining=0,
            retry_after=retry_after,
        )

    if season_quest.quest_mode != SeasonQuest.QuestMode.SCHEDULED:
        messages.error(request, "Only scheduled quests can be started manually.")
        response = redirect("control-dashboard")
        return add_rate_limit_headers(
            response,
            limit=limit,
            window_seconds=window_seconds,
            remaining=limit - current_count,
        )

    if season_quest.status == SeasonQuest.Status.ACTIVE:
        messages.info(request, "Scheduled quest is already live.")
        response = redirect("control-dashboard")
        return add_rate_limit_headers(
            response,
            limit=limit,
            window_seconds=window_seconds,
            remaining=limit - current_count,
        )

    if season_quest.status in {SeasonQuest.Status.COMPLETE, SeasonQuest.Status.ARCHIVED}:
        messages.error(request, "Closed or archived scheduled quests cannot be started.")
        response = redirect("control-dashboard")
        return add_rate_limit_headers(
            response,
            limit=limit,
            window_seconds=window_seconds,
            remaining=limit - current_count,
        )

    if season_quest.status != SeasonQuest.Status.PENDING:
        messages.error(request, "Scheduled quests must be published before they can be started.")
        response = redirect("control-dashboard")
        return add_rate_limit_headers(
            response,
            limit=limit,
            window_seconds=window_seconds,
            remaining=limit - current_count,
        )

    _activate_quest_window(season_quest)

    messages.success(request, f"Scheduled quest '{season_quest.resolved_title}' started.")
    response = redirect("control-dashboard")
    return add_rate_limit_headers(
        response,
        limit=limit,
        window_seconds=window_seconds,
        remaining=limit - current_count,
    )


@require_POST
def transition_season_quest_status(request: HttpRequest, quest_id: int) -> HttpResponse:
    season_quest = get_object_or_404(SeasonQuest.objects.select_related("season"), id=quest_id)
    if not can_manage_season(request, season_quest.season):
        messages.error(request, "Host or admin access required.")
        return redirect("control-dashboard")

    target_status = (request.POST.get("status") or "").strip().lower()
    valid_statuses = {choice for choice, _ in SeasonQuest.Status.choices}
    if target_status not in valid_statuses:
        messages.error(request, "Invalid target status.")
        return redirect("control-dashboard")

    if not season_quest.can_transition_to(target_status):
        messages.error(request, "Invalid status transition.")
        return redirect("control-dashboard")

    if target_status == SeasonQuest.Status.ACTIVE:
        if season_quest.quest_mode == SeasonQuest.QuestMode.SCHEDULED:
            _activate_quest_window(season_quest)
        else:
            season_quest.status = SeasonQuest.Status.ACTIVE
            season_quest.save(update_fields=["status", "updated_at"])
        messages.success(request, "Quest is now active.")
        return redirect("control-dashboard")

    if target_status == SeasonQuest.Status.COMPLETE:
        season_quest.status = SeasonQuest.Status.COMPLETE
        if not season_quest.ends_at:
            season_quest.ends_at = timezone.now()
            season_quest.save(update_fields=["status", "ends_at", "updated_at"])
        else:
            season_quest.save(update_fields=["status", "updated_at"])
        broadcast_season_event(
            season_id=season_quest.season_id,
            payload={
                "event": "quest_completed",
                "season_quest_id": season_quest.id,
            },
        )
        messages.success(request, "Quest marked complete.")
        return redirect("control-dashboard")

    season_quest.status = target_status
    season_quest.save(update_fields=["status", "updated_at"])
    messages.success(request, f"Quest moved to {season_quest.get_status_display()}.")
    return redirect("control-dashboard")


@require_POST
def enroll_scheduled_quest(request: HttpRequest, quest_id: int) -> HttpResponse:
    season_quest = get_object_or_404(SeasonQuest.objects.select_related("season"), id=quest_id)
    participant = get_session_participant(request, season_quest.season)
    if not participant:
        messages.error(request, "Join the season before enrolling.")
        return redirect("season-detail", slug=season_quest.season.slug)

    limit = 20
    window_seconds = 60
    allowed, retry_after, current_count = check_rate_limit(
        key=f"quest-enroll:{season_quest.season_id}:{participant.id}",
        limit=limit,
        window_seconds=window_seconds,
    )
    if not allowed:
        messages.error(request, f"Too many enroll attempts. Retry in about {retry_after} seconds.")
        response = redirect("season-detail", slug=season_quest.season.slug)
        return add_rate_limit_headers(
            response,
            limit=limit,
            window_seconds=window_seconds,
            remaining=0,
            retry_after=retry_after,
        )

    if season_quest.quest_mode != SeasonQuest.QuestMode.SCHEDULED:
        messages.error(request, "This quest is not scheduled.")
        return redirect("season-detail", slug=season_quest.season.slug)
    expected_code = season_quest.rsvp_code.strip().upper() if season_quest.rsvp_code else ""
    if expected_code:
        submitted_code = (request.POST.get("rsvp_code") or "").strip().upper()
        if submitted_code != expected_code:
            messages.error(request, "Invalid RSVP code.")
            return redirect("season-detail", slug=season_quest.season.slug)

    assignment, _created = QuestAssignment.objects.get_or_create(
        season_quest=season_quest,
        participant=participant,
        defaults={"assignment_source": QuestAssignment.Source.RSVP_CODE},
    )
    messages.success(request, f"Enrolled in scheduled quest '{season_quest.resolved_title}'.")
    response = redirect("assignment-view", assignment_id=assignment.pk)
    return add_rate_limit_headers(
        response,
        limit=limit,
        window_seconds=window_seconds,
        remaining=limit - current_count,
    )


def _can_manage_quests(participant: SeasonParticipant | None) -> bool:
    if not participant:
        return False
    return participant.role in {SeasonParticipant.Role.HOST, SeasonParticipant.Role.ADMIN}


def season_quest_status_check(request: HttpRequest, quest_id: int) -> JsonResponse:
    """Lightweight polling endpoint returning the current quest status."""
    season_quest = get_object_or_404(SeasonQuest, id=quest_id)
    return JsonResponse({
        "status": season_quest.status,
        "started_at": season_quest.started_at.isoformat() if season_quest.started_at else None,
        "ends_at": season_quest.ends_at.isoformat() if season_quest.ends_at else None,
    })
