from __future__ import annotations

from django.core.cache import cache


PRESENCE_TTL_SECONDS = 60


def _presence_cache_key(*, season_id: int, quest_id: int) -> str:
    return f"quest-presence:{season_id}:{quest_id}"


def register_quest_viewer_connection(
    *,
    season_id: int,
    quest_id: int,
    participant_id: int,
    connection_id: str,
) -> int:
    key = _presence_cache_key(season_id=season_id, quest_id=quest_id)
    presence_map = cache.get(key, {})
    participant_key = str(participant_id)
    existing_connections = set(presence_map.get(participant_key, []))
    existing_connections.add(connection_id)
    presence_map[participant_key] = sorted(existing_connections)
    cache.set(key, presence_map, timeout=PRESENCE_TTL_SECONDS)
    return len(presence_map)


def touch_quest_viewer_connection(
    *,
    season_id: int,
    quest_id: int,
    participant_id: int,
    connection_id: str,
) -> int:
    key = _presence_cache_key(season_id=season_id, quest_id=quest_id)
    presence_map = cache.get(key, {})
    participant_key = str(participant_id)
    existing_connections = set(presence_map.get(participant_key, []))
    existing_connections.add(connection_id)
    presence_map[participant_key] = sorted(existing_connections)
    cache.set(key, presence_map, timeout=PRESENCE_TTL_SECONDS)
    return len(presence_map)


def unregister_quest_viewer_connection(
    *,
    season_id: int,
    quest_id: int,
    participant_id: int,
    connection_id: str,
) -> int:
    key = _presence_cache_key(season_id=season_id, quest_id=quest_id)
    presence_map = cache.get(key, {})
    participant_key = str(participant_id)
    existing_connections = set(presence_map.get(participant_key, []))
    existing_connections.discard(connection_id)
    if existing_connections:
        presence_map[participant_key] = sorted(existing_connections)
    else:
        presence_map.pop(participant_key, None)

    cache.set(key, presence_map, timeout=PRESENCE_TTL_SECONDS)
    return len(presence_map)


def get_quest_online_counts(*, season_id: int, quest_ids: list[int]) -> dict[int, int]:
    return {
        quest_id: len(cache.get(_presence_cache_key(season_id=season_id, quest_id=quest_id), {}))
        for quest_id in quest_ids
    }
