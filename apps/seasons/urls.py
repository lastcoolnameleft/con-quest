from django.urls import path

from apps.seasons.views import claim_participation
from apps.seasons.views import control_dashboard
from apps.seasons.views import connection_test
from apps.seasons.views import connection_test_global
from apps.seasons.views import index
from apps.seasons.views import join_season_by_code
from apps.seasons.views import join_season
from apps.seasons.views import season_create
from apps.seasons.views import season_delete
from apps.seasons.views import season_edit
from apps.seasons.views import season_state
from apps.seasons.views import season_detail

urlpatterns = [
    path("", index, name="season-index"),
    path("join/", join_season_by_code, name="season-join-by-code"),
    path("seasons/<slug:slug>/", season_detail, name="season-detail"),
    path("seasons/<slug:slug>/join/", join_season, name="season-join"),
    path("seasons/<slug:slug>/claim/", claim_participation, name="season-claim"),
    path("connection-test/", connection_test_global, name="connection-test-global"),
    path("seasons/<slug:slug>/connection-test/", connection_test, name="season-connection-test"),
    path("seasons/<slug:slug>/state/", season_state, name="season-state"),
    path("control/", control_dashboard, name="control-dashboard"),
    path("control/seasons/new/", season_create, name="control-season-create"),
    path("control/seasons/<slug:slug>/edit/", season_edit, name="control-season-edit"),
    path("control/seasons/<slug:slug>/delete/", season_delete, name="control-season-delete"),
]
