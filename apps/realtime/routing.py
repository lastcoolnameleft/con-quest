from django.urls import re_path

from apps.realtime.consumers import HealthConsumer
from apps.realtime.consumers import SeasonQuestConsumer

websocket_urlpatterns = [
    re_path(r"ws/health/$", HealthConsumer.as_asgi()),
    re_path(r"ws/season/(?P<season_id>\d+)/$", SeasonQuestConsumer.as_asgi()),
]
