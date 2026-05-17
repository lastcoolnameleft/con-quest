"""Shared test infrastructure: factory-boy factories and pytest fixtures."""

from __future__ import annotations

import factory
import pytest
from django.core.cache import cache
from django.test import Client
from django.utils import timezone

from apps.accounts.models import Account
from apps.audit.models import AuditLog
from apps.moderation.models import ModerationReport
from apps.quests.models import Quest, QuestAssignment, SeasonQuest
from apps.seasons.models import Season, SeasonParticipant
from apps.submissions.models import Submission, SubmissionMedia


# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------


class AccountFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Account

    username = factory.Sequence(lambda n: f"user{n}")
    email = factory.LazyAttribute(lambda o: f"{o.username}@example.com")
    password = factory.PostGenerationMethodCall("set_password", "testpass123")
    provider = Account.Provider.LOCAL
    provider_user_id = ""


class SeasonFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Season

    title = factory.Sequence(lambda n: f"Season {n}")
    slug = factory.Sequence(lambda n: f"season-{n}")
    status = Season.Status.DRAFT
    join_code = factory.LazyFunction(lambda: "TESTCODE")
    timezone = "UTC"


class SeasonParticipantFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = SeasonParticipant

    season = factory.SubFactory(SeasonFactory)
    account = factory.SubFactory(AccountFactory)
    handle = factory.Sequence(lambda n: f"player{n}")
    role = SeasonParticipant.Role.PLAYER
    is_guest = False


class QuestFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Quest

    title = factory.Sequence(lambda n: f"Quest {n}")
    description = "A test quest description."
    default_duration_seconds = 120
    default_points_max = 5
    is_active = True


class SeasonQuestFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = SeasonQuest

    season = factory.SubFactory(SeasonFactory)
    quest = factory.SubFactory(QuestFactory)
    title_override = ""
    status = SeasonQuest.Status.DRAFT
    quest_mode = SeasonQuest.QuestMode.OPEN
    assignment_policy = SeasonQuest.AssignmentPolicy.OPEN_CLAIM
    duration_seconds = 120
    points_max = 5
    reveal_policy = SeasonQuest.RevealPolicy.INSTANT
    allow_late_submissions = False
    late_grace_seconds = 0


class QuestAssignmentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = QuestAssignment

    season_quest = factory.SubFactory(SeasonQuestFactory)
    participant = factory.SubFactory(SeasonParticipantFactory)
    status = QuestAssignment.Status.PENDING
    assignment_source = QuestAssignment.Source.OPEN_CLAIM


class SubmissionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Submission

    quest_assignment = factory.SubFactory(QuestAssignmentFactory)
    text_response = "Test submission text."
    is_draft = False
    is_late = False
    score = None
    judge_note = ""
    scored_at = None
    scored_by_participant = None


class SubmissionMediaFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = SubmissionMedia

    submission = factory.SubFactory(SubmissionFactory)
    blob_path_or_url = "https://example.com/media/test.jpg"
    media_type = SubmissionMedia.MediaType.IMAGE
    mime_type = "image/jpeg"
    file_size_bytes = 1024
    duration_seconds = None
    sort_order = factory.Sequence(lambda n: n)


class ModerationReportFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ModerationReport

    reporter_participant = factory.SubFactory(SeasonParticipantFactory)
    target_type = "Submission"
    target_id = "1"
    reason = ModerationReport.Reason.SPAM
    details = "Test report details."
    status = ModerationReport.Status.OPEN


class AuditLogFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = AuditLog

    season = factory.SubFactory(SeasonFactory)
    actor_participant = factory.SubFactory(SeasonParticipantFactory)
    action_type = "test.action"
    target_type = "TestModel"
    target_id = "1"
    old_value_json = {}
    new_value_json = {}
    reason = ""


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def bind_participant_session(client: Client, season: Season, participant: SeasonParticipant) -> None:
    """Bind a participant to the test client's session so views recognise them."""
    session = client.session
    session[f"season_participant_{season.id}"] = participant.id
    session.save()


# ---------------------------------------------------------------------------
# Shared pytest fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_cache():
    """Clear Django cache before each test to avoid rate-limit interference."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture()
def staff_user(db) -> Account:
    return AccountFactory(is_staff=True, username="staffuser")


@pytest.fixture()
def host_client(staff_user) -> Client:
    c = Client()
    c.force_login(staff_user)
    return c


@pytest.fixture()
def season(db) -> Season:
    return SeasonFactory(status=Season.Status.ACTIVE, join_code="JOINME")


@pytest.fixture()
def host_participant(season, staff_user) -> SeasonParticipant:
    return SeasonParticipantFactory(
        season=season,
        account=staff_user,
        handle="host",
        role=SeasonParticipant.Role.HOST,
        is_guest=False,
    )


@pytest.fixture()
def player_participant(season) -> SeasonParticipant:
    return SeasonParticipantFactory(
        season=season,
        handle="player1",
        role=SeasonParticipant.Role.PLAYER,
        is_guest=False,
    )
