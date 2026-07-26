from django.http import HttpRequest

from apps.seasons.models import Season
from apps.seasons.models import SeasonParticipant

ACTIVE_PARTICIPANT_KEY = "active_season_participant_id"


def session_participant_key(season_id: int) -> str:
    return f"season_participant_{season_id}"


def bind_session_participant(request: HttpRequest, season: Season, participant: SeasonParticipant) -> None:
    target_key = session_participant_key(season.id)
    for key in list(request.session.keys()):
        if key.startswith("season_participant_") and key != target_key:
            request.session.pop(key, None)
    request.session[target_key] = participant.id
    request.session[ACTIVE_PARTICIPANT_KEY] = participant.id
    request.session.modified = True


def get_session_participant(request: HttpRequest, season: Season) -> SeasonParticipant | None:
    participant_id = request.session.get(session_participant_key(season.id))
    if not participant_id:
        return None
    return SeasonParticipant.objects.filter(id=participant_id, season=season).first()


def get_bound_participant_ids(request: HttpRequest) -> list[int]:
    participant_ids: list[int] = []
    active_participant_id = request.session.get(ACTIVE_PARTICIPANT_KEY)
    if str(active_participant_id).isdigit():
        participant_ids.append(int(active_participant_id))

    for key, value in request.session.items():
        if not key.startswith("season_participant_"):
            continue
        if not str(value).isdigit():
            continue
        participant_id = int(value)
        if participant_id in participant_ids:
            continue
        participant_ids.append(participant_id)

    return participant_ids
