from django.conf import settings as django_settings
from apps.quests.permissions import can_access_control_center
from apps.quests.permissions import manageable_seasons_queryset
from apps.quests.models import QuestAssignment
from apps.quests.models import SeasonQuest
from apps.seasons.models import Season
from apps.seasons.models import SeasonParticipant
from apps.seasons.session import get_bound_participant_ids
from apps.submissions.models import Submission
from django.urls import reverse


def control_center(request):
    can_access = can_access_control_center(request)
    pending_score_count = 0
    pending_score_url = ""

    if can_access:
        manageable_season_ids = list(manageable_seasons_queryset(request).values_list("id", flat=True))
        if manageable_season_ids:
            pending_submissions = Submission.objects.filter(
                quest_assignment__season_quest__season_id__in=manageable_season_ids,
                score__isnull=True,
                is_draft=False,
            ).select_related("quest_assignment__season_quest__season")
            pending_score_count = pending_submissions.count()
            newest_pending = pending_submissions.order_by("-submitted_at").first()
            if newest_pending:
                pending_score_url = reverse(
                    "season-scoring-queue",
                    kwargs={"slug": newest_pending.quest_assignment.season_quest.season.slug},
                )

    active_scheduled_banner = None

    participant_filter_ids = get_bound_participant_ids(request)
    participant_filter = SeasonParticipant.objects.none()
    if participant_filter_ids:
        participant_filter = SeasonParticipant.objects.filter(id__in=participant_filter_ids)

    if request.user.is_authenticated:
        participant_filter = participant_filter | SeasonParticipant.objects.filter(account=request.user)

    active_participant = (
        participant_filter.select_related("season")
        .exclude(season__status=Season.Status.ARCHIVED)
        .order_by("-joined_at", "-id")
        .first()
    )

    if active_participant:
        live_scheduled_quest = (
            SeasonQuest.objects.filter(
                season=active_participant.season,
                quest_mode=SeasonQuest.QuestMode.SCHEDULED,
                status=SeasonQuest.Status.ACTIVE,
            )
            .select_related("season", "quest")
            .order_by("-started_at", "-id")
            .first()
        )
        if live_scheduled_quest:
            assignment = QuestAssignment.objects.filter(
                season_quest=live_scheduled_quest,
                participant=active_participant,
            ).first()
            if assignment:
                banner_url = reverse("assignment-submit", kwargs={"assignment_id": assignment.id})
            else:
                banner_url = reverse("season-detail", kwargs={"slug": active_participant.season.slug})
            active_scheduled_banner = {
                "title": live_scheduled_quest.resolved_title,
                "season_title": active_participant.season.title,
                "url": banner_url,
            }

    return {
        "can_access_control": can_access,
        "control_pending_score_count": pending_score_count,
        "control_pending_score_url": pending_score_url,
        "active_scheduled_banner": active_scheduled_banner,
        "debug": django_settings.DEBUG,
    }
