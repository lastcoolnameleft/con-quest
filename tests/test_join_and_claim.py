from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client
from django.test import TestCase
from django.urls import reverse

from apps.realtime.presence import register_quest_viewer_connection
from apps.seasons.models import Season
from apps.seasons.models import SeasonParticipant
from apps.quests.models import Quest
from apps.quests.models import SeasonQuest
from apps.quests.models import QuestAssignment


class JoinAndClaimTests(TestCase):
    def setUp(self):
        cache.clear()
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

    def test_valid_room_code_allows_many_players_from_same_network(self):
        for i in range(8):
            response = self.client.post(
                reverse("season-join-by-code"),
                {"handle": f"shared-wifi-{i}", "join_code": self.season.join_code},
            )
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response.url, reverse("season-detail", kwargs={"slug": self.season.slug}))

        self.assertEqual(
            SeasonParticipant.objects.filter(
                season=self.season,
                handle__startswith="shared-wifi-",
            ).count(),
            8,
        )

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

    def test_index_shows_joined_season_and_quest_status(self):
        participant = SeasonParticipant.objects.create(
            season=self.season,
            handle="player3",
            role=SeasonParticipant.Role.PLAYER,
            is_guest=True,
        )
        quest_template = Quest.objects.create(title="Photo Quest", description="Take a photo")
        season_quest = SeasonQuest.objects.create(
            season=self.season,
            quest=quest_template,
            title_override="Lobby Photo",
            quest_mode=SeasonQuest.QuestMode.OPEN,
            status=SeasonQuest.Status.ACTIVE,
        )
        QuestAssignment.objects.create(
            season_quest=season_quest,
            participant=participant,
            status=QuestAssignment.Status.PENDING,
        )

        session = self.client.session
        session[f"season_participant_{self.season.id}"] = participant.id
        session.save()

        response = self.client.get(reverse("season-index"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            reverse("season-detail", kwargs={"slug": self.season.slug}),
        )

    def test_index_shows_both_available_and_pending_quests(self):
        participant = SeasonParticipant.objects.create(
            season=self.season,
            handle="player4",
            role=SeasonParticipant.Role.PLAYER,
            is_guest=True,
        )
        quest_template = Quest.objects.create(title="Active Quest", description="Go")
        SeasonQuest.objects.create(
            season=self.season,
            quest=quest_template,
            title_override="Do Something",
            quest_mode=SeasonQuest.QuestMode.OPEN,
            status=SeasonQuest.Status.ACTIVE,
        )
        quest_template2 = Quest.objects.create(title="Pending Quest", description="Wait")
        SeasonQuest.objects.create(
            season=self.season,
            quest=quest_template2,
            title_override="Coming Up",
            quest_mode=SeasonQuest.QuestMode.OPEN,
            status=SeasonQuest.Status.PENDING,
        )

        session = self.client.session
        session[f"season_participant_{self.season.id}"] = participant.id
        session.save()

        response = self.client.get(reverse("season-index"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            reverse("season-detail", kwargs={"slug": self.season.slug}),
        )

    def test_archived_season_hidden_on_index_but_still_accessible_directly(self):
        participant = SeasonParticipant.objects.create(
            season=self.season,
            handle="archived-player",
            role=SeasonParticipant.Role.PLAYER,
            is_guest=True,
        )
        self.season.status = Season.Status.ARCHIVED
        self.season.save(update_fields=["status", "updated_at"])

        session = self.client.session
        session[f"season_participant_{self.season.id}"] = participant.id
        session.save()

        index_response = self.client.get(reverse("season-index"))
        self.assertEqual(index_response.status_code, 200)
        self.assertNotContains(index_response, self.season.title)

        detail_response = self.client.get(reverse("season-detail", kwargs={"slug": self.season.slug}))
        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(detail_response, self.season.title)

    def test_claimed_account_can_open_assignment_submit_without_session_binding(self):
        user_model = get_user_model()
        user = user_model.objects.create_user(username="claimedplayer", password="p@ssword123")
        participant = SeasonParticipant.objects.create(
            season=self.season,
            handle="claimed-player",
            role=SeasonParticipant.Role.PLAYER,
            account=user,
            is_guest=False,
        )
        quest_template = Quest.objects.create(title="Claimed Quest", description="Desc")
        season_quest = SeasonQuest.objects.create(
            season=self.season,
            quest=quest_template,
            title_override="Claimed Assignment",
            quest_mode=SeasonQuest.QuestMode.OPEN,
            status=SeasonQuest.Status.ACTIVE,
        )
        assignment = QuestAssignment.objects.create(
            season_quest=season_quest,
            participant=participant,
            status=QuestAssignment.Status.PENDING,
        )

        self.client.login(username="claimedplayer", password="p@ssword123")
        session = self.client.session
        session.pop(f"season_participant_{self.season.id}", None)
        session.save()

        response = self.client.get(reverse("assignment-submit", kwargs={"assignment_id": assignment.id}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Submit Quest Response")

    def test_season_detail_shows_already_submitted_notification(self):
        participant = SeasonParticipant.objects.create(
            season=self.season,
            handle="submitted-player",
            role=SeasonParticipant.Role.PLAYER,
            is_guest=True,
        )
        quest_template = Quest.objects.create(title="Submitted Quest", description="Desc")
        season_quest = SeasonQuest.objects.create(
            season=self.season,
            quest=quest_template,
            title_override="Submitted Assignment",
            quest_mode=SeasonQuest.QuestMode.OPEN,
            status=SeasonQuest.Status.ACTIVE,
        )
        QuestAssignment.objects.create(
            season_quest=season_quest,
            participant=participant,
            status=QuestAssignment.Status.SUBMITTED,
        )

        session = self.client.session
        session[f"season_participant_{self.season.id}"] = participant.id
        session.save()

        response = self.client.get(reverse("season-detail", kwargs={"slug": self.season.slug}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Submitted")

    def test_season_detail_recovers_claimed_participant_without_session(self):
        user_model = get_user_model()
        user = user_model.objects.create_user(username="notifplayer", password="p@ssword123")
        participant = SeasonParticipant.objects.create(
            season=self.season,
            handle="notif-player",
            role=SeasonParticipant.Role.PLAYER,
            account=user,
            is_guest=False,
        )
        quest_template = Quest.objects.create(title="Recovered Quest", description="Desc")
        season_quest = SeasonQuest.objects.create(
            season=self.season,
            quest=quest_template,
            title_override="Recovered Assignment",
            quest_mode=SeasonQuest.QuestMode.OPEN,
            status=SeasonQuest.Status.ACTIVE,
        )
        QuestAssignment.objects.create(
            season_quest=season_quest,
            participant=participant,
            status=QuestAssignment.Status.SUBMITTED,
        )

        self.client.login(username="notifplayer", password="p@ssword123")
        session = self.client.session
        session.pop(f"season_participant_{self.season.id}", None)
        session.save()

        response = self.client.get(reverse("season-detail", kwargs={"slug": self.season.slug}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "notif-player")

    def test_season_detail_uses_single_join_flow(self):
        response = self.client.get(reverse("season-detail", kwargs={"slug": self.season.slug}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Join this game")
        self.assertNotContains(response, "action=\"/seasons/dragoncon-2026/join/\"")

    def test_season_detail_shows_online_viewer_count_for_quest(self):
        participant = SeasonParticipant.objects.create(
            season=self.season,
            handle="viewer-player",
            role=SeasonParticipant.Role.PLAYER,
            is_guest=True,
        )
        quest_template = Quest.objects.create(title="Live Quest", description="Desc")
        season_quest = SeasonQuest.objects.create(
            season=self.season,
            quest=quest_template,
            title_override="Live Assignment",
            quest_mode=SeasonQuest.QuestMode.OPEN,
            status=SeasonQuest.Status.ACTIVE,
        )
        QuestAssignment.objects.create(
            season_quest=season_quest,
            participant=participant,
            status=QuestAssignment.Status.PENDING,
        )
        register_quest_viewer_connection(
            season_id=self.season.id,
            quest_id=season_quest.id,
            participant_id=participant.id,
            connection_id="presence-test-1",
        )

        session = self.client.session
        session[f"season_participant_{self.season.id}"] = participant.id
        session.save()
        response = self.client.get(reverse("season-detail", kwargs={"slug": self.season.slug}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "online now")

    def test_live_scheduled_quest_banner_links_to_assignment(self):
        participant = SeasonParticipant.objects.create(
            season=self.season,
            handle="scheduled-player",
            role=SeasonParticipant.Role.PLAYER,
            is_guest=True,
        )
        quest_template = Quest.objects.create(title="Scheduled Quest", description="Desc")
        season_quest = SeasonQuest.objects.create(
            season=self.season,
            quest=quest_template,
            title_override="Room Challenge",
            quest_mode=SeasonQuest.QuestMode.SCHEDULED,
            status=SeasonQuest.Status.ACTIVE,
        )
        assignment = QuestAssignment.objects.create(
            season_quest=season_quest,
            participant=participant,
            status=QuestAssignment.Status.PENDING,
        )

        session = self.client.session
        session[f"season_participant_{self.season.id}"] = participant.id
        session.save()

        response = self.client.get(
            reverse("season-detail", kwargs={"slug": self.season.slug})
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Live scheduled quest:")
        self.assertContains(response, "Room Challenge")
        self.assertContains(
            response,
            reverse("assignment-submit", kwargs={"assignment_id": assignment.id}),
        )
