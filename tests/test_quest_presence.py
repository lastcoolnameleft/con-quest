from django.core.cache import cache
from django.test import TestCase

from apps.realtime.presence import get_quest_online_counts
from apps.realtime.presence import register_quest_viewer_connection
from apps.realtime.presence import touch_quest_viewer_connection
from apps.realtime.presence import unregister_quest_viewer_connection


class QuestPresenceTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_presence_counts_unique_participants(self):
        count = register_quest_viewer_connection(
            season_id=1,
            quest_id=10,
            participant_id=21,
            connection_id="chan-a",
        )
        self.assertEqual(count, 1)

        count = register_quest_viewer_connection(
            season_id=1,
            quest_id=10,
            participant_id=21,
            connection_id="chan-b",
        )
        self.assertEqual(count, 1)

        count = register_quest_viewer_connection(
            season_id=1,
            quest_id=10,
            participant_id=22,
            connection_id="chan-c",
        )
        self.assertEqual(count, 2)

        counts = get_quest_online_counts(season_id=1, quest_ids=[10, 11])
        self.assertEqual(counts[10], 2)
        self.assertEqual(counts[11], 0)

    def test_unregister_and_touch_presence(self):
        register_quest_viewer_connection(
            season_id=1,
            quest_id=10,
            participant_id=21,
            connection_id="chan-a",
        )
        touch_quest_viewer_connection(
            season_id=1,
            quest_id=10,
            participant_id=21,
            connection_id="chan-a",
        )
        count = unregister_quest_viewer_connection(
            season_id=1,
            quest_id=10,
            participant_id=21,
            connection_id="chan-a",
        )
        self.assertEqual(count, 0)
