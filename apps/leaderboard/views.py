from django.db.models import Sum
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render

from apps.quests.models import QuestAssignment
from apps.quests.models import SeasonQuest
from apps.seasons.models import Season
from apps.seasons.models import SeasonParticipant


def season_leaderboard(request: HttpRequest, slug: str) -> HttpResponse:
    season = get_object_or_404(Season, slug=slug)

    # Overall leaderboard — total score per participant.
    rows = (
        SeasonParticipant.objects.filter(season=season)
        .annotate(total_score=Sum("quest_assignments__submission__score"))
        .order_by("-total_score", "handle")
    )

    leaderboard = []
    rank = 1
    for participant in rows:
        leaderboard.append(
            {
                "rank": rank,
                "handle": participant.handle,
                "role": participant.role,
                "total_score": participant.total_score or 0,
            }
        )
        rank += 1

    # Per-quest breakdowns — participants who have an assignment, sorted by score.
    quests = (
        SeasonQuest.objects.filter(season=season)
        .select_related("quest")
        .order_by("-created_at", "-id")
    )

    assignments = (
        QuestAssignment.objects.filter(season_quest__season=season)
        .select_related("participant", "submission", "season_quest")
        .order_by("-season_quest__created_at", "-season_quest__id", "-submission__score", "participant__handle")
    )

    # Group by season_quest id.
    from collections import defaultdict
    by_quest: dict = defaultdict(list)
    for assignment in assignments:
        by_quest[assignment.season_quest_id].append(assignment)

    quest_breakdowns = []
    for sq in quests:
        entries_raw = by_quest.get(sq.id, [])
        entries = []
        quest_rank = 1
        for a in sorted(
            entries_raw,
            key=lambda x: (-(x.submission.score or 0) if hasattr(x, "submission") and x.submission else 0, x.participant.handle),
        ):
            score = None
            if hasattr(a, "submission") and a.submission:
                score = a.submission.score
            entries.append(
                {
                    "rank": quest_rank,
                    "handle": a.participant.handle,
                    "status": a.status,
                    "score": score,
                }
            )
            quest_rank += 1

        quest_breakdowns.append(
            {
                "title": sq.resolved_title,
                "status": sq.status,
                "entries": entries,
            }
        )

    return render(
        request,
        "leaderboard/season_leaderboard.html",
        {
            "season": season,
            "leaderboard": leaderboard,
            "quest_breakdowns": quest_breakdowns,
        },
    )
