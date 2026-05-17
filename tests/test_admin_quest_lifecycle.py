"""Admin managing a SeasonQuest through the complete lifecycle."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.quests.models import QuestAssignment, SeasonQuest
from apps.seasons.models import SeasonParticipant
from apps.submissions.models import Submission

from .conftest import (
    AccountFactory,
    QuestAssignmentFactory,
    QuestFactory,
    SeasonFactory,
    SeasonParticipantFactory,
    SeasonQuestFactory,
    SubmissionFactory,
    bind_participant_session,
)


def _admin_client(season, host_participant):
    c = Client()
    c.force_login(host_participant.account)
    bind_participant_session(c, season, host_participant)
    return c


def _transition(client, sq_id, target_status):
    url = reverse("season-quest-status", args=[sq_id])
    return client.post(url, {"status": target_status})


# ===========================================================================
# Open quest lifecycle
# ===========================================================================


@pytest.mark.django_db
class TestOpenQuestLifecycle:

    @patch("apps.quests.views.broadcast_season_event")
    @patch("apps.submissions.views.broadcast_season_event")
    @patch("apps.submissions.views.upload_submission_media", return_value="https://blob/test.jpg")
    def test_full_open_lifecycle(
        self, mock_upload, mock_sub_broadcast, mock_quest_broadcast, season, host_participant
    ):
        ac = _admin_client(season, host_participant)

        # 1. Create quest template + season quest (draft)
        quest = QuestFactory()
        sq = SeasonQuestFactory(
            season=season, quest=quest, status=SeasonQuest.Status.DRAFT,
            quest_mode=SeasonQuest.QuestMode.OPEN,
        )

        # 2. draft → pending
        resp = _transition(ac, sq.id, "pending")
        assert resp.status_code == 302
        sq.refresh_from_db()
        assert sq.status == SeasonQuest.Status.PENDING

        # 3. pending → active (open mode — no started_at/ends_at)
        resp = _transition(ac, sq.id, "active")
        assert resp.status_code == 302
        sq.refresh_from_db()
        assert sq.status == SeasonQuest.Status.ACTIVE
        assert sq.started_at is None

        # 4. Player submits during active
        player_account = AccountFactory(username="lifecycle_player")
        player = SeasonParticipantFactory(
            season=season, account=player_account, handle="lc_player", role=SeasonParticipant.Role.PLAYER,
        )
        assignment = QuestAssignmentFactory(
            season_quest=sq, participant=player, status=QuestAssignment.Status.PENDING,
        )
        pc = Client()
        pc.force_login(player_account)
        bind_participant_session(pc, season, player)
        submit_url = reverse("assignment-submit", args=[assignment.id])
        resp = pc.post(submit_url, {"text_response": "Proof!", "submit_action": "submit"})
        assert resp.status_code == 302
        assignment.refresh_from_db()
        assert assignment.status == QuestAssignment.Status.SUBMITTED

        # 5. active → complete (ends_at set)
        resp = _transition(ac, sq.id, "complete")
        assert resp.status_code == 302
        sq.refresh_from_db()
        assert sq.status == SeasonQuest.Status.COMPLETE
        assert sq.ends_at is not None

        # 6. complete → archived
        resp = _transition(ac, sq.id, "archived")
        assert resp.status_code == 302
        sq.refresh_from_db()
        assert sq.status == SeasonQuest.Status.ARCHIVED


# ===========================================================================
# Scheduled quest lifecycle
# ===========================================================================


@pytest.mark.django_db
class TestScheduledQuestLifecycle:

    @patch("apps.quests.views.broadcast_season_event")
    @patch("apps.submissions.views.broadcast_season_event")
    @patch("apps.submissions.views.upload_submission_media", return_value="https://blob/test.jpg")
    def test_full_scheduled_lifecycle(
        self, mock_upload, mock_sub_broadcast, mock_quest_broadcast, season, host_participant
    ):
        ac = _admin_client(season, host_participant)
        now = timezone.now()

        sq = SeasonQuestFactory(
            season=season,
            status=SeasonQuest.Status.DRAFT,
            quest_mode=SeasonQuest.QuestMode.SCHEDULED,
            duration_seconds=3600,
            opens_at=now,
            closes_at=now + timezone.timedelta(hours=2),
        )

        # draft → pending
        resp = _transition(ac, sq.id, "pending")
        assert resp.status_code == 302
        sq.refresh_from_db()
        assert sq.status == SeasonQuest.Status.PENDING

        # pending → active (scheduled: _activate_quest_window sets started_at/ends_at)
        resp = _transition(ac, sq.id, "active")
        assert resp.status_code == 302
        sq.refresh_from_db()
        assert sq.status == SeasonQuest.Status.ACTIVE
        assert sq.started_at is not None
        assert sq.ends_at is not None

        # Move started_at to the past so submission timing check passes
        # (_activate_quest_window sets started_at = now + 2s fairness buffer)
        sq.refresh_from_db()
        sq.started_at = timezone.now() - timezone.timedelta(seconds=5)
        sq.ends_at = timezone.now() + timezone.timedelta(hours=1)
        sq.save(update_fields=["started_at", "ends_at"])

        # Player submits within window
        player_account = AccountFactory(username="sched_lc_player")
        player = SeasonParticipantFactory(
            season=season, account=player_account, handle="slc_player", role=SeasonParticipant.Role.PLAYER,
        )
        assignment = QuestAssignmentFactory(
            season_quest=sq, participant=player, status=QuestAssignment.Status.PENDING,
        )
        pc = Client()
        pc.force_login(player_account)
        bind_participant_session(pc, season, player)
        submit_url = reverse("assignment-submit", args=[assignment.id])
        resp = pc.post(submit_url, {"text_response": "In time", "submit_action": "submit"})
        assert resp.status_code == 302
        assignment.refresh_from_db()
        assert assignment.status == QuestAssignment.Status.SUBMITTED

        # active → complete
        resp = _transition(ac, sq.id, "complete")
        assert resp.status_code == 302
        sq.refresh_from_db()
        assert sq.status == SeasonQuest.Status.COMPLETE

        # complete → archived
        resp = _transition(ac, sq.id, "archived")
        assert resp.status_code == 302
        sq.refresh_from_db()
        assert sq.status == SeasonQuest.Status.ARCHIVED


# ===========================================================================
# Early archive paths
# ===========================================================================


@pytest.mark.django_db
class TestEarlyArchivePaths:

    @patch("apps.quests.views.broadcast_season_event")
    @pytest.mark.parametrize("start_status", ["draft", "pending", "active"])
    def test_early_archive(self, mock_broadcast, start_status, season, host_participant):
        sq = SeasonQuestFactory(season=season, status=start_status)
        ac = _admin_client(season, host_participant)
        resp = _transition(ac, sq.id, "archived")
        assert resp.status_code == 302
        sq.refresh_from_db()
        assert sq.status == SeasonQuest.Status.ARCHIVED


# ===========================================================================
# Invalid transition attempts
# ===========================================================================


@pytest.mark.django_db
class TestInvalidTransitions:
    """Every backward/skip transition should fail."""

    BACKWARD_TRANSITIONS = [
        ("pending", "draft"),
        ("active", "draft"),
        ("active", "pending"),
        ("complete", "draft"),
        ("complete", "pending"),
        ("complete", "active"),
        ("archived", "draft"),
        ("archived", "pending"),
        ("archived", "active"),
        ("archived", "complete"),
    ]

    SKIP_TRANSITIONS = [
        ("draft", "active"),
        ("draft", "complete"),
        ("pending", "complete"),
    ]

    @patch("apps.quests.views.broadcast_season_event")
    @pytest.mark.parametrize("from_status,to_status", BACKWARD_TRANSITIONS + SKIP_TRANSITIONS)
    def test_invalid_transition_rejected(self, mock_broadcast, from_status, to_status, season, host_participant):
        sq = SeasonQuestFactory(season=season, status=from_status)
        ac = _admin_client(season, host_participant)
        resp = _transition(ac, sq.id, to_status)
        assert resp.status_code == 302
        sq.refresh_from_db()
        assert sq.status == from_status  # status unchanged
