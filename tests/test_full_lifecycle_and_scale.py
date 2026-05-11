from django.contrib.auth import get_user_model
from django.test import Client
from django.test import TestCase
from django.urls import reverse

from apps.quests.models import Quest
from apps.quests.models import QuestAssignment
from apps.quests.models import SeasonQuest
from apps.seasons.models import Season
from apps.seasons.models import SeasonParticipant
from apps.submissions.models import Submission


class FullLifecycleAndScaleTests(TestCase):
    def setUp(self):
        self.host_client = Client()
        user_model = get_user_model()
        self.staff_user = user_model.objects.create_user(
            username="host-admin",
            password="pass",
            is_staff=True,
        )
        self.host_client.force_login(self.staff_user)

    def _bind_participant_session(self, client: Client, season: Season, participant: SeasonParticipant) -> None:
        session = client.session
        session[f"season_participant_{season.id}"] = participant.id
        session.save()

    def _create_season_via_control(self, *, title: str, slug: str, join_code: str) -> Season:
        response = self.host_client.post(
            reverse("control-season-create"),
            {
                "title": title,
                "slug": slug,
                "status": Season.Status.DRAFT,
                "join_code": join_code,
            },
        )
        self.assertEqual(response.status_code, 302)
        return Season.objects.get(slug=slug)

    def _create_quest_template_via_control(self, *, title: str) -> Quest:
        response = self.host_client.post(
            reverse("quest-create"),
            {
                "title": title,
                "description": f"Instructions for {title}",
                "default_duration_seconds": 120,
                "default_points_max": 5,
            },
        )
        self.assertEqual(response.status_code, 302)
        return Quest.objects.get(title=title)

    def _create_season_quest_via_control(self, *, season: Season, quest: Quest, title: str) -> SeasonQuest:
        response = self.host_client.post(
            reverse("season-quest-create", kwargs={"slug": season.slug}),
            {
                "quest": quest.id,
                "title_override": title,
                "description_override": "Text-only challenge",
                "quest_mode": SeasonQuest.QuestMode.OPEN,
                "rsvp_code": "",
                "duration_seconds": 120,
                "opens_at": "",
                "closes_at": "",
                "reveal_policy": SeasonQuest.RevealPolicy.INSTANT,
                "points_max": 5,
                "allow_late_submissions": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        return SeasonQuest.objects.get(season=season, title_override=title)

    def _join_player(self, *, season: Season, handle: str) -> tuple[Client, SeasonParticipant]:
        client = Client()
        response = client.post(
            reverse("season-join-by-code"),
            {
                "join_code": season.join_code,
                "handle": handle,
            },
        )
        self.assertEqual(response.status_code, 302)
        participant = SeasonParticipant.objects.get(season=season, handle=handle)
        return client, participant

    def test_full_controlled_lifecycle_multi_user_to_leaderboard(self):
        season = self._create_season_via_control(
            title="Dragon Con Friday",
            slug="dragoncon-friday",
            join_code="DCF2026",
        )

        host_participant = SeasonParticipant.objects.create(
            season=season,
            handle="Tommy",
            role=SeasonParticipant.Role.HOST,
            account=self.staff_user,
            is_guest=False,
        )
        self._bind_participant_session(self.host_client, season, host_participant)

        quest_template = self._create_quest_template_via_control(title="Badge Photo")
        season_quest = self._create_season_quest_via_control(
            season=season,
            quest=quest_template,
            title="Friday Badge Check-In",
        )
        self.assertEqual(season_quest.status, SeasonQuest.Status.DRAFT)

        publish_response = self.host_client.post(
            reverse("season-quest-status", kwargs={"quest_id": season_quest.id}),
            {"status": SeasonQuest.Status.PENDING},
        )
        self.assertEqual(publish_response.status_code, 302)

        activate_response = self.host_client.post(
            reverse("season-quest-status", kwargs={"quest_id": season_quest.id}),
            {"status": SeasonQuest.Status.ACTIVE},
        )
        self.assertEqual(activate_response.status_code, 302)

        season_quest.refresh_from_db()
        self.assertEqual(season_quest.status, SeasonQuest.Status.ACTIVE)

        players = ["alice", "bob", "carol", "dave"]
        player_clients: dict[str, Client] = {}
        assignments: dict[str, QuestAssignment] = {}

        for handle in players:
            player_client, participant = self._join_player(season=season, handle=handle)
            player_clients[handle] = player_client

            claim_response = player_client.post(
                reverse("season-quest-claim", kwargs={"quest_id": season_quest.id}),
            )
            self.assertEqual(claim_response.status_code, 302)

            assignment = QuestAssignment.objects.get(season_quest=season_quest, participant=participant)
            assignments[handle] = assignment

            submit_response = player_client.post(
                reverse("assignment-submit", kwargs={"assignment_id": assignment.id}),
                {"text_response": f"{handle} completed the challenge"},
            )
            self.assertEqual(submit_response.status_code, 302)

        self.assertEqual(Submission.objects.filter(quest_assignment__season_quest=season_quest).count(), len(players))

        scores = {
            "alice": 3,
            "bob": 5,
            "carol": 4,
            "dave": 1,
        }
        for handle, score in scores.items():
            submission = Submission.objects.get(quest_assignment=assignments[handle])
            score_response = self.host_client.post(
                reverse("submission-score", kwargs={"submission_id": submission.id}),
                {
                    "score": score,
                    "judge_note": f"Scored {handle}",
                    "reason": "",
                },
            )
            self.assertEqual(score_response.status_code, 302)

        complete_response = self.host_client.post(
            reverse("season-quest-status", kwargs={"quest_id": season_quest.id}),
            {"status": SeasonQuest.Status.COMPLETE},
        )
        self.assertEqual(complete_response.status_code, 302)

        season_quest.refresh_from_db()
        self.assertEqual(season_quest.status, SeasonQuest.Status.COMPLETE)

        leaderboard_response = self.host_client.get(reverse("season-leaderboard", kwargs={"slug": season.slug}))
        self.assertEqual(leaderboard_response.status_code, 200)

        leaderboard_rows = leaderboard_response.context["leaderboard"]
        ordered_handles = [row["handle"] for row in leaderboard_rows if row["handle"] in players]
        self.assertEqual(ordered_handles, ["bob", "carol", "alice", "dave"])

        quest_breakdowns = leaderboard_response.context["quest_breakdowns"]
        self.assertEqual(quest_breakdowns[0]["status"], SeasonQuest.Status.COMPLETE)
        breakdown_handles = [entry["handle"] for entry in quest_breakdowns[0]["entries"]]
        self.assertEqual(breakdown_handles, ["bob", "carol", "alice", "dave"])

        scored_statuses = set(
            QuestAssignment.objects.filter(season_quest=season_quest).values_list("status", flat=True)
        )
        self.assertEqual(scored_statuses, {QuestAssignment.Status.SCORED})

    def test_status_transition_guard_blocks_archived_back_to_pending(self):
        season = Season.objects.create(title="Transition Season", slug="transition-season", join_code="TRANS26")
        template = Quest.objects.create(title="Transition Quest", description="Desc")
        season_quest = SeasonQuest.objects.create(
            season=season,
            quest=template,
            title_override="Stateful",
            quest_mode=SeasonQuest.QuestMode.OPEN,
            status=SeasonQuest.Status.ARCHIVED,
        )

        response = self.host_client.post(
            reverse("season-quest-status", kwargs={"quest_id": season_quest.id}),
            {"status": SeasonQuest.Status.PENDING},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        season_quest.refresh_from_db()
        self.assertEqual(season_quest.status, SeasonQuest.Status.ARCHIVED)
        self.assertContains(response, "Invalid status transition")

    def test_season_detail_shows_pending_active_complete_only(self):
        season = Season.objects.create(title="Visibility Season", slug="visibility-season", join_code="VIS2026")
        template = Quest.objects.create(title="Visibility Quest", description="Desc")

        SeasonQuest.objects.create(
            season=season,
            quest=template,
            title_override="Draft Hidden",
            status=SeasonQuest.Status.DRAFT,
            quest_mode=SeasonQuest.QuestMode.OPEN,
        )
        SeasonQuest.objects.create(
            season=season,
            quest=template,
            title_override="Pending Visible",
            status=SeasonQuest.Status.PENDING,
            quest_mode=SeasonQuest.QuestMode.OPEN,
        )
        SeasonQuest.objects.create(
            season=season,
            quest=template,
            title_override="Active Visible",
            status=SeasonQuest.Status.ACTIVE,
            quest_mode=SeasonQuest.QuestMode.OPEN,
        )
        SeasonQuest.objects.create(
            season=season,
            quest=template,
            title_override="Complete Visible",
            status=SeasonQuest.Status.COMPLETE,
            quest_mode=SeasonQuest.QuestMode.OPEN,
        )
        SeasonQuest.objects.create(
            season=season,
            quest=template,
            title_override="Archived Hidden",
            status=SeasonQuest.Status.ARCHIVED,
            quest_mode=SeasonQuest.QuestMode.OPEN,
        )

        response = self.host_client.get(reverse("season-detail", kwargs={"slug": season.slug}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Pending Visible")
        self.assertContains(response, "Active Visible")
        self.assertContains(response, "Complete Visible")
        self.assertNotContains(response, "Draft Hidden")
        self.assertNotContains(response, "Archived Hidden")

    def test_leaderboard_scale_with_many_participants(self):
        season = Season.objects.create(title="Scale Season", slug="scale-season", join_code="SCALE26")
        template = Quest.objects.create(title="Scale Quest", description="Desc")
        season_quest = SeasonQuest.objects.create(
            season=season,
            quest=template,
            title_override="Mass Participation",
            status=SeasonQuest.Status.COMPLETE,
            quest_mode=SeasonQuest.QuestMode.OPEN,
        )

        participants_count = 40
        for idx in range(participants_count):
            participant = SeasonParticipant.objects.create(
                season=season,
                handle=f"player-{idx:02d}",
                role=SeasonParticipant.Role.PLAYER,
                is_guest=True,
            )
            assignment = QuestAssignment.objects.create(
                season_quest=season_quest,
                participant=participant,
                status=QuestAssignment.Status.SCORED,
            )
            Submission.objects.create(
                quest_assignment=assignment,
                text_response="done",
                score=idx % 6,
            )

        response = self.host_client.get(reverse("season-leaderboard", kwargs={"slug": season.slug}))
        self.assertEqual(response.status_code, 200)

        leaderboard_rows = response.context["leaderboard"]
        self.assertEqual(len(leaderboard_rows), participants_count)
        self.assertEqual(leaderboard_rows[0]["total_score"], 5)
        self.assertEqual(leaderboard_rows[-1]["total_score"], 0)

        breakdown = response.context["quest_breakdowns"][0]
        self.assertEqual(len(breakdown["entries"]), participants_count)
