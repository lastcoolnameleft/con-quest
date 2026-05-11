from unittest.mock import patch

from django.test import TestCase

from apps.realtime.events import broadcast_season_event


class _RecordingLayer:
    def __init__(self):
        self.calls = []

    async def group_send(self, group: str, message: dict):
        self.calls.append((group, message))


class _FailingLayer:
    async def group_send(self, group: str, message: dict):
        raise RuntimeError("channel send failed")


class RealtimeResilienceTests(TestCase):
    def test_broadcast_sends_event_when_channel_layer_available(self):
        layer = _RecordingLayer()
        payload = {"event": "quest_started", "season_quest_id": 1}

        with patch("apps.realtime.events.get_channel_layer", return_value=layer):
            broadcast_season_event(season_id=42, payload=payload)

        self.assertEqual(len(layer.calls), 1)
        group, message = layer.calls[0]
        self.assertEqual(group, "season_42")
        self.assertEqual(message["type"], "season_event")
        self.assertEqual(message["payload"], payload)

    def test_broadcast_noops_when_channel_layer_is_missing(self):
        with patch("apps.realtime.events.get_channel_layer", return_value=None):
            with self.assertLogs("apps.realtime.events", level="WARNING") as logs:
                broadcast_season_event(season_id=42, payload={"event": "ping"})

        self.assertTrue(any("channel layer is unavailable" in line for line in logs.output))

    def test_broadcast_noops_when_group_send_raises(self):
        layer = _FailingLayer()

        with patch("apps.realtime.events.get_channel_layer", return_value=layer):
            with self.assertLogs("apps.realtime.events", level="WARNING") as logs:
                broadcast_season_event(season_id=42, payload={"event": "ping"})

        self.assertTrue(any("Realtime broadcast failed" in line for line in logs.output))
