from django import forms
from zoneinfo import available_timezones

from apps.common.forms import BootstrapFormMixin
from apps.seasons.models import Season


class SeasonJoinForm(BootstrapFormMixin, forms.Form):
    handle = forms.CharField(
        max_length=50,
        widget=forms.TextInput(
            attrs={
                "class": "form-control form-control-lg",
                "placeholder": "Your display name",
                "autocomplete": "nickname",
                "title": "The name other players will see for your entries and score.",
            }
        ),
    )
    join_code = forms.CharField(
        max_length=20,
        widget=forms.TextInput(
            attrs={
                "class": "form-control form-control-lg text-uppercase",
                "autocomplete": "one-time-code",
                "placeholder": "JOIN CODE",
                "spellcheck": "false",
                "autocapitalize": "characters",
                "title": "Required to join this season.",
            }
        ),
    )


class SeasonClaimForm(BootstrapFormMixin, forms.Form):
    confirm = forms.BooleanField(required=True)


TIMEZONE_CHOICES = [(tz_name, tz_name) for tz_name in sorted(available_timezones())]


class SeasonForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Season
        fields = [
            "title",
            "slug",
            "status",
            "join_code",
            "timezone",
        ]
        widgets = {
            "timezone": forms.Select(choices=TIMEZONE_CHOICES),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["timezone"].required = False
        self.fields["timezone"].help_text = "All season times are displayed in this timezone."
