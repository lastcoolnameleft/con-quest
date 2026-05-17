"""Permission boundary tests for can_access_control_center, can_manage_season, can_create_quests, _can_moderate."""

from __future__ import annotations

import pytest
from django.test import Client, RequestFactory

from apps.quests.permissions import can_access_control_center, can_create_quests, can_manage_season
from apps.seasons.models import SeasonParticipant

from .conftest import (
    AccountFactory,
    SeasonFactory,
    SeasonParticipantFactory,
    bind_participant_session,
)


@pytest.fixture()
def rf():
    return RequestFactory()


def _build_request(rf, user=None, session_data=None):
    """Create a request with an optional user and session dict."""
    request = rf.get("/")
    if user:
        request.user = user
    else:
        from django.contrib.auth.models import AnonymousUser
        request.user = AnonymousUser()
    request.session = session_data or {}
    return request


# ===========================================================================
# can_access_control_center
# ===========================================================================


@pytest.mark.django_db
class TestCanAccessControlCenter:

    def test_staff_user(self, rf):
        user = AccountFactory(is_staff=True)
        request = _build_request(rf, user=user)
        assert can_access_control_center(request) is True

    def test_superuser(self, rf):
        user = AccountFactory(is_superuser=True)
        request = _build_request(rf, user=user)
        assert can_access_control_center(request) is True

    def test_host_participant_via_account(self, rf):
        user = AccountFactory()
        season = SeasonFactory(status="active")
        SeasonParticipantFactory(season=season, account=user, role=SeasonParticipant.Role.HOST)
        request = _build_request(rf, user=user)
        assert can_access_control_center(request) is True

    def test_admin_participant_via_account(self, rf):
        user = AccountFactory()
        season = SeasonFactory(status="active")
        SeasonParticipantFactory(season=season, account=user, role=SeasonParticipant.Role.ADMIN)
        request = _build_request(rf, user=user)
        assert can_access_control_center(request) is True

    def test_player_denied(self, rf):
        user = AccountFactory()
        season = SeasonFactory(status="active")
        SeasonParticipantFactory(season=season, account=user, role=SeasonParticipant.Role.PLAYER)
        request = _build_request(rf, user=user)
        assert can_access_control_center(request) is False

    def test_viewer_denied(self, rf):
        user = AccountFactory()
        season = SeasonFactory(status="active")
        SeasonParticipantFactory(season=season, account=user, role=SeasonParticipant.Role.VIEWER)
        request = _build_request(rf, user=user)
        assert can_access_control_center(request) is False

    def test_anonymous_denied(self, rf):
        request = _build_request(rf)
        assert can_access_control_center(request) is False

    def test_guest_host_via_session(self, rf):
        season = SeasonFactory(status="active")
        participant = SeasonParticipantFactory(
            season=season, account=None, role=SeasonParticipant.Role.HOST, is_guest=True,
        )
        request = _build_request(rf, session_data={f"season_participant_{season.id}": participant.id})
        assert can_access_control_center(request) is True

    def test_guest_player_via_session_denied(self, rf):
        season = SeasonFactory(status="active")
        participant = SeasonParticipantFactory(
            season=season, account=None, role=SeasonParticipant.Role.PLAYER, is_guest=True,
        )
        request = _build_request(rf, session_data={f"season_participant_{season.id}": participant.id})
        assert can_access_control_center(request) is False


# ===========================================================================
# can_manage_season
# ===========================================================================


