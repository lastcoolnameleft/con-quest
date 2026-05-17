"""Exhaustive state machine tests for SeasonQuest, QuestAssignment, Season, and ModerationReport."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.moderation.models import ModerationReport
from apps.quests.models import QuestAssignment, SeasonQuest
from apps.seasons.models import Season, SeasonParticipant
from apps.submissions.models import Submission

from .conftest import (
    AccountFactory,
    AuditLogFactory,
    ModerationReportFactory,
    QuestAssignmentFactory,
    QuestFactory,
    SeasonFactory,
    SeasonParticipantFactory,
    SeasonQuestFactory,
    SubmissionFactory,
    bind_participant_session,
)


# ===========================================================================
# SeasonQuest status machine — model-level
# ===========================================================================


class TestSeasonQuestAllowedTransitions:
    """Test allowed_next_statuses() returns exactly the right set."""

    @pytest.mark.django_db
    def test_draft_allows_pending_and_archived(self):
        sq = SeasonQuestFactory(status=SeasonQuest.Status.DRAFT)
        assert sq.allowed_next_statuses() == {
            SeasonQuest.Status.PENDING,
            SeasonQuest.Status.ARCHIVED,
        }

    @pytest.mark.django_db
    def test_pending_allows_active_and_archived(self):
        sq = SeasonQuestFactory(status=SeasonQuest.Status.PENDING)
        assert sq.allowed_next_statuses() == {
            SeasonQuest.Status.ACTIVE,
            SeasonQuest.Status.ARCHIVED,
        }

    @pytest.mark.django_db
    def test_active_allows_complete_and_archived(self):
        sq = SeasonQuestFactory(status=SeasonQuest.Status.ACTIVE)
        assert sq.allowed_next_statuses() == {
            SeasonQuest.Status.COMPLETE,
            SeasonQuest.Status.ARCHIVED,
        }

    @pytest.mark.django_db
    def test_complete_allows_archived_only(self):
        sq = SeasonQuestFactory(status=SeasonQuest.Status.COMPLETE)
        assert sq.allowed_next_statuses() == {SeasonQuest.Status.ARCHIVED}

    @pytest.mark.django_db
    def test_archived_is_terminal(self):
        sq = SeasonQuestFactory(status=SeasonQuest.Status.ARCHIVED)
        assert sq.allowed_next_statuses() == set()


class TestSeasonQuestCanTransitionTo:
    """Test can_transition_to() returns correct bool for every pair."""

    VALID_TRANSITIONS = [
        ("draft", "pending"),
        ("draft", "archived"),
        ("pending", "active"),
        ("pending", "archived"),
        ("active", "complete"),
        ("active", "archived"),
        ("complete", "archived"),
    ]

    INVALID_TRANSITIONS = [
        ("draft", "active"),
        ("draft", "complete"),
        ("pending", "complete"),
        ("pending", "draft"),
        ("active", "pending"),
        ("active", "draft"),
        ("complete", "draft"),
        ("complete", "active"),
        ("complete", "pending"),
        ("archived", "draft"),
        ("archived", "pending"),
        ("archived", "active"),
        ("archived", "complete"),
    ]

    @pytest.mark.django_db
    @pytest.mark.parametrize("from_status,to_status", VALID_TRANSITIONS)
    def test_valid_transition(self, from_status, to_status):
        sq = SeasonQuestFactory(status=from_status)
        assert sq.can_transition_to(to_status) is True

    @pytest.mark.django_db
    @pytest.mark.parametrize("from_status,to_status", INVALID_TRANSITIONS)
    def test_invalid_transition(self, from_status, to_status):
        sq = SeasonQuestFactory(status=from_status)
        assert sq.can_transition_to(to_status) is False


# ===========================================================================
# SeasonQuest status machine — view-level
# ===========================================================================


@pytest.mark.django_db
class TestTransitionSeasonQuestStatusView:
    """Test the transition_season_quest_status view enforces the state machine."""

    def _make_staff_client(self, season, host_participant):
        c = Client()
        c.force_login(host_participant.account)
        bind_participant_session(c, season, host_participant)
        return c

    @pytest.mark.parametrize("from_status,to_status", [
        ("draft", "pending"),
        ("draft", "archived"),
        ("pending", "archived"),
        ("complete", "archived"),
    ])
    @patch("apps.quests.views.broadcast_season_event")
    def test_valid_transitions_succeed(self, mock_broadcast, from_status, to_status, season, host_participant):
        sq = SeasonQuestFactory(season=season, status=from_status)
        client = self._make_staff_client(season, host_participant)
        url = reverse("season-quest-status", args=[sq.id])
        resp = client.post(url, {"status": to_status})
        assert resp.status_code == 302
        sq.refresh_from_db()
        assert sq.status == to_status

    @patch("apps.quests.views.broadcast_season_event")
    def test_valid_transition_pending_to_active_open(self, mock_broadcast, season, host_participant):
        sq = SeasonQuestFactory(season=season, status="pending", quest_mode=SeasonQuest.QuestMode.OPEN)
        client = self._make_staff_client(season, host_participant)
        url = reverse("season-quest-status", args=[sq.id])
        resp = client.post(url, {"status": "active"})
        assert resp.status_code == 302
        sq.refresh_from_db()
        assert sq.status == SeasonQuest.Status.ACTIVE
        # Open quests don't set started_at/ends_at via _activate_quest_window
        assert sq.started_at is None

    @patch("apps.quests.views.broadcast_season_event")
    def test_valid_transition_pending_to_active_scheduled(self, mock_broadcast, season, host_participant):
        sq = SeasonQuestFactory(
            season=season, status="pending",
            quest_mode=SeasonQuest.QuestMode.SCHEDULED,
            duration_seconds=300,
        )
        client = self._make_staff_client(season, host_participant)
        url = reverse("season-quest-status", args=[sq.id])
        resp = client.post(url, {"status": "active"})
        assert resp.status_code == 302
        sq.refresh_from_db()
        assert sq.status == SeasonQuest.Status.ACTIVE
        assert sq.started_at is not None
        assert sq.ends_at is not None
        mock_broadcast.assert_called()

    @patch("apps.quests.views.broadcast_season_event")
    def test_valid_transition_active_to_complete_sets_ends_at(self, mock_broadcast, season, host_participant):
        sq = SeasonQuestFactory(season=season, status="active")
        assert sq.ends_at is None
        client = self._make_staff_client(season, host_participant)
        url = reverse("season-quest-status", args=[sq.id])
        resp = client.post(url, {"status": "complete"})
        assert resp.status_code == 302
        sq.refresh_from_db()
        assert sq.status == SeasonQuest.Status.COMPLETE
        assert sq.ends_at is not None

    @patch("apps.quests.views.broadcast_season_event")
    def test_active_to_complete_preserves_existing_ends_at(self, mock_broadcast, season, host_participant):
        original_ends = timezone.now()
        sq = SeasonQuestFactory(season=season, status="active", ends_at=original_ends)
        client = self._make_staff_client(season, host_participant)
        url = reverse("season-quest-status", args=[sq.id])
        resp = client.post(url, {"status": "complete"})
        assert resp.status_code == 302
        sq.refresh_from_db()
        assert sq.ends_at == original_ends

    @pytest.mark.parametrize("from_status,to_status", [
        ("draft", "active"),
        ("draft", "complete"),
        ("pending", "draft"),
        ("pending", "complete"),
        ("active", "draft"),
        ("active", "pending"),
        ("complete", "draft"),
        ("complete", "active"),
        ("complete", "pending"),
        ("archived", "draft"),
        ("archived", "active"),
    ])
    @patch("apps.quests.views.broadcast_season_event")
    def test_invalid_transitions_rejected(self, mock_broadcast, from_status, to_status, season, host_participant):
        sq = SeasonQuestFactory(season=season, status=from_status)
        client = self._make_staff_client(season, host_participant)
        url = reverse("season-quest-status", args=[sq.id])
        resp = client.post(url, {"status": to_status})
        assert resp.status_code == 302
        sq.refresh_from_db()
        assert sq.status == from_status  # unchanged

    def test_non_admin_rejected(self, season, player_participant):
        sq = SeasonQuestFactory(season=season, status="draft")
        c = Client()
        c.force_login(player_participant.account)
        bind_participant_session(c, season, player_participant)
        url = reverse("season-quest-status", args=[sq.id])
        resp = c.post(url, {"status": "pending"})
        assert resp.status_code == 302
        sq.refresh_from_db()
        assert sq.status == SeasonQuest.Status.DRAFT  # unchanged


# ===========================================================================
# QuestAssignment status machine — view-level
# ===========================================================================


@pytest.mark.django_db
class TestQuestAssignmentStatusMachine:
    """Test assignment status transitions via the actual views."""

    @patch("apps.submissions.views.upload_submission_media", return_value="https://blob/test.jpg")
    @patch("apps.submissions.views.broadcast_season_event")
    def test_submit_transitions_pending_to_submitted(
        self, mock_broadcast, mock_upload, season, host_participant, player_participant
    ):
        sq = SeasonQuestFactory(season=season, status=SeasonQuest.Status.ACTIVE, quest_mode=SeasonQuest.QuestMode.OPEN)
        assignment = QuestAssignmentFactory(
            season_quest=sq, participant=player_participant, status=QuestAssignment.Status.PENDING,
        )
        c = Client()
        c.force_login(player_participant.account)
        bind_participant_session(c, season, player_participant)
        url = reverse("assignment-submit", args=[assignment.id])
        resp = c.post(url, {"text_response": "My proof", "submit_action": "submit"})
        assert resp.status_code == 302
        assignment.refresh_from_db()
        assert assignment.status == QuestAssignment.Status.SUBMITTED

    @patch("apps.submissions.views.upload_submission_media", return_value="https://blob/test.jpg")
    @patch("apps.submissions.views.broadcast_season_event")
    def test_draft_save_keeps_pending(
        self, mock_broadcast, mock_upload, season, host_participant, player_participant
    ):
        sq = SeasonQuestFactory(season=season, status=SeasonQuest.Status.ACTIVE, quest_mode=SeasonQuest.QuestMode.OPEN)
        assignment = QuestAssignmentFactory(
            season_quest=sq, participant=player_participant, status=QuestAssignment.Status.PENDING,
        )
        c = Client()
        c.force_login(player_participant.account)
        bind_participant_session(c, season, player_participant)
        url = reverse("assignment-submit", args=[assignment.id])
        resp = c.post(url, {"text_response": "Draft text", "submit_action": "draft"})
        assert resp.status_code == 302
        assignment.refresh_from_db()
        assert assignment.status == QuestAssignment.Status.PENDING

    @patch("apps.submissions.views.broadcast_season_event")
    def test_score_transitions_submitted_to_scored(self, mock_broadcast, season, host_participant):
        sq = SeasonQuestFactory(season=season, status=SeasonQuest.Status.ACTIVE)
        player = SeasonParticipantFactory(season=season, handle="scorer_target", role=SeasonParticipant.Role.PLAYER)
        assignment = QuestAssignmentFactory(
            season_quest=sq, participant=player, status=QuestAssignment.Status.SUBMITTED,
        )
        submission = SubmissionFactory(quest_assignment=assignment, text_response="proof")
        c = Client()
        c.force_login(host_participant.account)
        bind_participant_session(c, season, host_participant)
        url = reverse("submission-score", args=[submission.id])
        resp = c.post(url, {"score": 4, "judge_note": "Good job"})
        assert resp.status_code == 302
        assignment.refresh_from_db()
        assert assignment.status == QuestAssignment.Status.SCORED
        submission.refresh_from_db()
        assert submission.score == 4

    @patch("apps.submissions.views.broadcast_season_event")
    def test_cannot_score_without_host_role(self, mock_broadcast, season, player_participant):
        sq = SeasonQuestFactory(season=season, status=SeasonQuest.Status.ACTIVE)
        other_player = SeasonParticipantFactory(season=season, handle="other_p", role=SeasonParticipant.Role.PLAYER)
        assignment = QuestAssignmentFactory(
            season_quest=sq, participant=other_player, status=QuestAssignment.Status.SUBMITTED,
        )
        submission = SubmissionFactory(quest_assignment=assignment, text_response="proof")
        c = Client()
        c.force_login(player_participant.account)
        bind_participant_session(c, season, player_participant)
        url = reverse("submission-score", args=[submission.id])
        resp = c.post(url, {"score": 5, "judge_note": "Hacked"})
        assert resp.status_code == 302
        assignment.refresh_from_db()
        assert assignment.status == QuestAssignment.Status.SUBMITTED  # unchanged


# ===========================================================================
# Season status — direct model level
# ===========================================================================


@pytest.mark.django_db
class TestSeasonStatus:
    """Season has no transition helper — status is set directly."""

    @pytest.mark.parametrize("status", ["draft", "active", "closed"])
    def test_create_with_each_status(self, status):
        s = SeasonFactory(status=status)
        assert s.status == status

    def test_edit_season_status(self):
        s = SeasonFactory(status=Season.Status.DRAFT)
        s.status = Season.Status.ACTIVE
        s.save()
        s.refresh_from_db()
        assert s.status == Season.Status.ACTIVE

        s.status = Season.Status.CLOSED
        s.save()
        s.refresh_from_db()
        assert s.status == Season.Status.CLOSED


# ===========================================================================
# ModerationReport status machine
# ===========================================================================


@pytest.mark.django_db
class TestModerationReportStateMachine:
    """Test resolve_report view transitions and side-effects."""

    def _setup(self, season, host_participant, player_participant):
        sq = SeasonQuestFactory(season=season, status=SeasonQuest.Status.ACTIVE)
        assignment = QuestAssignmentFactory(
            season_quest=sq, participant=player_participant, status=QuestAssignment.Status.SUBMITTED,
        )
        submission = SubmissionFactory(quest_assignment=assignment)
        report = ModerationReportFactory(
            reporter_participant=player_participant,
            target_type="Submission",
            target_id=str(submission.id),
            status=ModerationReport.Status.OPEN,
        )
        return report

    def test_resolve_as_dismissed(self, season, host_participant, player_participant):
        report = self._setup(season, host_participant, player_participant)
        c = Client()
        c.force_login(host_participant.account)
        bind_participant_session(c, season, host_participant)
        url = reverse("moderation-report-resolve", args=[report.id])
        resp = c.post(url, {"status": "dismissed", "details": "Not valid"})
        assert resp.status_code == 302
        report.refresh_from_db()
        assert report.status == ModerationReport.Status.DISMISSED
        assert report.resolved_at is not None
        assert AuditLog.objects.filter(
            action_type="moderation.report.resolved",
            target_id=str(report.id),
        ).exists()

    def test_resolve_as_actioned(self, season, host_participant, player_participant):
        report = self._setup(season, host_participant, player_participant)
        c = Client()
        c.force_login(host_participant.account)
        bind_participant_session(c, season, host_participant)
        url = reverse("moderation-report-resolve", args=[report.id])
        resp = c.post(url, {"status": "actioned", "details": "Removed content"})
        assert resp.status_code == 302
        report.refresh_from_db()
        assert report.status == ModerationReport.Status.ACTIONED
        assert report.resolved_at is not None

    def test_non_moderator_cannot_resolve(self, season, host_participant, player_participant):
        report = self._setup(season, host_participant, player_participant)
        c = Client()
        c.force_login(player_participant.account)
        bind_participant_session(c, season, player_participant)
        url = reverse("moderation-report-resolve", args=[report.id])
        resp = c.post(url, {"status": "dismissed", "details": "Trying"})
        assert resp.status_code == 302
        report.refresh_from_db()
        assert report.status == ModerationReport.Status.OPEN  # unchanged
