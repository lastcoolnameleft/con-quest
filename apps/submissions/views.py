from __future__ import annotations

import json
import logging
from datetime import timedelta
from pathlib import Path

from django.contrib import messages
from django.core import signing
from django.core.signing import BadSignature
from django.core.signing import SignatureExpired
from django.db import transaction
from django.http import HttpRequest, HttpResponse, JsonResponse
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
from apps.submissions.storage import create_direct_upload_target
from apps.submissions.storage import fetch_blob_properties
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
MAX_MEDIA_FILES_PER_SUBMISSION = 5
UPLOAD_TICKET_TTL_SECONDS = 30 * 60
UPLOAD_TICKET_SALT = "submissions.direct-upload"

logger = logging.getLogger(__name__)


@require_POST
def prepare_assignment_uploads(request: HttpRequest, assignment_id: int) -> HttpResponse:
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
        return JsonResponse(
            {"error": "You can only upload media for your own assigned quests."},
            status=403,
        )

    if assignment.status == QuestAssignment.Status.SCORED:
        return JsonResponse(
            {"error": "This submission has already been scored and is read-only."},
            status=409,
        )

    limit = 20
    window_seconds = 60
    allowed, retry_after, current_count = check_rate_limit(
        key=f"upload-target:{assignment.season_quest.season_id}:{participant.id}",
        limit=limit,
        window_seconds=window_seconds,
    )
    if not allowed:
        return JsonResponse(
            {
                "error": f"Too many upload attempts. Retry in about {retry_after} seconds.",
            },
            status=429,
        )

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "Invalid upload request payload."}, status=400)

    files = payload.get("files")
    if not isinstance(files, list) or not files:
        return JsonResponse({"error": "No files were provided."}, status=400)

    submission = getattr(assignment, "submission", None)
    existing_media_count = submission.media_items.count() if submission else 0
    if existing_media_count + len(files) > MAX_MEDIA_FILES_PER_SUBMISSION:
        remaining_slots = max(MAX_MEDIA_FILES_PER_SUBMISSION - existing_media_count, 0)
        return JsonResponse(
            {
                "error": (
                    f"You can add up to {MAX_MEDIA_FILES_PER_SUBMISSION} media files per submission. "
                    f"You have {remaining_slots} slot(s) remaining."
                )
            },
            status=400,
        )

    uploads: list[dict] = []
    errors: list[str] = []
    for descriptor in files:
        if not isinstance(descriptor, dict):
            errors.append("Invalid file metadata.")
            continue

        file_name = str(descriptor.get("name") or "").strip()
        content_type = str(descriptor.get("type") or "").strip().lower()
        try:
            file_size = int(descriptor.get("size", 0))
        except (TypeError, ValueError):
            file_size = 0

        raw_duration_seconds = descriptor.get("duration_seconds")
        duration_seconds: int | None = None
        if raw_duration_seconds is not None:
            try:
                duration_seconds = int(raw_duration_seconds)
            except (TypeError, ValueError):
                duration_seconds = None

        media_type, descriptor_errors = _validate_media_descriptor(
            file_name=file_name,
            content_type=content_type,
            file_size=file_size,
            duration_seconds=duration_seconds,
        )
        if descriptor_errors:
            errors.extend(descriptor_errors)
            continue

        try:
            upload_target = create_direct_upload_target(
                season_slug=assignment.season_quest.season.slug,
                assignment_id=assignment.id,
                media_type=media_type,
                original_filename=file_name,
                content_type=content_type,
            )
        except StorageConfigurationError:
            return JsonResponse(
                {"error": "Storage is not configured for direct uploads."},
                status=503,
            )

        ticket = signing.dumps(
            {
                "assignment_id": assignment.id,
                "participant_id": participant.id,
                "blob_url": upload_target["blob_url"],
                "media_type": media_type,
                "content_type": content_type,
                "file_size_bytes": file_size,
                "original_name": file_name,
                "duration_seconds": duration_seconds,
            },
            salt=UPLOAD_TICKET_SALT,
        )

        uploads.append(
            {
                "ticket": ticket,
                "upload_url": upload_target["upload_url"],
                "blob_url": upload_target["blob_url"],
                "headers": {
                    "x-ms-blob-type": "BlockBlob",
                    "x-ms-blob-content-type": content_type,
                },
            }
        )

    if errors:
        return JsonResponse({"errors": errors}, status=400)

    response = JsonResponse(
        {
            "uploads": uploads,
            "max_files": MAX_MEDIA_FILES_PER_SUBMISSION,
        }
    )
    return add_rate_limit_headers(
        response,
        limit=limit,
        window_seconds=window_seconds,
        remaining=limit - current_count,
    )


