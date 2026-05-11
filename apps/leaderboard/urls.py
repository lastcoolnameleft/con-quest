from django.urls import path

from apps.leaderboard.views import season_leaderboard

urlpatterns = [
    path("seasons/<slug:slug>/leaderboard/", season_leaderboard, name="season-leaderboard"),
]
