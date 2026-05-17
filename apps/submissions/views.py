from __future__ import annotations

import logging
from datetime import timedelta
from pathlib import Path

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.audit.models import AuditLog
from apps.common.rate_limit import check_rate_limit
from apps.common.rate_limit import add_rate_limit_headers
from apps.quests.models import QuestAssignment
from apps.quests.models import SeasonQuest
from apps.quests.permissions import can_manage_season
from apps.realtime.events import broadcast_season_event
from apps.submissions.forms import SubmissionForm
from apps.submissions.forms import ScoreSubmissionForm
from apps.submissions.models import Submission
from apps.submissions.models import SubmissionMedia
from apps.submissions.storage import StorageConfigurationError
from apps.submissions.storage import detect_video_duration_seconds
from apps.submissions.storage import extract_exif_data
from apps.submissions.storage import signed_read_url
from apps.submissions.storage import upload_submission_media
from apps.seasons.models import SeasonParticipant
from apps.seasons.session import bind_session_participant
from apps.seasons.session import get_session_participant

ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov"}
ALLOWED_IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_VIDEO_MIME_TYPES = {"video/mp4", "video/quicktime"}
MAX_IMAGE_SIZE_BYTES = 30 * 1024 * 1024
MAX_VIDEO_SIZE_BYTES = 100 * 1024 * 1024
MAX_VIDEO_DURATION_SECONDS = 15

logger = logging.getLogger(__name__)


def submit_open_quest(request: HttpRequest, quest_id: int) -> HttpResponse:
    season_quest = get_object_or_404(SeasonQuest.objects.select_related("season"), id=quest_id)
    participant = get_session_participant(request, season_quest.season)
    if not participant:
        messages.error(request, "Join the season before submitting.")
        return redirect("season-detail", slug=season_quest.season.slug)

    if season_quest.quest_mode != SeasonQuest.QuestMode.OPEN:
        messages.error(request, "Use the scheduled quest enrollment flow for this quest.")
        return redirect("season-detail", slug=season_quest.season.slug)

    if season_quest.status != SeasonQuest.Status.ACTIVE:
        messages.error(request, "Quest is not active yet.")
        return redirect("season-detail", slug=season_quest.season.slug)

    limit = 20
    window_seconds = 60
    allowed, retry_after, current_count = check_rate_limit(
        key=f"quest-submit-direct:{season_quest.season_id}:{participant.id}",
        limit=limit,
        window_seconds=window_seconds,
    )
    if not allowed:
        messages.error(request, f"Too many submit attempts. Retry in about {retry_after} seconds.")
        response = redirect("season-detail", slug=season_quest.season.slug)
        return add_rate_limit_headers(
            response,
            limit=limit,
            window_seconds=window_seconds,
            remaining=0,
            retry_after=retry_after,
        )

    assignment, _ = QuestAssignment.objects.get_or_create(
        season_quest=season_quest,
        participant=participant,
        defaults={"assignment_source": QuestAssignment.Source.OPEN_CLAIM},
    )
    response = redirect("assignment-submit", assignment_id=assignment.id)
    return add_rate_limit_headers(
        response,
        limit=limit,
        window_seconds=window_seconds,
        remaining=limit - current_count,
    )


