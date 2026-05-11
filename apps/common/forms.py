from django import forms


class BootstrapFormMixin:
    """Apply consistent Bootstrap classes to form widgets."""

    CONTEXTUAL_TOOLTIPS = {
        "title": "Public name shown to players.",
        "slug": "URL-friendly identifier used in links, for example summer-2026.",
        "description": "Player-facing instructions that explain what to do.",
        "status": "Controls lifecycle and visibility behavior for this item.",
        "keep_image_exif": "Keep camera metadata on uploaded images. Disable for better privacy.",
        "join_code": "Required to join the season. Share this with participants.",
        "starts_at": "Optional start date/time. Leave blank to start manually.",
        "ends_at": "Optional end date/time after which activity should stop.",
        "default_duration_seconds": "Default time limit in seconds when this quest is used.",
        "default_points_max": "Default maximum score judges can award.",
        "quest": "Reusable quest definition that this season quest is based on.",
        "title_override": "Optional season-specific title shown instead of the base quest title.",
        "description_override": "Optional season-specific instructions shown to players.",
        "quest_mode": "Scheduled quests start at a specific time. Open quests can be claimed anytime.",
        "assignment_policy": "Choose whether hosts assign quests or players claim them.",
        "rsvp_code": "Optional quest-specific override. Leave blank to use the season join code.",
        "duration_seconds": "Use this when you want to set the quest length directly.",
        "opens_at": "Optional planned open time. Use with close time to auto-calculate duration.",
        "closes_at": "Optional planned close time. Use with open time to auto-calculate duration.",
        "reveal_policy": "Determines when results become visible to players.",
        "points_max": "Maximum score a judge can give for this quest.",
        "allow_late_submissions": "Allow submissions after deadline with grace period rules.",
        "late_grace_seconds": "Extra time allowed after deadline when late submissions are enabled.",
        "handle": "Display name shown on leaderboard and quest activity.",
        "confirm": "Confirm this action before continuing.",
        "text_response": "Optional written response when a quest accepts text.",
        "media_files": "Upload one or more files. Size and format limits apply.",
        "score": "Judge score from 0 to 5.",
        "judge_note": "Optional private judging note for staff.",
        "reason": "Explain the report reason or why a score was changed.",
        "details": "Optional extra context to help reviewers decide.",
    }

    def _build_tooltip(self, field_name: str, field: forms.Field) -> str:
        explicit_help = (field.help_text or "").strip()
        if explicit_help:
            return explicit_help

        if field_name in self.CONTEXTUAL_TOOLTIPS:
            return self.CONTEXTUAL_TOOLTIPS[field_name]

        if isinstance(field, forms.BooleanField):
            return f"Toggle {str(field.label).lower()}."

        if field.label:
            return f"Enter {str(field.label).lower()}."

        return ""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            widget = field.widget
            classes = widget.attrs.get("class", "").split()

            if isinstance(widget, forms.CheckboxInput):
                wanted = "form-check-input"
            elif isinstance(widget, forms.Select):
                wanted = "form-select"
            elif isinstance(widget, forms.Textarea):
                wanted = "form-control"
            elif isinstance(widget, forms.FileInput):
                wanted = "form-control"
            else:
                wanted = "form-control"

            if wanted not in classes:
                classes.append(wanted)
            widget.attrs["class"] = " ".join(c for c in classes if c)

            if "title" not in widget.attrs:
                tooltip = self._build_tooltip(field_name, field)
                if tooltip:
                    widget.attrs["title"] = tooltip
