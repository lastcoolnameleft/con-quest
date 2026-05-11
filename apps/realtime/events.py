from __future__ import annotations

import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer


logger = logging.getLogger(__name__)


def broadcast_season_event(*, season_id: int, payload: dict) -> None:
    channel_layer = get_channel_layer()
    if channel_layer is None:
        logger.warning("Skipping broadcast for season_%s because channel layer is unavailable.", season_id)
        return

    try:
        async_to_sync(channel_layer.group_send)(
            f"season_{season_id}",
            {
                "type": "season_event",
                "payload": payload,
            },
        )
    except Exception:
        logger.warning("Realtime broadcast failed for season_%s.", season_id, exc_info=True)
