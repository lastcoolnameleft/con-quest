"""End-to-end submission flow tests exercising the full user journey through views."""

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
    ModerationReportFactory,
    QuestAssignmentFactory,
    QuestFactory,
    SeasonFactory,
    SeasonParticipantFactory,
    SeasonQuestFactory,
    SubmissionFactory,
    bind_participant_session,
)


def _player_client(season, participant):
    """Create a Client logged in and session-bound for the given participant."""
    c = Client()
    c.force_login(participant.account)
    bind_participant_session(c, season, participant)
    return c


def _host_client(season, host_participant):
    c = Client()
    c.force_login(host_participant.account)
    bind_participant_session(c, season, host_participant)
    return c


# ===========================================================================
# Open quest flow
# ===========================================================================


@pytest.mark.django_db
class TestOpenQuestFlow:
    """Player joins → claims open quest → submits → host scores → leaderboard."""

    @patch("apps.submissions.views.upload_submission_media", return_value="https://blob/test.jpg")
    @patch("apps.submissions.views.broadcast_season_event")
    def test_full_open_quest_journey(self, mock_broadcast, mock_upload, season, host_participant):
        # 1. Create player + join season
        player_account = AccountFactory(username="open_player")
        player = SeasonParticipantFactory(
            season=season, account=player_account, handle="open_player", role=SeasonParticipant.Role.PLAYER,
        )
        pc = _player_client(season, player)

        # 2. Create active open quest
        sq = SeasonQuestFactory(
            season=season, status=SeasonQuest.Status.ACTIVE, quest_mode=SeasonQuest.QuestMode.OPEN,
        )

        # 3. Player claims quest (POST to season-quest-submit)
        claim_url = reverse("season-quest-submit", args=[sq.id])
        resp = pc.post(claim_url)
        assert resp.status_code == 302
        assignment = QuestAssignment.objects.get(season_quest=sq, participant=player)
        assert assignment.status == QuestAssignment.Status.PENDING

        # 4. Player submits text proof
        submit_url = reverse("assignment-submit", args=[assignment.id])
        resp = pc.post(submit_url, {"text_response": "Here is my proof!", "submit_action": "submit"})
        assert resp.status_code == 302
        assignment.refresh_from_db()
        assert assignment.status == QuestAssignment.Status.SUBMITTED

        # 5. Host scores submission
        submission = Submission.objects.get(quest_assignment=assignment)
        hc = _host_client(season, host_participant)
        score_url = reverse("submission-score", args=[submission.id])
        resp = hc.post(score_url, {"score": 5, "judge_note": "Perfect!"})
        assert resp.status_code == 302
        assignment.refresh_from_db()
        assert assignment.status == QuestAssignment.Status.SCORED
        submission.refresh_from_db()
        assert submission.score == 5

        # 6. Leaderboard reflects score
        lb_url = reverse("season-leaderboard", args=[season.slug])
        resp = pc.get(lb_url)
        assert resp.status_code == 200
        assert b"open_player" in resp.content


# ===========================================================================
# Scheduled quest flow
# ===========================================================================