def submit_assignment(request: HttpRequest, assignment_id: int) -> HttpResponse:
    assignment = get_object_or_404(
        QuestAssignment.objects.select_related("season_quest__season", "participant"),
        id=assignment_id,
    )
    season = assignment.season_quest.season
    participant = get_session_participant(request, season)
    if not participant and getattr(request.user, "is_authenticated", False):
        participant = (
            SeasonParticipant.objects.filter(season=season, account=request.user)
            .order_by("joined_at")
            .first()
        )
        if participant:
            bind_session_participant(request, season, participant)
    if not participant or assignment.participant_id != participant.id:
        messages.error(request, "You can only submit for your own assigned quests.")
        return redirect("season-detail", slug=season.slug)

    submission = getattr(assignment, "submission", None)
    can_edit_submission = assignment.status != QuestAssignment.Status.SCORED

    if request.method == "POST":
        submit_action = (request.POST.get("submit_action") or "submit").strip().lower()
        if submit_action not in {"draft", "submit"}:
            submit_action = "submit"

        if submission and not can_edit_submission:
            messages.error(request, "This submission has already been scored and can no longer be edited.")
            return redirect("assignment-submit", assignment_id=assignment.id)

        limit = 10
        window_seconds = 60
        allowed, retry_after, current_count = check_rate_limit(
            key=f"submit:{assignment.season_quest.season_id}:{participant.id}",
            limit=limit,
            window_seconds=window_seconds,
        )
        if not allowed:
            messages.error(request, f"Too many submission attempts. Retry in about {retry_after} seconds.")
            response = redirect("season-detail", slug=season.slug)
            return add_rate_limit_headers(
                response,
                limit=limit,
                window_seconds=window_seconds,
                remaining=0,
                retry_after=retry_after,
            )

    if request.method == "POST" and submit_action == "submit":
        timing_error = _submission_timing_error(assignment)
        if timing_error:
            season_quest = assignment.season_quest
            logger.info(
                "Submission timing rejected for assignment %s (%s): %s | status=%s started_at=%s ends_at=%s",
                assignment.id,
                season_quest.quest_mode,
                timing_error,
                season_quest.status,
                season_quest.started_at.isoformat() if season_quest.started_at else None,
                season_quest.ends_at.isoformat() if season_quest.ends_at else None,
            )
            messages.error(request, timing_error)
            return redirect("season-detail", slug=season.slug)

    if request.method == "POST":
        form = SubmissionForm(request.POST, request.FILES)
        if form.is_valid():
            media_files = request.FILES.getlist("media_files")
            text_response = form.cleaned_data["text_response"].strip()
            existing_media_count = submission.media_items.count() if submission else 0

            if not media_files and not text_response and existing_media_count == 0:
                if submit_action == "draft":
                    messages.error(request, "Add text or at least one media file before saving draft.")
                else:
                    messages.error(request, "Add text or at least one media file before submitting.")
                return render(
                    request,
                    "submissions/form.html",
                    {
                        "form": form,
                        "assignment": assignment,
                        "submission": submission,
                        "can_edit_submission": can_edit_submission,
                    },
                )

            validation_errors = _validate_media_files(media_files)
            if validation_errors:
                for error in validation_errors:
                    messages.error(request, error)
                return render(
                    request,
                    "submissions/form.html",
                    {
                        "form": form,
                        "assignment": assignment,
                        "submission": submission,
                        "can_edit_submission": can_edit_submission,
                    },
                )

            created_submission = False
            previous_text_response = submission.text_response if submission else ""
            previous_is_draft = submission.is_draft if submission else False
            if not submission:
                submission = Submission.objects.create(
                    quest_assignment=assignment,
                    text_response=text_response,
                    is_draft=(submit_action == "draft"),
                )
                created_submission = True

            try:
                next_sort_order = submission.media_items.count()
                for index, media_file in enumerate(media_files):
                    media_type = "video" if media_file.content_type in ALLOWED_VIDEO_MIME_TYPES else "image"
                    duration_seconds = None
                    if media_type == SubmissionMedia.MediaType.VIDEO:
                        duration_seconds = detect_video_duration_seconds(media_file)

                    # Extract EXIF before stripping so we retain it in the DB.
                    exif_data = extract_exif_data(media_file) if media_type == "image" else None

                    blob_url = upload_submission_media(
                        season_slug=assignment.season_quest.season.slug,
                        assignment_id=assignment.id,
                        uploaded_file=media_file,
                        media_type=media_type,
                        strip_exif=True,
                    )
                    SubmissionMedia.objects.create(
                        submission=submission,
                        blob_path_or_url=blob_url,
                        media_type=media_type,
                        mime_type=media_file.content_type,
                        file_size_bytes=media_file.size,
                        duration_seconds=duration_seconds,
                        sort_order=next_sort_order + index,
                        exif_data=exif_data,
                    )
                fields_to_update: list[str] = []
                if submission.text_response != text_response:
                    submission.text_response = text_response
                    fields_to_update.append("text_response")

                desired_is_draft = submit_action == "draft"
                if submission.is_draft != desired_is_draft:
                    submission.is_draft = desired_is_draft
                    fields_to_update.append("is_draft")
                    if not desired_is_draft:
                        submission.submitted_at = timezone.now()
                        fields_to_update.append("submitted_at")

                if fields_to_update:
                    submission.save(update_fields=fields_to_update)
            except StorageConfigurationError:
                if created_submission:
                    submission.delete()
                else:
                    rollback_fields: list[str] = []
                    if submission.text_response != previous_text_response:
                        submission.text_response = previous_text_response
                        rollback_fields.append("text_response")
                    if submission.is_draft != previous_is_draft:
                        submission.is_draft = previous_is_draft
                        rollback_fields.append("is_draft")
                    if rollback_fields:
                        submission.save(update_fields=rollback_fields)
                logger.exception("Submission upload failed due to storage configuration for assignment %s.", assignment.id)
                messages.error(request, "There was an error uploading the media.")
                return render(
                    request,
                    "submissions/form.html",
                    {
                        "form": form,
                        "assignment": assignment,
                        "submission": submission if not created_submission else None,
                        "can_edit_submission": can_edit_submission,
                    },
                )
            except Exception:
                if created_submission:
                    submission.delete()
                else:
                    rollback_fields: list[str] = []
                    if submission.text_response != previous_text_response:
                        submission.text_response = previous_text_response
                        rollback_fields.append("text_response")
                    if submission.is_draft != previous_is_draft:
                        submission.is_draft = previous_is_draft
                        rollback_fields.append("is_draft")
                    if rollback_fields:
                        submission.save(update_fields=rollback_fields)
                logger.exception("Submission upload failed unexpectedly for assignment %s.", assignment.id)
                messages.error(request, "Upload failed unexpectedly. Please try again.")
                return render(
                    request,
                    "submissions/form.html",
                    {
                        "form": form,
                        "assignment": assignment,
                        "submission": submission if not created_submission else None,
                        "can_edit_submission": can_edit_submission,
                    },
                )

            if submit_action == "submit":
                assignment.status = QuestAssignment.Status.SUBMITTED
                assignment.save(update_fields=["status"])
                if created_submission:
                    broadcast_season_event(
                        season_id=assignment.season_quest.season_id,
                        payload={
                            "event": "submission_created",
                            "assignment_id": assignment.id,
                            "season_quest_id": assignment.season_quest_id,
                            "participant_id": assignment.participant_id,
                        },
                    )
                    messages.success(request, "Submission received.")
                else:
                    messages.success(request, "Submission updated and submitted for scoring.")
            else:
                assignment.status = QuestAssignment.Status.PENDING
                assignment.save(update_fields=["status"])
                messages.success(request, "Draft saved.")
            response = redirect("season-detail", slug=season.slug)
            return add_rate_limit_headers(
                response,
                limit=limit,
                window_seconds=window_seconds,
                remaining=limit - current_count,
            )
    else:
        form = SubmissionForm(initial={"text_response": submission.text_response} if submission else None)

    if submission:
        for media in submission.media_items.all():
            media.signed_url = signed_read_url(media.blob_path_or_url)

    season_quest = assignment.season_quest
    ends_at_iso = season_quest.ends_at.isoformat() if season_quest.ends_at and season_quest.quest_mode == SeasonQuest.QuestMode.SCHEDULED else None

    return render(
        request,
        "submissions/form.html",
        {
            "form": form,
            "assignment": assignment,
            "submission": submission,
            "can_edit_submission": can_edit_submission,
            "submission_is_draft": bool(submission and submission.is_draft),
            "ends_at_iso": ends_at_iso,
        },
    )


