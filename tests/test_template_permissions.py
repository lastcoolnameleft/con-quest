from django.test import Client
from django.test import TestCase
from django.urls import reverse

from apps.seasons.models import Season
from apps.seasons.models import SeasonParticipant


class QuestPermissionTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.season = Season.objects.create(title="Perm Season", slug="perm-season")

    def test_index_hides_new_quest_button_for_non_host(self):
        response = self.client.get(reverse("season-index"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "New Quest")

    def test_quest_create_rejects_non_host(self):
        response = self.client.get(reverse("quest-create"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("season-index"))

    def test_host_can_open_create_form_without_index_button(self):
        host = SeasonParticipant.objects.create(
            season=self.season,
            handle="host",
            role=SeasonParticipant.Role.HOST,
            is_guest=True,
        )

        session = self.client.session
        session[f"season_participant_{self.season.id}"] = host.id
        session.save()

        index_response = self.client.get(reverse("season-index"))
        self.assertEqual(index_response.status_code, 200)
        self.assertNotContains(index_response, "New Quest")
        self.assertContains(index_response, "Control Center")

        create_response = self.client.get(reverse("quest-create"))
        self.assertEqual(create_response.status_code, 200)
