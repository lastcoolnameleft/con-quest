from django import forms

from apps.common.forms import BootstrapFormMixin
from apps.quests.models import Quest, SeasonQuest


class QuestForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Quest
        fields = ["title", "description", "default_duration_seconds", "default_points_max"]


class SeasonQuestForm(BootstrapFormMixin, forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.season = kwargs.pop("season", None)
        super().__init__(*args, **kwargs)
        self.fields["rsvp_code"].required = False
        self.fields["late_grace_seconds"].required = False
        if "status" in self.fields:
            self.fields["status"].required = False
            if self.instance.pk:
                self.fields["status"].initial = self.instance.status
            else:
                # Status changes are managed after creation; keep create form streamlined.
                self.fields.pop("status")
        self.fields["opens_at"].input_formats = ["%Y-%m-%dT%H:%M"]
        self.fields["opens_at"].widget = forms.DateTimeInput(
            attrs={
                "type": "datetime-local",
                "step": 60,
                "data-datetime-picker": "true",
                "autocomplete": "off",
            },
            format="%Y-%m-%dT%H:%M",
        )
        self.fields["closes_at"].input_formats = ["%Y-%m-%dT%H:%M"]
        self.fields["closes_at"].widget = forms.DateTimeInput(
            attrs={
                "type": "datetime-local",
                "step": 60,
                "data-datetime-picker": "true",
                "autocomplete": "off",
            },
            format="%Y-%m-%dT%H:%M",
        )

        # Re-apply Bootstrap classes and contextual titles after widget replacement.
        for field_name in ("opens_at", "closes_at"):
            field = self.fields[field_name]
            classes = field.widget.attrs.get("class", "").split()
            if "form-control" not in classes:
                classes.append("form-control")
            field.widget.attrs["class"] = " ".join(c for c in classes if c)
            if "title" not in field.widget.attrs:
                tooltip = self._build_tooltip(field_name, field)
                if tooltip:
                    field.widget.attrs["title"] = tooltip

    def clean(self):
        cleaned_data = super().clean()
        quest_mode = cleaned_data.get("quest_mode")
        allow_late_submissions = bool(cleaned_data.get("allow_late_submissions"))
        quest = cleaned_data.get("quest")
        title_override = (cleaned_data.get("title_override") or "").strip()
        target_status = cleaned_data.get("status")
        duration_seconds = cleaned_data.get("duration_seconds")
        opens_at = cleaned_data.get("opens_at")
        closes_at = cleaned_data.get("closes_at")

        # Keep override code normalized; empty means "inherit season code".
        cleaned_data["rsvp_code"] = (cleaned_data.get("rsvp_code") or "").strip().upper()

        # Hidden/disabled inputs are omitted from POST, so normalize missing grace values.
        if not allow_late_submissions:
            cleaned_data["late_grace_seconds"] = 0
        elif cleaned_data.get("late_grace_seconds") is None:
            self.add_error("late_grace_seconds", "Enter grace period seconds when late submissions are enabled.")

        if self.instance.pk and "status" in self.fields:
            original_status = self.instance.status
            if not target_status:
                cleaned_data["status"] = original_status
            elif target_status != original_status and not self.instance.can_transition_to(target_status):
                self.add_error("status", "Invalid status transition from current state.")

        # Hard-block duplicate quest names in the same season.
        season = self.season or getattr(self.instance, "season", None)
        resolved_title = title_override or (quest.title.strip() if quest else "")
        if not resolved_title:
            self.add_error("title_override", "Title is required.")
        elif season:
            existing = (
                SeasonQuest.objects.filter(season=season)
                .exclude(pk=self.instance.pk)
                .select_related("quest")
            )
            normalized_title = resolved_title.casefold()
            for season_quest in existing:
                existing_title = (season_quest.title_override or season_quest.quest.title or "").strip().casefold()
                if existing_title == normalized_title:
                    self.add_error("title_override", "A quest with this title already exists in this season.")
                    break

        if quest_mode != SeasonQuest.QuestMode.SCHEDULED:
            cleaned_data["opens_at"] = None
            cleaned_data["closes_at"] = None
            return cleaned_data

        has_open_time = opens_at is not None
        has_close_time = closes_at is not None

        if has_open_time != has_close_time:
            message = "Provide both open and close times, or leave both blank."
            self.add_error("opens_at", message)
            self.add_error("closes_at", message)
        elif has_open_time and has_close_time:
            if closes_at <= opens_at:
                self.add_error("closes_at", "Close time must be after open time.")
            else:
                cleaned_data["duration_seconds"] = int((closes_at - opens_at).total_seconds())
        elif not duration_seconds or duration_seconds <= 0:
            self.add_error("duration_seconds", "Enter a positive duration or set open and close times.")

        return cleaned_data

    class Meta:
        model = SeasonQuest
        fields = [
            "quest",
            "title_override",
            "description_override",
            "quest_mode",
            "status",
            "rsvp_code",
            "duration_seconds",
            "opens_at",
            "closes_at",
            "reveal_policy",
            "points_max",
            "allow_late_submissions",
            "late_grace_seconds",
        ]
        labels = {
            "title_override": "Title",
            "description_override": "Description",
        }
        help_texts = {
            "title_override": "Auto-filled from selected quest. You can edit it for this season.",
            "description_override": "Auto-filled from selected quest. Update if this season needs different instructions.",
        }