def view_assignment(request: HttpRequest, assignment_id: int) -> HttpResponse:
    assignment = get_object_or_404(
        QuestAssignment.objects.select_related("season_quest__season", "season_quest__quest", "participant"),
        id=assignment_id,
    )
    season = assignment.season_quest.season
    participant = get_session_participant(request, season)
    if not participant and getattr(request.user, "is_authenticated", False):
        participant = (
            SeasonParticipant.objects.filter(season=season, account=request.user)
            .order_by("joined_at")
            .first()
        )
        if participant:
            bind_session_participant(request, season, participant)
    if not participant or assignment.participant_id != participant.id:
        messages.error(request, "You can only view your own assigned quests.")
        return redirect("season-detail", slug=season.slug)

    season_quest = assignment.season_quest
    submission = getattr(assignment, "submission", None)

    # Scheduled quests get the lifecycle-aware page
    if season_quest.quest_mode == SeasonQuest.QuestMode.SCHEDULED:
        return _render_scheduled_quest(request, assignment, submission)

    if not submission:
        messages.error(request, "No submission found for this assignment.")
        return redirect("season-detail", slug=season.slug)

    # Fetch signed URLs for media
    for media in submission.media_items.all():
        media.signed_url = signed_read_url(media.blob_path_or_url)

    return render(
        request,
        "submissions/view.html",
        {
            "assignment": assignment,
            "submission": submission,
        },
    )


