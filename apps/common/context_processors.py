from apps.quests.permissions import can_access_control_center
from apps.quests.permissions import manageable_seasons_queryset
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

    return {
        "can_access_control": can_access,
        "control_pending_score_count": pending_score_count,
        "control_pending_score_url": pending_score_url,
    }