@pytest.mark.django_db
class TestScheduledQuestFlow:
    """Admin creates scheduled quest → activates → player enrolls → submits within window."""

    @patch("apps.submissions.views.upload_submission_media", return_value="https://blob/test.jpg")
    @patch("apps.submissions.views.broadcast_season_event")
    @patch("apps.quests.views.broadcast_season_event")
    def test_scheduled_quest_submit_within_window(
        self, mock_quest_broadcast, mock_sub_broadcast, mock_upload, season, host_participant
    ):
        now = timezone.now()
        # Pre-create an already-active scheduled quest with started_at in the past
        sq = SeasonQuestFactory(
            season=season,
            status=SeasonQuest.Status.ACTIVE,
            quest_mode=SeasonQuest.QuestMode.SCHEDULED,
            duration_seconds=3600,
            rsvp_code="RSVP123",
            started_at=now - timezone.timedelta(seconds=10),
            ends_at=now + timezone.timedelta(hours=1),
        )

        # Player enrolls via RSVP
        player_account = AccountFactory(username="scheduled_player")
        player = SeasonParticipantFactory(
            season=season, account=player_account, handle="sched_player", role=SeasonParticipant.Role.PLAYER,
        )
        pc = _player_client(season, player)
        enroll_url = reverse("season-quest-enroll", args=[sq.id])
        resp = pc.post(enroll_url, {"rsvp_code": "RSVP123"})
        assert resp.status_code == 302
        assignment = QuestAssignment.objects.get(season_quest=sq, participant=player)

        # Player submits within window
        submit_url = reverse("assignment-submit", args=[assignment.id])
        resp = pc.post(submit_url, {"text_response": "Scheduled proof", "submit_action": "submit"})
        assert resp.status_code == 302
        assignment.refresh_from_db()
        assert assignment.status == QuestAssignment.Status.SUBMITTED

    @patch("apps.submissions.views.upload_submission_media", return_value="https://blob/test.jpg")
    @patch("apps.submissions.views.broadcast_season_event")
    @patch("apps.quests.views.broadcast_season_event")
    def test_scheduled_quest_reject_after_window(
        self, mock_quest_broadcast, mock_sub_broadcast, mock_upload, season, host_participant
    ):
        sq = SeasonQuestFactory(
            season=season,
            status=SeasonQuest.Status.ACTIVE,
            quest_mode=SeasonQuest.QuestMode.SCHEDULED,
            duration_seconds=60,
            started_at=timezone.now() - timezone.timedelta(hours=2),
            ends_at=timezone.now() - timezone.timedelta(hours=1),
            allow_late_submissions=False,
        )

        player_account = AccountFactory(username="late_player")
        player = SeasonParticipantFactory(
            season=season, account=player_account, handle="late_player", role=SeasonParticipant.Role.PLAYER,
        )
        assignment = QuestAssignmentFactory(
            season_quest=sq, participant=player, status=QuestAssignment.Status.PENDING,
        )
        pc = _player_client(season, player)
        submit_url = reverse("assignment-submit", args=[assignment.id])
        resp = pc.post(submit_url, {"text_response": "Too late!", "submit_action": "submit"})
        assert resp.status_code == 302
        assignment.refresh_from_db()
        assert assignment.status == QuestAssignment.Status.PENDING  # not submitted


# ===========================================================================
# Draft submission flow
# ===========================================================================


@pytest.mark.django_db
class TestDraftSubmissionFlow:
    """Player saves draft → edits → submits final."""

    @patch("apps.submissions.views.upload_submission_media", return_value="https://blob/test.jpg")
    @patch("apps.submissions.views.broadcast_season_event")
    def test_draft_then_submit(self, mock_broadcast, mock_upload, season, host_participant):
        sq = SeasonQuestFactory(season=season, status=SeasonQuest.Status.ACTIVE, quest_mode=SeasonQuest.QuestMode.OPEN)
        player_account = AccountFactory(username="drafter")
        player = SeasonParticipantFactory(
            season=season, account=player_account, handle="drafter", role=SeasonParticipant.Role.PLAYER,
        )
        assignment = QuestAssignmentFactory(
            season_quest=sq, participant=player, status=QuestAssignment.Status.PENDING,
        )
        pc = _player_client(season, player)
        submit_url = reverse("assignment-submit", args=[assignment.id])

        # 1. Save draft
        resp = pc.post(submit_url, {"text_response": "WIP draft", "submit_action": "draft"})
        assert resp.status_code == 302
        assignment.refresh_from_db()
        assert assignment.status == QuestAssignment.Status.PENDING
        submission = Submission.objects.get(quest_assignment=assignment)
        assert submission.is_draft is True

        # 2. Submit final
        resp = pc.post(submit_url, {"text_response": "Final version", "submit_action": "submit"})
        assert resp.status_code == 302
        assignment.refresh_from_db()
        assert assignment.status == QuestAssignment.Status.SUBMITTED
        submission.refresh_from_db()
        assert submission.is_draft is False
        assert submission.text_response == "Final version"