def _render_scheduled_quest(
    request: HttpRequest, assignment: QuestAssignment, submission: Submission | None
) -> HttpResponse:
    season_quest = assignment.season_quest
    now = timezone.now()

    # Determine the quest phase
    if season_quest.status in {SeasonQuest.Status.COMPLETE, SeasonQuest.Status.ARCHIVED}:
        phase = "expired"
    elif season_quest.ends_at and now > season_quest.ends_at:
        if season_quest.allow_late_submissions:
            grace_deadline = season_quest.ends_at + timedelta(seconds=season_quest.late_grace_seconds)
            phase = "active" if now <= grace_deadline else "expired"
        else:
            phase = "expired"
    elif season_quest.status == SeasonQuest.Status.ACTIVE and season_quest.started_at:
        phase = "active"
    elif season_quest.opens_at and now >= season_quest.opens_at and season_quest.status == SeasonQuest.Status.ACTIVE:
        phase = "active"
    else:
        phase = "waiting"

    # ISO timestamps for JavaScript countdowns
    opens_at_iso = season_quest.opens_at.isoformat() if season_quest.opens_at else None
    ends_at_iso = season_quest.ends_at.isoformat() if season_quest.ends_at else None

    # Prepare submission form for active phase
    form = None
    can_edit_submission = False
    if phase == "active":
        can_edit_submission = assignment.status != QuestAssignment.Status.SCORED
        form = SubmissionForm(initial={"text_response": submission.text_response if submission else ""})

    # Fetch signed URLs for media on existing submissions
    if submission:
        for media in submission.media_items.all():
            media.signed_url = signed_read_url(media.blob_path_or_url)

    return render(
        request,
        "submissions/scheduled_quest.html",
        {
            "assignment": assignment,
            "submission": submission,
            "phase": phase,
            "opens_at_iso": opens_at_iso,
            "ends_at_iso": ends_at_iso,
            "form": form,
            "can_edit_submission": can_edit_submission,
        },
    )


