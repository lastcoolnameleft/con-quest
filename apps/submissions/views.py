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
from apps.seasons.session import get_session_participant

ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov"}
ALLOWED_IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_VIDEO_MIME_TYPES = {"video/mp4", "video/quicktime"}
MAX_IMAGE_SIZE_BYTES = 30 * 1024 * 1024
MAX_VIDEO_SIZE_BYTES = 100 * 1024 * 1024
MAX_VIDEO_DURATION_SECONDS = 15

logger = logging.getLogger(__name__)


def submit_assignment(request: HttpRequest, assignment_id: int) -> HttpResponse:
    assignment = get_object_or_404(
        QuestAssignment.objects.select_related("season_quest__season", "participant"),
        id=assignment_id,
    )
    participant = get_session_participant(request, assignment.season_quest.season)
    if not participant or assignment.participant_id != participant.id:
        messages.error(request, "You can only submit for your own assigned quests.")
        return redirect("season-detail", slug=assignment.season_quest.season.slug)

    if request.method == "POST":
        limit = 10
        window_seconds = 60
        allowed, retry_after, current_count = check_rate_limit(
            key=f"submit:{assignment.season_quest.season_id}:{participant.id}",
            limit=limit,
            window_seconds=window_seconds,
        )
        if not allowed:
            messages.error(request, f"Too many submission attempts. Retry in about {retry_after} seconds.")
            response = redirect("season-detail", slug=assignment.season_quest.season.slug)
            return add_rate_limit_headers(
                response,
                limit=limit,
                window_seconds=window_seconds,
                remaining=0,
                retry_after=retry_after,
            )

    if hasattr(assignment, "submission"):
        messages.info(request, "This assignment already has a submission.")
        return redirect("season-detail", slug=assignment.season_quest.season.slug)

    if request.method == "POST":
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
            return redirect("season-detail", slug=assignment.season_quest.season.slug)

    if request.method == "POST":
        form = SubmissionForm(request.POST, request.FILES)
        if form.is_valid():
            media_files = request.FILES.getlist("media_files")
            text_response = form.cleaned_data["text_response"].strip()

            if not media_files and not text_response:
                messages.error(request, "Add text or at least one media file.")
                return render(
                    request,
                    "submissions/form.html",
                    {"form": form, "assignment": assignment},
                )

            validation_errors = _validate_media_files(media_files)
            if validation_errors:
                for error in validation_errors:
                    messages.error(request, error)
                return render(request, "submissions/form.html", {"form": form, "assignment": assignment})

            submission = Submission.objects.create(
                quest_assignment=assignment,
                text_response=text_response,
            )

            try:
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
                        sort_order=index,
                        exif_data=exif_data,
                    )
            except StorageConfigurationError as exc:
                submission.delete()
                messages.error(request, str(exc))
                return render(request, "submissions/form.html", {"form": form, "assignment": assignment})
            except Exception:
                submission.delete()
                logger.exception("Submission upload failed unexpectedly for assignment %s.", assignment.id)
                messages.error(request, "Upload failed unexpectedly. Please try again.")
                return render(request, "submissions/form.html", {"form": form, "assignment": assignment})

            assignment.status = QuestAssignment.Status.SUBMITTED
            assignment.save(update_fields=["status"])
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
            response = redirect("season-detail", slug=assignment.season_quest.season.slug)
            return add_rate_limit_headers(
                response,
                limit=limit,
                window_seconds=window_seconds,
                remaining=limit - current_count,
            )
    else:
        form = SubmissionForm()

    return render(request, "submissions/form.html", {"form": form, "assignment": assignment})


def scoring_queue(request: HttpRequest, slug: str) -> HttpResponse:
    from apps.seasons.models import Season

    season = get_object_or_404(Season, slug=slug)
    participant = get_session_participant(request, season)
    if not _can_score(participant):
        messages.error(request, "Host or admin access required.")
        return redirect("season-detail", slug=slug)

    submissions = (
        Submission.objects.filter(quest_assignment__season_quest__season=season)
        .select_related("quest_assignment__participant", "quest_assignment__season_quest")
        .prefetch_related("media_items")
        .order_by("score", "-submitted_at")
    )

    for submission in submissions:
        for media in submission.media_items.all():
            media.signed_url = signed_read_url(media.blob_path_or_url)

    return render(
        request,
        "submissions/scoring_queue.html",
        {
            "season": season,
            "submissions": submissions,
        },
    )


@require_POST
def score_submission(request: HttpRequest, submission_id: int) -> HttpResponse:
    submission = get_object_or_404(
        Submission.objects.select_related("quest_assignment__season_quest__season", "quest_assignment"),
        id=submission_id,
    )
    season = submission.quest_assignment.season_quest.season
    scorer = get_session_participant(request, season)
    if not _can_score(scorer):
        messages.error(request, "Host or admin access required.")
        return redirect("season-detail", slug=season.slug)

    limit = 30
    window_seconds = 60
    allowed, retry_after, current_count = check_rate_limit(
        key=f"score:{season.id}:{scorer.id}",
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
    reason = form.cleaned_data["reason"].strip()

    old_score = submission.score
    old_note = submission.judge_note
    score_changed = old_score != new_score
    if old_score is not None and score_changed and not reason:
        messages.error(request, "Reason is required when editing an existing score.")
        return redirect("season-scoring-queue", slug=season.slug)

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
        reason=reason,
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


def _can_score(participant: SeasonParticipant | None) -> bool:
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
