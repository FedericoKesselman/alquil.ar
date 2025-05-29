# usuarios/forms.py
from django import forms
from django.contrib.auth.forms import AuthenticationForm
from .models import Sucursal
from django.contrib.auth import get_user_model
from django.core.validators import RegexValidator
import random
import string
from django.core.mail import send_mail
from django.conf import settings
from datetime import date

User = get_user_model()

class LoginForm(forms.Form):
    #Declarar los campos del formulario
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
        email = cleaned_data.get('email') #Extraer la info de los campos
        password = cleaned_data.get('password')

        if email and password:
            try:
                user = User.objects.get(email=email) #Traigo el usuario correspondiente a ese mail
                if not user.is_active:
                    raise forms.ValidationError('Esta cuenta está inactiva.')
                if not user.check_password(password):
                    raise forms.ValidationError('Contraseña incorrecta.')
                cleaned_data['user'] = user
            except User.DoesNotExist:
                raise forms.ValidationError('El email no está registrado.')
        
        return cleaned_data

class EmpleadoForm(forms.Form):
    # Declaro los campos del fomrulario
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

    # Extraigo la info de los campos y la chequeo
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

    def save(self): #Se guarde el usuario
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
    # Declaramos los campos
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
        max_length=8,  # Cambiamos a 8 para DNI argentino
        min_length=7,  # Mínimo 7 dígitos
        widget=forms.TextInput(attrs={
            'class': 'form-control', 
            'placeholder': 'DNI (7-8 dígitos)'
        }),
        validators=[
            RegexValidator(
                r'^\d{7,8}$', 
                'El DNI debe tener 7 u 8 dígitos numéricos'
            )
        ]
    )
    telefono = forms.CharField(
        label="Teléfono",
        max_length=20,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Número de teléfono'}),
        validators=[RegexValidator(r'^\d+$', 'Solo se permiten números en el teléfono')]
    )
    fecha_nacimiento = forms.DateField(
        label="Fecha de nacimiento",
        widget=forms.DateInput(
            attrs={
                'class': 'form-control', 
                'type': 'date'  # Esto hace que aparezca un selector de fecha
            }
        )
    )

    # Extraemos los campos y chequeamos info
    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError('El correo electrónico ingresado ya se encuentra registrado')
        return email

    def clean_dni(self):
        dni = self.cleaned_data.get('dni')
        if User.objects.filter(dni=dni).exists():
            raise forms.ValidationError('El DNI ingresado ya se encuentra registrado en el sistema')
        return dni
    
    def clean_fecha_nacimiento(self):
        fecha_nacimiento = self.cleaned_data.get('fecha_nacimiento')
        hoy = date.today()
        edad = hoy.year - fecha_nacimiento.year - ((hoy.month, hoy.day) < (fecha_nacimiento.month, fecha_nacimiento.day))
        
        if edad < 18:
            raise forms.ValidationError("El cliente debe ser mayor de 18 años para registrarse")
        return fecha_nacimiento

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        confirm_password = cleaned_data.get('confirm_password')

        if password and confirm_password and password != confirm_password:
            raise forms.ValidationError('Las contraseñas no coinciden.')

        return cleaned_data

    def save(self):
        # Generar contraseña aleatoria de 12 caracteres
        caracteres = string.ascii_letters + string.digits
        password = ''.join(random.choice(caracteres) for i in range(12))
        
        # Crear el usuario
        user = User.objects.create_user(
            username=self.cleaned_data['email'],
            email=self.cleaned_data['email'],
            password=password,
            nombre=self.cleaned_data['nombre'],
            dni=self.cleaned_data['dni'],
            telefono=self.cleaned_data['telefono'],
            fecha_nacimiento=self.cleaned_data['fecha_nacimiento'],
            tipo='CLIENTE'
        )
        
        # Enviar email con la contraseña
        send_mail(
            'Bienvenido a Alquil.ar',
            f'''Hola {self.cleaned_data['nombre']},
        
Tu cuenta ha sido creada exitosamente.
        
Tus credenciales de acceso son:
Email: {self.cleaned_data['email']}
Contraseña temporal: {password}
        
Por favor, ingresa al sistema y cambia tu contraseña por seguridad.
        
Saludos,
Equipo de Alquil.ar''',
            'alquil.ar2025@gmail.com',
            [self.cleaned_data['email']],
            fail_silently=False,
        )
    
        return user