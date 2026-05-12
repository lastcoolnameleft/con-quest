from django.test import Client
from django.test import TestCase
from django.urls import reverse

from apps.quests.models import QuestAssignment
from apps.quests.models import Quest
from apps.quests.models import SeasonQuest
from apps.seasons.models import Season
from apps.seasons.models import SeasonParticipant
from apps.submissions.models import Submission


class ControlCenterTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.season = Season.objects.create(title="Control Season", slug="control-season")
        self.host = SeasonParticipant.objects.create(
            season=self.season,
            handle="host",
            role=SeasonParticipant.Role.HOST,
            is_guest=True,
        )
        self.template = Quest.objects.create(title="Template A", description="Desc")
        self.season_quest = SeasonQuest.objects.create(
            season=self.season,
            quest=self.template,
            title_override="Quest A",
            points_max=5,
            quest_mode=SeasonQuest.QuestMode.OPEN,
        )

    def _bind_host_session(self):
        session = self.client.session
        session[f"season_participant_{self.season.id}"] = self.host.id
        session.save()

    def test_non_host_cannot_access_control_dashboard(self):
        response = self.client.get(reverse("control-dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("season-index"))

    def test_host_can_access_control_dashboard(self):
        self._bind_host_session()
        response = self.client.get(reverse("control-dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Control Center")
        self.assertContains(response, self.season.title)

    def test_control_dashboard_shows_pending_score_activity(self):
        self._bind_host_session()
        player = SeasonParticipant.objects.create(
            season=self.season,
            handle="player",
            role=SeasonParticipant.Role.PLAYER,
            is_guest=True,
        )
        assignment = QuestAssignment.objects.create(
            season_quest=self.season_quest,
            participant=player,
            status=QuestAssignment.Status.SUBMITTED,
        )
        Submission.objects.create(quest_assignment=assignment, text_response="pending")

        response = self.client.get(reverse("control-dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Pending scores needing review:")
        self.assertContains(response, "1")
        self.assertContains(response, reverse("season-scoring-queue", kwargs={"slug": self.season.slug}))

    def test_host_can_create_edit_delete_season(self):
        self._bind_host_session()

        create_response = self.client.post(
            reverse("control-season-create"),
            {
                "title": "New Season",
                "slug": "new-season",
                "status": Season.Status.DRAFT,
                "keep_image_exif": "",
                "join_code": "JOIN1234",
                "starts_at": "",
                "ends_at": "",
            },
        )
        self.assertEqual(create_response.status_code, 302)
        created = Season.objects.get(slug="new-season")

        edit_response = self.client.post(
            reverse("control-season-edit", kwargs={"slug": created.slug}),
            {
                "title": "Updated Season",
                "slug": "new-season",
                "status": Season.Status.ACTIVE,
                "keep_image_exif": "on",
                "join_code": "JOIN1234",
                "starts_at": "",
                "ends_at": "",
            },
        )
        self.assertEqual(edit_response.status_code, 302)
        created.refresh_from_db()
        self.assertEqual(created.title, "Updated Season")
        self.assertEqual(created.status, Season.Status.ACTIVE)

        delete_response = self.client.post(reverse("control-season-delete", kwargs={"slug": created.slug}))
        self.assertEqual(delete_response.status_code, 302)
        self.assertFalse(Season.objects.filter(slug="new-season").exists())

    def test_host_can_edit_delete_quest_and_season_quest(self):
        self._bind_host_session()

        edit_template_response = self.client.post(
            reverse("quest-edit", kwargs={"quest_id": self.template.id}),
            {
                "title": "Template B",
                "description": "Updated",
                "default_duration_seconds": 150,
                "default_points_max": 4,
            },
        )
        self.assertEqual(edit_template_response.status_code, 302)
        self.template.refresh_from_db()
        self.assertEqual(self.template.title, "Template B")

        edit_quest_response = self.client.post(
            reverse("season-quest-edit", kwargs={"quest_id": self.season_quest.id}),
            {
                "quest": self.template.id,
                "title_override": "Quest B",
                "description_override": "",
                "quest_mode": SeasonQuest.QuestMode.OPEN,
                "status": SeasonQuest.Status.PENDING,
                "rsvp_code": "",
                "duration_seconds": 120,
                "opens_at": "",
                "closes_at": "",
                "reveal_policy": self.season_quest.reveal_policy,
                "points_max": 5,
                "allow_late_submissions": "",
                "late_grace_seconds": 0,
            },
        )
        self.assertEqual(edit_quest_response.status_code, 302)
        self.season_quest.refresh_from_db()
        self.assertEqual(self.season_quest.title_override, "Quest B")
        self.assertEqual(self.season_quest.status, SeasonQuest.Status.PENDING)

        delete_quest_response = self.client.post(
            reverse("season-quest-delete", kwargs={"quest_id": self.season_quest.id})
        )
        self.assertEqual(delete_quest_response.status_code, 302)
        self.assertFalse(SeasonQuest.objects.filter(id=self.season_quest.id).exists())

        delete_template_response = self.client.post(
            reverse("quest-delete", kwargs={"quest_id": self.template.id})
        )
        self.assertEqual(delete_template_response.status_code, 302)
        self.assertFalse(Quest.objects.filter(id=self.template.id).exists())

    def test_host_can_create_season_quest_when_late_grace_input_omitted(self):
        self._bind_host_session()

        response = self.client.post(
            reverse("season-quest-create", kwargs={"slug": self.season.slug}),
            {
                "quest": self.template.id,
                "title_override": "Friday Opener",
                "description_override": "Snap a photo of your badge.",
                "quest_mode": SeasonQuest.QuestMode.OPEN,
                "rsvp_code": "",
                "duration_seconds": 120,
                "opens_at": "",
                "closes_at": "",
                "reveal_policy": SeasonQuest.RevealPolicy.INSTANT,
                "points_max": 5,
                # Simulates disabled late_grace_seconds input not present in POST.
                "allow_late_submissions": "",
            },
        )

        self.assertEqual(response.status_code, 302)
        created = SeasonQuest.objects.filter(season=self.season, title_override="Friday Opener").first()
        self.assertIsNotNone(created)
        self.assertEqual(created.late_grace_seconds, 0)

    def test_host_cannot_create_duplicate_season_quest_title(self):
        self._bind_host_session()

        existing_count = SeasonQuest.objects.filter(season=self.season).count()
        response = self.client.post(
            reverse("season-quest-create", kwargs={"slug": self.season.slug}),
            {
                "quest": self.template.id,
                "title_override": "Quest A",
                "description_override": "Duplicate title attempt",
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

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "A quest with this title already exists in this season.")
        self.assertEqual(SeasonQuest.objects.filter(season=self.season).count(), existing_count)
