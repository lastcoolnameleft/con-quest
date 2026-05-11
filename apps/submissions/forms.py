from django import forms

from apps.common.forms import BootstrapFormMixin


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    widget = MultipleFileInput

    def clean(self, data, initial=None):
        single_file_clean = super().clean
        if not data:
            return []
        if isinstance(data, (list, tuple)):
            return [single_file_clean(item, initial) for item in data]
        return [single_file_clean(data, initial)]


class SubmissionForm(BootstrapFormMixin, forms.Form):
    text_response = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 4}))
    media_files = MultipleFileField(required=False)


class ScoreSubmissionForm(BootstrapFormMixin, forms.Form):
    score = forms.IntegerField(min_value=0, max_value=5)
    judge_note = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))
    reason = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))