@pytest.mark.django_db
class TestCanManageSeason:

    def test_staff_user(self, rf):
        user = AccountFactory(is_staff=True)
        season = SeasonFactory(status="active")
        request = _build_request(rf, user=user)
        assert can_manage_season(request, season) is True

    def test_superuser(self, rf):
        user = AccountFactory(is_superuser=True)
        season = SeasonFactory(status="active")
        request = _build_request(rf, user=user)
        assert can_manage_season(request, season) is True

    def test_host_on_correct_season(self, rf):
        user = AccountFactory()
        season = SeasonFactory(status="active")
        SeasonParticipantFactory(season=season, account=user, role=SeasonParticipant.Role.HOST)
        request = _build_request(rf, user=user)
        assert can_manage_season(request, season) is True

    def test_host_on_different_season_denied(self, rf):
        user = AccountFactory()
        season_a = SeasonFactory(status="active", slug="season-a")
        season_b = SeasonFactory(status="active", slug="season-b")
        SeasonParticipantFactory(season=season_a, account=user, role=SeasonParticipant.Role.HOST)
        request = _build_request(rf, user=user)
        assert can_manage_season(request, season_b) is False

    def test_admin_participant(self, rf):
        user = AccountFactory()
        season = SeasonFactory(status="active")
        SeasonParticipantFactory(season=season, account=user, role=SeasonParticipant.Role.ADMIN)
        request = _build_request(rf, user=user)
        assert can_manage_season(request, season) is True

    def test_player_denied(self, rf):
        user = AccountFactory()
        season = SeasonFactory(status="active")
        SeasonParticipantFactory(season=season, account=user, role=SeasonParticipant.Role.PLAYER)
        request = _build_request(rf, user=user)
        assert can_manage_season(request, season) is False

    def test_anonymous_denied(self, rf):
        season = SeasonFactory(status="active")
        request = _build_request(rf)
        assert can_manage_season(request, season) is False

    def test_guest_host_via_session(self, rf):
        season = SeasonFactory(status="active")
        participant = SeasonParticipantFactory(
            season=season, account=None, role=SeasonParticipant.Role.HOST, is_guest=True,
        )
        request = _build_request(rf, session_data={f"season_participant_{season.id}": participant.id})
        assert can_manage_season(request, season) is True


# ===========================================================================
# can_create_quests — delegates to can_access_control_center
# ===========================================================================


@pytest.mark.django_db
class TestCanCreateQuests:

    def test_staff_can_create(self, rf):
        user = AccountFactory(is_staff=True)
        request = _build_request(rf, user=user)
        assert can_create_quests(request) is True

    def test_player_cannot_create(self, rf):
        user = AccountFactory()
        season = SeasonFactory(status="active")
        SeasonParticipantFactory(season=season, account=user, role=SeasonParticipant.Role.PLAYER)
        request = _build_request(rf, user=user)
        assert can_create_quests(request) is False


# ===========================================================================
# _can_moderate (moderation/views.py)
# ===========================================================================


@pytest.mark.django_db
class TestCanModerate:

    def _call(self, request, participant):
        from apps.moderation.views import _can_moderate
        return _can_moderate(request, participant)

    def test_staff_can_moderate(self, rf):
        user = AccountFactory(is_staff=True)
        request = _build_request(rf, user=user)
        assert self._call(request, None) is True

    def test_host_can_moderate(self, rf):
        user = AccountFactory()
        season = SeasonFactory(status="active")
        host = SeasonParticipantFactory(season=season, account=user, role=SeasonParticipant.Role.HOST)
        request = _build_request(rf, user=user)
        assert self._call(request, host) is True

    def test_admin_can_moderate(self, rf):
        user = AccountFactory()
        season = SeasonFactory(status="active")
        admin = SeasonParticipantFactory(season=season, account=user, role=SeasonParticipant.Role.ADMIN)
        request = _build_request(rf, user=user)
        assert self._call(request, admin) is True

    def test_player_cannot_moderate(self, rf):
        user = AccountFactory()
        season = SeasonFactory(status="active")
        player = SeasonParticipantFactory(season=season, account=user, role=SeasonParticipant.Role.PLAYER)
        request = _build_request(rf, user=user)
        assert self._call(request, player) is False

    def test_anonymous_no_participant_cannot_moderate(self, rf):
        request = _build_request(rf)
        assert self._call(request, None) is False
