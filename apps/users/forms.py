from django import forms

from apps.users.models import User


class UserCreationForm(forms.ModelForm):
    """
    Form for creating new users
    """

    class Meta:
        model = User
        fields = ["username", "name", "email", "github"]
