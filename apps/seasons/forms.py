from django import forms

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


class SeasonForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Season
        fields = [
            "title",
            "slug",
            "status",
            "join_code",
        ]
