from apps.quests.permissions import can_access_control_center


def control_center(request):
    return {"can_access_control": can_access_control_center(request)}
