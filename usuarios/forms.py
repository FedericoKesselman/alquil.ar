# usuarios/forms.py
from django import forms
from django.contrib.auth.forms import AuthenticationForm
from .models import Sucursal
from django.contrib.auth import get_user_model
from django.core.validators import RegexValidator

User = get_user_model()

class LoginForm(forms.Form):
    email = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email'})
    )
    password = forms.CharField(
        label="Contraseña",
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Contraseña'})
    )

    def clean(self):
        cleaned_data = super().clean()
        email = cleaned_data.get('email')
        password = cleaned_data.get('password')

        if email and password:
            try:
                user = User.objects.get(email=email)
                if not user.is_active:
                    raise forms.ValidationError('Esta cuenta está inactiva.')
                if not user.check_password(password):
                    raise forms.ValidationError('Contraseña incorrecta.')
                cleaned_data['user'] = user
            except User.DoesNotExist:
                raise forms.ValidationError('El email no está registrado.')
        
        return cleaned_data

class EmpleadoForm(forms.Form):
    email = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email del empleado'})
    )
    nombre = forms.CharField(
        label="Nombre completo",
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nombre completo'})
    )
    dni = forms.CharField(
        label="DNI",
        max_length=20,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Documento de identidad'}),
        validators=[RegexValidator(r'^\d+$', 'Solo se permiten números en el DNI')]
    )
    telefono = forms.CharField(
        label="Teléfono",
        max_length=20,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Número de teléfono'}),
        validators=[RegexValidator(r'^\d+$', 'Solo se permiten números en el teléfono')]
    )
    sucursal = forms.ModelChoiceField(
        queryset=Sucursal.objects.filter(activa=True),
        label="Sucursal",
        widget=forms.Select(attrs={'class': 'form-control'}),
        required=True
    )
    password = forms.CharField(
        label="Contraseña temporal",
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Contraseña temporal'})
    )
    confirm_password = forms.CharField(
        label="Confirmar contraseña",
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Repetir contraseña'})
    )

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError('Este email ya está registrado.')
        return email

    def clean_dni(self):
        dni = self.cleaned_data.get('dni')
        if User.objects.filter(dni=dni).exists():
            raise forms.ValidationError('Este DNI ya está registrado.')
        return dni

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        confirm_password = cleaned_data.get('confirm_password')

        if password and confirm_password and password != confirm_password:
            raise forms.ValidationError('Las contraseñas no coinciden.')

        return cleaned_data

    def save(self):
        user = User.objects.create_user(
            username=self.cleaned_data['email'],  # Usamos el email como username
            email=self.cleaned_data['email'],
            password=self.cleaned_data['password'],
            nombre=self.cleaned_data['nombre'],
            dni=self.cleaned_data['dni'],
            telefono=self.cleaned_data['telefono'],
            sucursal=self.cleaned_data['sucursal'],
            tipo='EMPLEADO'
        )
        return user
    
class ClienteForm(forms.Form):
    email = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email del cliente'})
    )
    nombre = forms.CharField(
        label="Nombre completo",
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nombre completo'})
    )
    dni = forms.CharField(
        label="DNI",
        max_length=20,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Documento de identidad'}),
        validators=[RegexValidator(r'^\d+$', 'Solo se permiten números en el DNI')]
    )
    telefono = forms.CharField(
        label="Teléfono",
        max_length=20,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Número de teléfono'}),
        validators=[RegexValidator(r'^\d+$', 'Solo se permiten números en el teléfono')]
    )
    password = forms.CharField(
        label="Contraseña",
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Contraseña'})
    )
    confirm_password = forms.CharField(
        label="Confirmar contraseña",
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Repetir contraseña'})
    )

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError('Este email ya está registrado.')
        return email

    def clean_dni(self):
        dni = self.cleaned_data.get('dni')
        if User.objects.filter(dni=dni).exists():
            raise forms.ValidationError('Este DNI ya está registrado.')
        return dni

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        confirm_password = cleaned_data.get('confirm_password')

        if password and confirm_password and password != confirm_password:
            raise forms.ValidationError('Las contraseñas no coinciden.')

        return cleaned_data

    def save(self):
        user = User.objects.create_user(
            username=self.cleaned_data['email'],
            email=self.cleaned_data['email'],
            password=self.cleaned_data['password'],
            nombre=self.cleaned_data['nombre'],
            dni=self.cleaned_data['dni'],
            telefono=self.cleaned_data['telefono'],
            tipo='CLIENTE'  # Rol de cliente
        )
        return user