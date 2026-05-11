from django.http import HttpRequest

from apps.seasons.models import Season
from apps.seasons.models import SeasonParticipant


def session_participant_key(season_id: int) -> str:
    return f"season_participant_{season_id}"


def bind_session_participant(request: HttpRequest, season: Season, participant: SeasonParticipant) -> None:
    request.session[session_participant_key(season.id)] = participant.id
    request.session.modified = True


def get_session_participant(request: HttpRequest, season: Season) -> SeasonParticipant | None:
    participant_id = request.session.get(session_participant_key(season.id))
    if not participant_id:
        return None
    return SeasonParticipant.objects.filter(id=participant_id, season=season).first()