def submit_open_quest(request: HttpRequest, quest_id: int) -> HttpResponse:
    season_quest = get_object_or_404(
        SeasonQuest.objects.select_related("season"), id=quest_id
    )
    participant = get_session_participant(request, season_quest.season)
    if not participant:
        messages.error(request, "Join the season before submitting.")
        return redirect("season-detail", slug=season_quest.season.slug)

    if season_quest.quest_mode != SeasonQuest.QuestMode.OPEN:
        messages.error(
            request, "Use the scheduled quest enrollment flow for this quest."
        )
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
        messages.error(
            request, f"Too many submit attempts. Retry in about {retry_after} seconds."
        )
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
        submit_action = (request.POST.get("submit_action") or "submit").strip().lower()
        if submit_action not in {"draft", "submit"}:
            submit_action = "submit"

        if submission and not can_edit_submission:
            messages.error(
                request,
                "This submission has already been scored and can no longer be edited.",
            )
            return redirect("assignment-submit", assignment_id=assignment.id)

        limit = 10
        window_seconds = 60
        allowed, retry_after, current_count = check_rate_limit(
            key=f"submit:{assignment.season_quest.season_id}:{participant.id}",
            limit=limit,
            window_seconds=window_seconds,
        )
        if not allowed:
            messages.error(
                request,
                f"Too many submission attempts. Retry in about {retry_after} seconds.",
            )
            response = redirect("season-detail", slug=season.slug)
            return add_rate_limit_headers(
                response,
                limit=limit,
                window_seconds=window_seconds,
                remaining=0,
                retry_after=retry_after,
            )

    if request.method == "POST":
        form = SubmissionForm(request.POST, request.FILES)
        if form.is_valid():
            media_files = request.FILES.getlist("media_files")
            uploaded_manifest, manifest_errors = _parse_uploaded_media_manifest(
                request.POST.get("uploaded_media_manifest", "")
            )
            text_response = form.cleaned_data["text_response"].strip()
            retained_existing_media: list[tuple[int, SubmissionMedia]] = []
            deleted_existing_media: list[SubmissionMedia] = []
            existing_media_count = 0

            if manifest_errors:
                for error in manifest_errors:
                    messages.error(request, error)
                return render(
                    request,
                    "submissions/form.html",
                    {
                        "form": form,
                        "assignment": assignment,
                        "submission": submission,
                        "can_edit_submission": can_edit_submission,
                        "max_media_files": MAX_MEDIA_FILES_PER_SUBMISSION,
                        "existing_media_count": submission.media_items.count() if submission else 0,
                    },
                )

            try:
                validated_manifest_items, manifest_validation_errors = (
                    _validate_uploaded_manifest_items(
                        uploaded_manifest=uploaded_manifest,
                        assignment=assignment,
                        participant=participant,
                    )
                )
            except StorageConfigurationError:
                messages.error(request, "There was an error validating uploaded media.")
                return render(
                    request,
                    "submissions/form.html",
                    {
                        "form": form,
                        "assignment": assignment,
                        "submission": submission,
                        "can_edit_submission": can_edit_submission,
                        "max_media_files": MAX_MEDIA_FILES_PER_SUBMISSION,
                        "existing_media_count": submission.media_items.count() if submission else 0,
                    },
                )
            if manifest_validation_errors:
                for error in manifest_validation_errors:
                    messages.error(request, error)
                return render(
                    request,
                    "submissions/form.html",
                    {
                        "form": form,
                        "assignment": assignment,
                        "submission": submission,
                        "can_edit_submission": can_edit_submission,
                        "max_media_files": MAX_MEDIA_FILES_PER_SUBMISSION,
                        "existing_media_count": submission.media_items.count() if submission else 0,
                    },
                )

            if submission:
                retained_existing_media, deleted_existing_media, existing_media_errors = (
                    _parse_existing_media_updates(
                        submission=submission,
                        post_data=request.POST,
                    )
                )
                if existing_media_errors:
                    for error in existing_media_errors:
                        messages.error(request, error)
                    return render(
                        request,
                        "submissions/form.html",
                        {
                            "form": form,
                            "assignment": assignment,
                            "submission": submission,
                            "can_edit_submission": can_edit_submission,
                            "max_media_files": MAX_MEDIA_FILES_PER_SUBMISSION,
                            "existing_media_count": submission.media_items.count(),
                        },
                    )
                existing_media_count = len(retained_existing_media)
            else:
                existing_media_count = 0

            total_new_files = len(media_files) + len(validated_manifest_items)
            if existing_media_count + total_new_files > MAX_MEDIA_FILES_PER_SUBMISSION:
                messages.error(
                    request,
                    (
                        f"You can add up to {MAX_MEDIA_FILES_PER_SUBMISSION} media files per submission. "
                        f"This submission already has {existing_media_count} file(s)."
                    ),
                )
                return render(
                    request,
                    "submissions/form.html",
                    {
                        "form": form,
                        "assignment": assignment,
                        "submission": submission,
                        "can_edit_submission": can_edit_submission,
                        "max_media_files": MAX_MEDIA_FILES_PER_SUBMISSION,
                        "existing_media_count": submission.media_items.count() if submission else 0,
                    },
                )

            if (
                not media_files
                and not validated_manifest_items
                and not text_response
                and existing_media_count == 0
            ):
                if submit_action == "draft":
                    messages.error(
                        request,
                        "Add text or at least one media file before saving draft.",
                    )
                else:
                    messages.error(
                        request,
                        "Add text or at least one media file before submitting.",
                    )
                return render(
                    request,
                    "submissions/form.html",
                    {
                        "form": form,
                        "assignment": assignment,
                        "submission": submission,
                        "can_edit_submission": can_edit_submission,
                        "max_media_files": MAX_MEDIA_FILES_PER_SUBMISSION,
                        "existing_media_count": submission.media_items.count() if submission else 0,
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
                        "max_media_files": MAX_MEDIA_FILES_PER_SUBMISSION,
                        "existing_media_count": submission.media_items.count() if submission else 0,
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
                with transaction.atomic():
                    if deleted_existing_media:
                        SubmissionMedia.objects.filter(
                            submission=submission,
                            id__in=[media.id for media in deleted_existing_media],
                        ).delete()

                    ordered_entries: list[tuple[int, str, object]] = []
                    max_explicit_order = 0

                    for desired_order, media in retained_existing_media:
                        ordered_entries.append((desired_order, "existing", media))
                        max_explicit_order = max(max_explicit_order, desired_order)

                    for manifest_item in validated_manifest_items:
                        desired_order = manifest_item.get("sort_order")
                        if desired_order is None:
                            max_explicit_order += 1
                            desired_order = max_explicit_order
                        else:
                            max_explicit_order = max(max_explicit_order, desired_order)
                        ordered_entries.append((desired_order, "manifest", manifest_item))

                    for media_file in media_files:
                        max_explicit_order += 1
                        ordered_entries.append((max_explicit_order, "file", media_file))

                    ordered_entries.sort(
                        key=lambda row: (
                            row[0],
                            0 if row[1] == "existing" else (1 if row[1] == "manifest" else 2),
                        )
                    )

                    existing_media_in_order = [
                        entry[2] for entry in ordered_entries if entry[1] == "existing"
                    ]
                    if existing_media_in_order:
                        for index, media in enumerate(existing_media_in_order):
                            media.sort_order = 10_000 + index
                        SubmissionMedia.objects.bulk_update(existing_media_in_order, ["sort_order"])

                    final_existing_media: list[SubmissionMedia] = []
                    for final_sort_order, (_desired_order, entry_kind, payload) in enumerate(ordered_entries):
                        if entry_kind == "existing":
                            media = payload
                            media.sort_order = final_sort_order
                            final_existing_media.append(media)
                            continue

                        if entry_kind == "manifest":
                            manifest_item = payload
                            SubmissionMedia.objects.create(
                                submission=submission,
                                blob_path_or_url=manifest_item["blob_url"],
                                media_type=manifest_item["media_type"],
                                mime_type=manifest_item["content_type"],
                                file_size_bytes=manifest_item["file_size_bytes"],
                                duration_seconds=manifest_item["duration_seconds"],
                                sort_order=final_sort_order,
                                exif_data=None,
                            )
                            continue

                        media_file = payload
                        media_type = (
                            "video"
                            if media_file.content_type in ALLOWED_VIDEO_MIME_TYPES
                            else "image"
                        )
                        duration_seconds = None
                        if media_type == SubmissionMedia.MediaType.VIDEO:
                            duration_seconds = detect_video_duration_seconds(media_file)

                        # Extract EXIF before stripping so we retain it in the DB.
                        exif_data = (
                            extract_exif_data(media_file)
                            if media_type == "image"
                            else None
                        )

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
                            sort_order=final_sort_order,
                            exif_data=exif_data,
                        )

                    if final_existing_media:
                        SubmissionMedia.objects.bulk_update(final_existing_media, ["sort_order"])
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
                logger.exception(
                    "Submission upload failed due to storage configuration for assignment %s.",
                    assignment.id,
                )
                messages.error(request, "There was an error uploading the media.")
                return render(
                    request,
                    "submissions/form.html",
                    {
                        "form": form,
                        "assignment": assignment,
                        "submission": submission if not created_submission else None,
                        "can_edit_submission": can_edit_submission,
                        "max_media_files": MAX_MEDIA_FILES_PER_SUBMISSION,
                        "existing_media_count": 0 if created_submission else submission.media_items.count(),
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
                logger.exception(
                    "Submission upload failed unexpectedly for assignment %s.",
                    assignment.id,
                )
                messages.error(request, "Upload failed unexpectedly. Please try again.")
                return render(
                    request,
                    "submissions/form.html",
                    {
                        "form": form,
                        "assignment": assignment,
                        "submission": submission if not created_submission else None,
                        "can_edit_submission": can_edit_submission,
                        "max_media_files": MAX_MEDIA_FILES_PER_SUBMISSION,
                        "existing_media_count": 0 if created_submission else submission.media_items.count(),
                    },
                )

            if submit_action == "submit":
                assignment.status = QuestAssignment.Status.SUBMITTED
                assignment.save(update_fields=["status"])
                broadcast_season_event(
                    season_id=assignment.season_quest.season_id,
                    payload={
                        "event": "submission_created",
                        "assignment_id": assignment.id,
                        "season_quest_id": assignment.season_quest_id,
                        "participant_id": assignment.participant_id,
                        "participant_handle": assignment.participant.handle,
                        "quest_title": assignment.season_quest.resolved_title,
                        "scoring_url": f"/seasons/{season.slug}/scoring/",
                    },
                )
                if created_submission:
                    messages.success(request, "Submission received.")
                else:
                    messages.success(
                        request, "Submission updated and submitted for scoring."
                    )
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
        form = SubmissionForm(
            initial={"text_response": submission.text_response} if submission else None
        )

    if submission:
        for media in submission.media_items.all():
            media.signed_url = signed_read_url(media.blob_path_or_url)

    season_quest = assignment.season_quest
    ends_at_iso = (
        season_quest.ends_at.isoformat()
        if season_quest.ends_at
        and season_quest.quest_mode == SeasonQuest.QuestMode.SCHEDULED
        else None
    )

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
            "max_media_files": MAX_MEDIA_FILES_PER_SUBMISSION,
            "existing_media_count": submission.media_items.count() if submission else 0,
        },
    )


def view_assignment(request: HttpRequest, assignment_id: int) -> HttpResponse:
    assignment = get_object_or_404(
        QuestAssignment.objects.select_related(
            "season_quest__season", "season_quest__quest", "participant"
        ),
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
    if season_quest.status in {
        SeasonQuest.Status.COMPLETE,
        SeasonQuest.Status.ARCHIVED,
    }:
        phase = "expired"
    elif season_quest.ends_at and now > season_quest.ends_at:
        if season_quest.allow_late_submissions:
            grace_deadline = season_quest.ends_at + timedelta(
                seconds=season_quest.late_grace_seconds
            )
            phase = "active" if now <= grace_deadline else "expired"
        else:
            phase = "expired"
    elif season_quest.status == SeasonQuest.Status.ACTIVE and season_quest.started_at:
        phase = "active"
    elif (
        season_quest.opens_at
        and now >= season_quest.opens_at
        and season_quest.status == SeasonQuest.Status.ACTIVE
    ):
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
        form = SubmissionForm(
            initial={"text_response": submission.text_response if submission else ""}
        )

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
            "max_media_files": MAX_MEDIA_FILES_PER_SUBMISSION,
            "existing_media_count": submission.media_items.count() if submission else 0,
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
        Submission.objects.filter(
            quest_assignment__season_quest__season=season, is_draft=False
        )
        .select_related(
            "quest_assignment__participant", "quest_assignment__season_quest"
        )
        .prefetch_related("media_items")
        .order_by("score", "-submitted_at")
    )

    submission_ids = [submission.id for submission in submissions]
    score_logs_by_submission: dict[int, list[AuditLog]] = {}
    if submission_ids:
        score_update_logs = (
            AuditLog.objects.filter(
                season=season,
                action_type="submission.score.updated",
                target_type="Submission",
                target_id__in=[str(submission_id) for submission_id in submission_ids],
            )
            .select_related("actor_participant")
            .order_by("-created_at", "-id")
        )
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
            actor_handle = (
                log.actor_participant.handle if log.actor_participant else "Staff"
            )
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

    pending_submissions = [
        submission for submission in submissions if submission.score is None
    ]
    scored_submissions = [
        submission for submission in submissions if submission.score is not None
    ]

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
        Submission.objects.select_related(
            "quest_assignment__season_quest__season", "quest_assignment"
        ),
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
        messages.error(
            request, f"Too many scoring actions. Retry in about {retry_after} seconds."
        )
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
    submission.save(
        update_fields=["score", "judge_note", "scored_at", "scored_by_participant"]
    )

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
            "participant_handle": assignment.participant.handle,
            "participant_id": assignment.participant_id,
            "quest_title": assignment.season_quest.resolved_title,
            "leaderboard_url": f"/seasons/{season.slug}/leaderboard/",
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
                errors.append(
                    f"{media_file.name}: video exceeds 15 second duration limit."
                )
                continue
        else:
            errors.append(f"{media_file.name}: unsupported file type.")

    return errors


def _validate_media_descriptor(
    *,
    file_name: str,
    content_type: str,
    file_size: int,
    duration_seconds: int | None = None,
) -> tuple[str | None, list[str]]:
    errors: list[str] = []
    extension = Path(file_name).suffix.lower()

    if extension in ALLOWED_IMAGE_EXTENSIONS:
        if content_type not in ALLOWED_IMAGE_MIME_TYPES:
            errors.append(f"{file_name}: MIME type mismatch for image file.")
            return None, errors
        if file_size > MAX_IMAGE_SIZE_BYTES:
            errors.append(f"{file_name}: image exceeds 30MB limit.")
            return None, errors
        return SubmissionMedia.MediaType.IMAGE, []

    if extension in ALLOWED_VIDEO_EXTENSIONS:
        if content_type not in ALLOWED_VIDEO_MIME_TYPES:
            errors.append(f"{file_name}: MIME type mismatch for video file.")
            return None, errors
        if file_size > MAX_VIDEO_SIZE_BYTES:
            errors.append(f"{file_name}: video exceeds 100MB limit.")
            return None, errors
        if duration_seconds is None:
            errors.append(f"{file_name}: could not determine video duration.")
            return None, errors
        if duration_seconds > MAX_VIDEO_DURATION_SECONDS:
            errors.append(f"{file_name}: video exceeds 15 second duration limit.")
            return None, errors
        return SubmissionMedia.MediaType.VIDEO, []

    errors.append(f"{file_name}: unsupported file type.")
    return None, errors


def _parse_uploaded_media_manifest(raw_value: str) -> tuple[list[dict], list[str]]:
    if not raw_value:
        return [], []

    try:
        decoded = json.loads(raw_value)
    except json.JSONDecodeError:
        return [], ["Uploaded media metadata was malformed. Please try selecting files again."]

    if not isinstance(decoded, list):
        return [], ["Uploaded media metadata had an invalid format."]

    manifest: list[dict] = []
    errors: list[str] = []
    for index, item in enumerate(decoded):
        if not isinstance(item, dict):
            errors.append(f"Uploaded media entry #{index + 1} is invalid.")
            continue
        ticket = str(item.get("ticket") or "").strip()
        if not ticket:
            errors.append(f"Uploaded media entry #{index + 1} is missing a ticket.")
            continue
        raw_sort_order = item.get("sort_order")
        sort_order: int | None = None
        if raw_sort_order not in (None, ""):
            try:
                sort_order = int(raw_sort_order)
            except (TypeError, ValueError):
                errors.append(f"Uploaded media entry #{index + 1} has an invalid sort order.")
                continue
            if sort_order < 1:
                errors.append(f"Uploaded media entry #{index + 1} has an invalid sort order.")
                continue

        manifest.append({"ticket": ticket, "sort_order": sort_order})

    return manifest, errors


def _parse_existing_media_updates(
    *,
    submission: Submission,
    post_data,
) -> tuple[list[tuple[int, SubmissionMedia]], list[SubmissionMedia], list[str]]:
    existing_media = list(submission.media_items.all())
    media_by_id = {media.id: media for media in existing_media}

    raw_delete_ids = post_data.getlist("delete_media_ids")
    delete_ids: set[int] = set()
    errors: list[str] = []

    for raw_id in raw_delete_ids:
        try:
            media_id = int(raw_id)
        except (TypeError, ValueError):
            errors.append("Invalid media removal request.")
            continue
        if media_id not in media_by_id:
            errors.append("One or more media items could not be matched to this submission.")
            continue
        delete_ids.add(media_id)

    retained_with_order: list[tuple[int, int, SubmissionMedia]] = []
    removed_media: list[SubmissionMedia] = []
    for media in existing_media:
        if media.id in delete_ids:
            removed_media.append(media)
            continue

        raw_order = post_data.get(f"media_order_{media.id}")
        if raw_order in (None, ""):
            desired_order = media.sort_order + 1
        else:
            try:
                desired_order = int(raw_order)
            except (TypeError, ValueError):
                errors.append("Media order must be a number.")
                continue
            if desired_order < 1:
                errors.append("Media order must be 1 or greater.")
                continue

        retained_with_order.append((desired_order, media.id, media))

    retained_media = [(item[0], item[2]) for item in sorted(retained_with_order, key=lambda row: (row[0], row[1]))]
    return retained_media, removed_media, errors


def _validate_uploaded_manifest_items(
    *,
    uploaded_manifest: list[dict],
    assignment: QuestAssignment,
    participant: SeasonParticipant,
) -> tuple[list[dict], list[str]]:
    if not uploaded_manifest:
        return [], []

    validated: list[dict] = []
    errors: list[str] = []
    for item in uploaded_manifest:
        ticket = item["ticket"]
        try:
            payload = signing.loads(
                ticket,
                salt=UPLOAD_TICKET_SALT,
                max_age=UPLOAD_TICKET_TTL_SECONDS,
            )
        except SignatureExpired:
            errors.append("One or more uploads expired. Please re-select your files.")
            continue
        except BadSignature:
            errors.append("One or more uploads could not be verified. Please re-select your files.")
            continue

        if payload.get("assignment_id") != assignment.id:
            errors.append("Uploaded media assignment mismatch. Please re-select your files.")
            continue
        if payload.get("participant_id") != participant.id:
            errors.append("Uploaded media participant mismatch. Please re-select your files.")
            continue

        file_name = str(payload.get("original_name") or "").strip()
        content_type = str(payload.get("content_type") or "").strip().lower()
        expected_size = int(payload.get("file_size_bytes") or 0)
        raw_duration_seconds = payload.get("duration_seconds")
        duration_seconds: int | None = None
        if raw_duration_seconds is not None:
            try:
                duration_seconds = int(raw_duration_seconds)
            except (TypeError, ValueError):
                duration_seconds = None
        media_type = payload.get("media_type")
        blob_url = str(payload.get("blob_url") or "").strip()
        if not file_name or not blob_url or expected_size <= 0:
            errors.append("Uploaded media metadata was incomplete. Please re-select your files.")
            continue

        inferred_media_type, descriptor_errors = _validate_media_descriptor(
            file_name=file_name,
            content_type=content_type,
            file_size=expected_size,
            duration_seconds=duration_seconds,
        )
        if descriptor_errors:
            errors.extend(descriptor_errors)
            continue
        if inferred_media_type != media_type:
            errors.append(f"{file_name}: uploaded media type mismatch.")
            continue

        blob_properties = fetch_blob_properties(blob_url)
        if blob_properties is None:
            errors.append(f"{file_name}: uploaded file was not found in storage.")
            continue

        blob_size = int(blob_properties["size"])
        blob_content_type = (blob_properties["content_type"] or "").lower()
        if blob_size != expected_size:
            errors.append(f"{file_name}: uploaded file size did not match the selected file.")
            continue
        if blob_content_type and blob_content_type != content_type:
            errors.append(f"{file_name}: uploaded file type did not match the selected file.")
            continue

        validated.append(
            {
                "blob_url": blob_url,
                "media_type": inferred_media_type,
                "content_type": content_type,
                "file_size_bytes": blob_size,
                "duration_seconds": duration_seconds if inferred_media_type == SubmissionMedia.MediaType.VIDEO else None,
                "sort_order": item.get("sort_order"),
            }
        )

    return validated, errors


def _resolve_scorer_participant(
    request: HttpRequest, season
) -> SeasonParticipant | None:
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


def _can_score(
    request: HttpRequest, season, participant: SeasonParticipant | None
) -> bool:
    if can_manage_season(request, season):
        return True
    if not participant:
        return False
    return participant.role in {
        SeasonParticipant.Role.HOST,
        SeasonParticipant.Role.ADMIN,
    }


def _submission_timing_error(assignment: QuestAssignment) -> str | None:
    season_quest = assignment.season_quest
    if season_quest.quest_mode != season_quest.QuestMode.SCHEDULED:
        return None

    now = timezone.now()
    if season_quest.started_at and now < season_quest.started_at:
        return "Scheduled quest has not started yet."

    if season_quest.ends_at and now > season_quest.ends_at:
        if season_quest.allow_late_submissions:
            grace_deadline = season_quest.ends_at + timedelta(
                seconds=season_quest.late_grace_seconds
            )
            if now <= grace_deadline:
                return None
        return "Submission window has closed."

    if season_quest.status in {
        season_quest.Status.COMPLETE,
        season_quest.Status.ARCHIVED,
    }:
        return "Submission window has closed."

    return None