# ===========================================================================
# Moderation flow
# ===========================================================================


@pytest.mark.django_db
class TestModerationFlow:
    """Player submits → another player reports → host resolves."""

    @patch("apps.submissions.views.upload_submission_media", return_value="https://blob/test.jpg")
    @patch("apps.submissions.views.broadcast_season_event")
    def test_report_and_resolve_dismissed(self, mock_broadcast, mock_upload, season, host_participant):
        sq = SeasonQuestFactory(season=season, status=SeasonQuest.Status.ACTIVE, quest_mode=SeasonQuest.QuestMode.OPEN)
        # Player submits
        submitter_account = AccountFactory(username="submitter")
        submitter = SeasonParticipantFactory(
            season=season, account=submitter_account, handle="submitter", role=SeasonParticipant.Role.PLAYER,
        )
        assignment = QuestAssignmentFactory(
            season_quest=sq, participant=submitter, status=QuestAssignment.Status.SUBMITTED,
        )
        submission = SubmissionFactory(quest_assignment=assignment)

        # Reporter reports submission
        reporter_account = AccountFactory(username="reporter")
        reporter = SeasonParticipantFactory(
            season=season, account=reporter_account, handle="reporter", role=SeasonParticipant.Role.PLAYER,
        )
        rc = _player_client(season, reporter)
        report_url = reverse("submission-report", args=[submission.id])
        resp = rc.post(report_url, {"reason": "spam", "details": "Looks like spam"})
        assert resp.status_code == 302
        report = ModerationReport.objects.get(reporter_participant=reporter, target_id=str(submission.id))
        assert report.status == ModerationReport.Status.OPEN

        # Host resolves as dismissed
        hc = _host_client(season, host_participant)
        resolve_url = reverse("moderation-report-resolve", args=[report.id])
        resp = hc.post(resolve_url, {"status": "dismissed", "details": "Not spam"})
        assert resp.status_code == 302
        report.refresh_from_db()
        assert report.status == ModerationReport.Status.DISMISSED
        assert report.resolved_at is not None
        assert AuditLog.objects.filter(action_type="moderation.report.resolved").exists()

    @patch("apps.submissions.views.upload_submission_media", return_value="https://blob/test.jpg")
    @patch("apps.submissions.views.broadcast_season_event")
    def test_report_and_resolve_actioned(self, mock_broadcast, mock_upload, season, host_participant):
        sq = SeasonQuestFactory(season=season, status=SeasonQuest.Status.ACTIVE, quest_mode=SeasonQuest.QuestMode.OPEN)
        submitter_account = AccountFactory(username="submitter2")
        submitter = SeasonParticipantFactory(
            season=season, account=submitter_account, handle="submitter2", role=SeasonParticipant.Role.PLAYER,
        )
        assignment = QuestAssignmentFactory(
            season_quest=sq, participant=submitter, status=QuestAssignment.Status.SUBMITTED,
        )
        submission = SubmissionFactory(quest_assignment=assignment)

        reporter_account = AccountFactory(username="reporter2")
        reporter = SeasonParticipantFactory(
            season=season, account=reporter_account, handle="reporter2", role=SeasonParticipant.Role.PLAYER,
        )
        rc = _player_client(season, reporter)
        report_url = reverse("submission-report", args=[submission.id])
        resp = rc.post(report_url, {"reason": "cheating", "details": "Cheated"})
        assert resp.status_code == 302
        report = ModerationReport.objects.get(reporter_participant=reporter)

        hc = _host_client(season, host_participant)
        resolve_url = reverse("moderation-report-resolve", args=[report.id])
        resp = hc.post(resolve_url, {"status": "actioned", "details": "Removed"})
        assert resp.status_code == 302
        report.refresh_from_db()
        assert report.status == ModerationReport.Status.ACTIONED
        assert report.resolved_at is not None
