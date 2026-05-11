from allauth.account.forms import LoginForm

from apps.common.forms import BootstrapFormMixin


class ConQuestLoginForm(BootstrapFormMixin, LoginForm):
    pass
