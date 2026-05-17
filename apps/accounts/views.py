from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from apps.seasons.models import SeasonParticipant


@login_required
def profile(request):
    participations = (
        SeasonParticipant.objects.filter(account=request.user)
        .select_related("season")
        .order_by("-joined_at")
    )

    return render(
        request,
        "account/profile.html",
        {
            "participations": participations,
        },
    )
