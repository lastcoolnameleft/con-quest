from __future__ import annotations

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.audit.models import AuditLog
from apps.common.rate_limit import check_rate_limit
from apps.common.rate_limit import add_rate_limit_headers
from apps.quests.models import QuestAssignment
from apps.moderation.forms import ModerationReportForm
from apps.moderation.forms import ResolveReportForm
from apps.moderation.models import ModerationReport
from apps.seasons.models import Season
from apps.seasons.models import SeasonParticipant
from apps.seasons.session import get_session_participant
from apps.submissions.models import Submission


def report_submission(request: HttpRequest, submission_id: int) -> HttpResponse:
    submission = get_object_or_404(
        Submission.objects.select_related("quest_assignment__season_quest__season"),
        id=submission_id,
    )
    season = submission.quest_assignment.season_quest.season
    participant = get_session_participant(request, season)
    if not participant:
        messages.error(request, "Join the season before filing reports.")
        return redirect("season-detail", slug=season.slug)

    if request.method == "POST":
        limit = 5
        window_seconds = 3600
        allowed, retry_after, current_count = check_rate_limit(
            key=f"report:{season.id}:{participant.id}",
            limit=limit,
            window_seconds=window_seconds,
        )
        if not allowed:
            messages.error(request, f"Rate limit reached. Retry in about {retry_after} seconds.")
            response = redirect("season-detail", slug=season.slug)
            return add_rate_limit_headers(
                response,
                limit=limit,
                window_seconds=window_seconds,
                remaining=0,
                retry_after=retry_after,
            )

        form = ModerationReportForm(request.POST)
        if form.is_valid():
            report = ModerationReport.objects.create(
                reporter_participant=participant,
                target_type="Submission",
                target_id=str(submission.id),
                reason=form.cleaned_data["reason"],
                details=form.cleaned_data["details"].strip(),
            )
            AuditLog.objects.create(
                season=season,
                actor_participant=participant,
                action_type="moderation.report.created",
                target_type="ModerationReport",
                target_id=str(report.id),
                new_value_json={"reason": report.reason, "target_submission_id": submission.id},
            )
            messages.success(request, "Report submitted.")
            response = redirect("season-detail", slug=season.slug)
            return add_rate_limit_headers(
                response,
                limit=limit,
                window_seconds=window_seconds,
                remaining=limit - current_count,
            )
    else:
        form = ModerationReportForm()

    return render(
        request,
        "moderation/report_form.html",
        {
            "form": form,
            "submission": submission,
            "season": season,
        },
    )


def moderation_queue(request: HttpRequest, slug: str) -> HttpResponse:
    season = get_object_or_404(Season, slug=slug)
    moderator = get_session_participant(request, season)
    if not _can_moderate(request, moderator):
        messages.error(request, "Host or admin access required.")
        return redirect("season-detail", slug=slug)

    reports = (
        ModerationReport.objects.filter(
            reporter_participant__season=season,
            status=ModerationReport.Status.OPEN,
        )
        .select_related("reporter_participant")
        .order_by("created_at")
    )
    submission_map = {
        str(sub.id): sub
        for sub in Submission.objects.filter(id__in=[r.target_id for r in reports if r.target_type == "Submission"]).select_related(
            "quest_assignment__participant",
            "quest_assignment__season_quest",
        )
    }

    for report in reports:
        report.target_submission = submission_map.get(report.target_id)

    return render(
        request,
        "moderation/queue.html",
        {
            "season": season,
            "reports": reports,
        },
    )


@require_POST
def resolve_report(request: HttpRequest, report_id: int) -> HttpResponse:
    report = get_object_or_404(
        ModerationReport.objects.select_related("reporter_participant__season"),
        id=report_id,
    )
    season = report.reporter_participant.season
    moderator = get_session_participant(request, season)
    if not _can_moderate(request, moderator):
        messages.error(request, "Host or admin access required.")
        return redirect("season-detail", slug=season.slug)

    limit = 20
    window_seconds = 60
    moderator_key = str(moderator.id) if moderator else f"user:{request.user.id}"
    allowed, retry_after, current_count = check_rate_limit(
        key=f"moderation-resolve:{season.id}:{moderator_key}",
        limit=limit,
        window_seconds=window_seconds,
    )
    if not allowed:
        messages.error(request, f"Too many moderation actions. Retry in about {retry_after} seconds.")
        response = redirect("season-moderation-queue", slug=season.slug)
        return add_rate_limit_headers(
            response,
            limit=limit,
            window_seconds=window_seconds,
            remaining=0,
            retry_after=retry_after,
        )

    form = ResolveReportForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Invalid moderation resolution request.")
        return redirect("season-moderation-queue", slug=season.slug)

    old_status = report.status
    report.status = form.cleaned_data["status"]
    report.details = form.cleaned_data["details"].strip() or report.details
    report.resolved_at = timezone.now()
    report.save(update_fields=["status", "details", "resolved_at"])

    AuditLog.objects.create(
        season=season,
        actor_participant=moderator,
        action_type="moderation.report.resolved",
        target_type="ModerationReport",
        target_id=str(report.id),
        old_value_json={"status": old_status},
        new_value_json={"status": report.status},
        reason=form.cleaned_data["details"].strip(),
    )

    messages.success(request, "Report resolved.")
    response = redirect("season-moderation-queue", slug=season.slug)
    return add_rate_limit_headers(
        response,
        limit=limit,
        window_seconds=window_seconds,
        remaining=limit - current_count,
    )


def _can_moderate(request: HttpRequest, participant: SeasonParticipant | None) -> bool:
    user = request.user
    if getattr(user, "is_authenticated", False) and (user.is_staff or user.is_superuser):
        return True
    if not participant:
        return False
    return participant.role in {SeasonParticipant.Role.HOST, SeasonParticipant.Role.ADMIN}
