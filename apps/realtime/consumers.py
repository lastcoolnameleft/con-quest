from channels.generic.websocket import AsyncJsonWebsocketConsumer


class SeasonQuestConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.season_id = self.scope["url_route"]["kwargs"]["season_id"]
        self.group_name = f"season_{self.season_id}"

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self.send_json({"event": "connected", "season_id": self.season_id})

    async def disconnect(self, code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def season_event(self, event):
        await self.send_json(event["payload"])


class HealthConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        await self.accept()
        await self.send_json({"event": "connected"})
