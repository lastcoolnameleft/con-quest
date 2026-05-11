from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("auth/", include("django.contrib.auth.urls")),
    path("auth/", include("allauth.urls")),
    path("", include("apps.legal.urls")),
    path("", include("apps.quests.urls")),
    path("", include("apps.submissions.urls")),
    path("", include("apps.moderation.urls")),
    path("", include("apps.leaderboard.urls")),
    path("", include("apps.seasons.urls")),
]
