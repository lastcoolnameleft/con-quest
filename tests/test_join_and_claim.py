from django.contrib.auth import get_user_model
from django.test import Client
from django.test import TestCase
from django.urls import reverse

from apps.seasons.models import Season
from apps.seasons.models import SeasonParticipant


class JoinAndClaimTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.season = Season.objects.create(
            title="DragonCon 2026",
            slug="dragoncon-2026",
            join_code="ABC123",
        )

    def test_join_requires_matching_code(self):
        response = self.client.post(
            reverse("season-join", kwargs={"slug": self.season.slug}),
            {"handle": "player1", "join_code": "WRONG"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(SeasonParticipant.objects.filter(season=self.season, handle="player1").exists())

    def test_join_from_index_resolves_season_by_code(self):
        response = self.client.post(
            reverse("season-join-by-code"),
            {"handle": "player-index", "join_code": self.season.join_code},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("season-detail", kwargs={"slug": self.season.slug}))
        self.assertTrue(SeasonParticipant.objects.filter(season=self.season, handle="player-index").exists())

    def test_index_prefills_room_code_from_query_string(self):
        response = self.client.get(reverse("season-index"), {"code": "abc123"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["join_form"].initial["join_code"], "ABC123")

    def test_join_then_claim_with_authenticated_account(self):
        self.client.post(
            reverse("season-join", kwargs={"slug": self.season.slug}),
            {"handle": "player2", "join_code": self.season.join_code},
        )
        participant = SeasonParticipant.objects.get(season=self.season, handle="player2")

        user_model = get_user_model()
        user = user_model.objects.create_user(username="alice", password="p@ssword123")
        self.client.login(username="alice", password="p@ssword123")

        session = self.client.session
        session[f"season_participant_{self.season.id}"] = participant.id
        session.save()

        response = self.client.post(reverse("season-claim", kwargs={"slug": self.season.slug}))
        self.assertEqual(response.status_code, 302)

        participant.refresh_from_db()
        self.assertEqual(participant.account_id, user.id)
        self.assertFalse(participant.is_guest)
