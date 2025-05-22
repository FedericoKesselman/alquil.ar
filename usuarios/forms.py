# usuarios/forms.py
from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth import get_user_model

User = get_user_model()

class LoginForm(forms.Form):
    mail = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email'})
    )
    password = forms.CharField(
        label="Contraseña",
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Contraseña'})
    )

    def clean(self):
        cleaned_data = super().clean()
        mail = cleaned_data.get('mail')
        password = cleaned_data.get('password')

        if mail and password:
            try:
                user = User.objects.get(mail=mail)
            except User.DoesNotExist:
                raise forms.ValidationError('El email no está registrado.')
            if not user.check_password(password):
                raise forms.ValidationError('Contraseña incorrecta.')
            cleaned_data['user'] = user

        return cleaned_data