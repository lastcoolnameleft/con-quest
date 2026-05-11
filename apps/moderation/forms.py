from django import forms

from apps.common.forms import BootstrapFormMixin
from apps.moderation.models import ModerationReport


class ModerationReportForm(BootstrapFormMixin, forms.Form):
    reason = forms.ChoiceField(choices=ModerationReport.Reason.choices)
    details = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))


class ResolveReportForm(BootstrapFormMixin, forms.Form):
    status = forms.ChoiceField(
        choices=(
            (ModerationReport.Status.DISMISSED, "Dismiss"),
            (ModerationReport.Status.ACTIONED, "Actioned"),
        )
    )
    details = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))