def scoring_queue(request: HttpRequest, slug: str) -> HttpResponse:
    from apps.seasons.models import Season

    season = get_object_or_404(Season, slug=slug)
    participant = _resolve_scorer_participant(request, season)
    if not _can_score(request, season, participant):
        messages.error(request, "Host or admin access required.")
        return redirect("season-detail", slug=slug)

    submissions = (
        Submission.objects.filter(quest_assignment__season_quest__season=season, is_draft=False)
        .select_related("quest_assignment__participant", "quest_assignment__season_quest")
        .prefetch_related("media_items")
        .order_by("score", "-submitted_at")
    )

    submission_ids = [submission.id for submission in submissions]
    score_logs_by_submission: dict[int, list[AuditLog]] = {}
    if submission_ids:
        score_update_logs = AuditLog.objects.filter(
            season=season,
            action_type="submission.score.updated",
            target_type="Submission",
            target_id__in=[str(submission_id) for submission_id in submission_ids],
        ).select_related("actor_participant").order_by("-created_at", "-id")
        for log in score_update_logs:
            try:
                submission_id = int(log.target_id)
            except (TypeError, ValueError):
                continue
            score_logs_by_submission.setdefault(submission_id, []).append(log)

    for submission in submissions:
        for media in submission.media_items.all():
            media.signed_url = signed_read_url(media.blob_path_or_url)
        timeline = [
            {
                "label": "Joined quest",
                "timestamp": submission.quest_assignment.assigned_at,
                "detail": f"Joined via {submission.quest_assignment.get_assignment_source_display()}.",
            },
            {
                "label": "Submitted response",
                "timestamp": submission.submitted_at,
                "detail": "Participant submitted a response.",
            },
        ]
        for log in reversed(score_logs_by_submission.get(submission.id, [])):
            new_values = log.new_value_json or {}
            score_value = new_values.get("score")
            judge_note = (new_values.get("judge_note") or "").strip()
            actor_handle = log.actor_participant.handle if log.actor_participant else "Staff"
            detail_parts: list[str] = [f"Updated by {actor_handle}."]
            if score_value is not None:
                detail_parts.append(f"Score set to {score_value}.")
            if judge_note:
                detail_parts.append(f"Judge note: {judge_note}")

            timeline.append(
                {
                    "label": "Judge update",
                    "timestamp": log.created_at,
                    "detail": " ".join(detail_parts),
                }
            )

        submission.timeline_events = timeline
        submission.timeline_event_count = len(timeline)

    pending_submissions = [submission for submission in submissions if submission.score is None]
    scored_submissions = [submission for submission in submissions if submission.score is not None]

    return render(
        request,
        "submissions/scoring_queue.html",
        {
            "season": season,
            "pending_submissions": pending_submissions,
            "scored_submissions": scored_submissions,
        },
    )


@require_POST
def score_submission(request: HttpRequest, submission_id: int) -> HttpResponse:
    submission = get_object_or_404(
        Submission.objects.select_related("quest_assignment__season_quest__season", "quest_assignment"),
        id=submission_id,
    )
    season = submission.quest_assignment.season_quest.season
    scorer = _resolve_scorer_participant(request, season)
    if not _can_score(request, season, scorer):
        messages.error(request, "Host or admin access required.")
        return redirect("season-detail", slug=season.slug)

    limit = 30
    window_seconds = 60
    scorer_key = str(scorer.id) if scorer else f"user:{request.user.id}"
    allowed, retry_after, current_count = check_rate_limit(
        key=f"score:{season.id}:{scorer_key}",
        limit=limit,
        window_seconds=window_seconds,
    )
    if not allowed:
        messages.error(request, f"Too many scoring actions. Retry in about {retry_after} seconds.")
        response = redirect("season-scoring-queue", slug=season.slug)
        return add_rate_limit_headers(
            response,
            limit=limit,
            window_seconds=window_seconds,
            remaining=0,
            retry_after=retry_after,
        )

    form = ScoreSubmissionForm(request.POST)
    if not form.is_valid():
        for field_errors in form.errors.values():
            for err in field_errors:
                messages.error(request, err)
        return redirect("season-scoring-queue", slug=season.slug)

    new_score = form.cleaned_data["score"]
    judge_note = form.cleaned_data["judge_note"].strip()

    old_score = submission.score
    old_note = submission.judge_note

    submission.score = new_score
    submission.judge_note = judge_note
    submission.scored_at = timezone.now()
    submission.scored_by_participant = scorer
    submission.save(update_fields=["score", "judge_note", "scored_at", "scored_by_participant"])

    assignment = submission.quest_assignment
    assignment.status = QuestAssignment.Status.SCORED
    assignment.save(update_fields=["status"])

    AuditLog.objects.create(
        season=season,
        actor_participant=scorer,
        action_type="submission.score.updated",
        target_type="Submission",
        target_id=str(submission.id),
        old_value_json={"score": old_score, "judge_note": old_note},
        new_value_json={"score": new_score, "judge_note": judge_note},
        reason=judge_note,
    )

    broadcast_season_event(
        season_id=season.id,
        payload={
            "event": "submission_scored",
            "submission_id": submission.id,
            "assignment_id": assignment.id,
            "score": new_score,
        },
    )

    messages.success(request, "Submission scored.")
    response = redirect("season-scoring-queue", slug=season.slug)
    return add_rate_limit_headers(
        response,
        limit=limit,
        window_seconds=window_seconds,
        remaining=limit - current_count,
    )


