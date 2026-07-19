from urllib.parse import parse_qs

from asgiref.sync import sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from apps.realtime.presence import register_quest_viewer_connection
from apps.realtime.presence import touch_quest_viewer_connection
from apps.realtime.presence import unregister_quest_viewer_connection


class SeasonQuestConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.season_id = self.scope["url_route"]["kwargs"]["season_id"]
        self.group_name = f"season_{self.season_id}"
        self.presence_quest_id: int | None = None
        self.presence_participant_id: int | None = None

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        query_string = self.scope.get("query_string", b"").decode()
        query_params = parse_qs(query_string)
        quest_id_value = (query_params.get("quest_id") or [None])[0]
        participant_id_value = (query_params.get("participant_id") or [None])[0]
        try:
            quest_id = int(quest_id_value) if quest_id_value is not None else None
            participant_id = int(participant_id_value) if participant_id_value is not None else None
        except ValueError:
            quest_id = None
            participant_id = None

        if quest_id and participant_id:
            self.presence_quest_id = quest_id
            self.presence_participant_id = participant_id
            active_viewer_count = await sync_to_async(register_quest_viewer_connection)(
                season_id=int(self.season_id),
                quest_id=quest_id,
                participant_id=participant_id,
                connection_id=self.channel_name,
            )
            await self._broadcast_presence_count(active_viewer_count)

        await self.send_json({"event": "connected", "season_id": self.season_id})

    async def disconnect(self, code):
        if self.presence_quest_id and self.presence_participant_id:
            active_viewer_count = await sync_to_async(unregister_quest_viewer_connection)(
                season_id=int(self.season_id),
                quest_id=self.presence_quest_id,
                participant_id=self.presence_participant_id,
                connection_id=self.channel_name,
            )
            await self._broadcast_presence_count(active_viewer_count)
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def season_event(self, event):
        await self.send_json(event["payload"])

    async def receive_json(self, content, **kwargs):
        if content.get("event") != "presence_ping":
            return
        if not self.presence_quest_id or not self.presence_participant_id:
            return
        active_viewer_count = await sync_to_async(touch_quest_viewer_connection)(
            season_id=int(self.season_id),
            quest_id=self.presence_quest_id,
            participant_id=self.presence_participant_id,
            connection_id=self.channel_name,
        )
        await self._broadcast_presence_count(active_viewer_count)

    async def _broadcast_presence_count(self, active_viewer_count: int) -> None:
        if not self.presence_quest_id:
            return
        await self.channel_layer.group_send(
            self.group_name,
            {
                "type": "season_event",
                "payload": {
                    "event": "quest_presence_updated",
                    "season_quest_id": self.presence_quest_id,
                    "active_viewer_count": active_viewer_count,
                },
            },
        )


class HealthConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        await self.accept()
        await self.send_json({"event": "connected"})