def _validate_media_files(media_files) -> list[str]:
    errors: list[str] = []
    for media_file in media_files:
        extension = Path(media_file.name).suffix.lower()
        content_type = media_file.content_type

        if extension in ALLOWED_IMAGE_EXTENSIONS:
            if content_type not in ALLOWED_IMAGE_MIME_TYPES:
                errors.append(f"{media_file.name}: MIME type mismatch for image file.")
                continue
            if media_file.size > MAX_IMAGE_SIZE_BYTES:
                errors.append(f"{media_file.name}: image exceeds 30MB limit.")
                continue

        elif extension in ALLOWED_VIDEO_EXTENSIONS:
            if content_type not in ALLOWED_VIDEO_MIME_TYPES:
                errors.append(f"{media_file.name}: MIME type mismatch for video file.")
                continue
            if media_file.size > MAX_VIDEO_SIZE_BYTES:
                errors.append(f"{media_file.name}: video exceeds 100MB limit.")
                continue

            duration = detect_video_duration_seconds(media_file)
            if duration is None:
                errors.append(f"{media_file.name}: could not determine video duration.")
                continue
            if duration > MAX_VIDEO_DURATION_SECONDS:
                errors.append(f"{media_file.name}: video exceeds 15 second duration limit.")
                continue
        else:
            errors.append(f"{media_file.name}: unsupported file type.")

    return errors


def _resolve_scorer_participant(request: HttpRequest, season) -> SeasonParticipant | None:
    participant = get_session_participant(request, season)
    if participant:
        return participant

    user = request.user
    if not getattr(user, "is_authenticated", False):
        return None

    return (
        SeasonParticipant.objects.filter(
            season=season,
            account=user,
            role__in=[SeasonParticipant.Role.HOST, SeasonParticipant.Role.ADMIN],
        )
        .order_by("joined_at")
        .first()
    )


def _can_score(request: HttpRequest, season, participant: SeasonParticipant | None) -> bool:
    if can_manage_season(request, season):
        return True
    if not participant:
        return False
    return participant.role in {SeasonParticipant.Role.HOST, SeasonParticipant.Role.ADMIN}


def _submission_timing_error(assignment: QuestAssignment) -> str | None:
    season_quest = assignment.season_quest
    if season_quest.quest_mode != season_quest.QuestMode.SCHEDULED:
        return None

    now = timezone.now()
    if season_quest.started_at and now < season_quest.started_at:
        return "Scheduled quest has not started yet."

    if season_quest.ends_at and now > season_quest.ends_at:
        if season_quest.allow_late_submissions:
            grace_deadline = season_quest.ends_at + timedelta(seconds=season_quest.late_grace_seconds)
            if now <= grace_deadline:
                return None
        return "Submission window has closed."

    if season_quest.status in {season_quest.Status.COMPLETE, season_quest.Status.ARCHIVED}:
        return "Submission window has closed."

    return None
