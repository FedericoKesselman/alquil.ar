# usuarios/forms.py
from datetime import date  
from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth import get_user_model
from django.core.validators import RegexValidator
from django.core.mail import send_mail
from django.utils import timezone
from datetime import date
import random
import string
import hashlib
import uuid
from .models import Sucursal, Usuario

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

    # Los campos actuales están bien
    def clean(self):
        cleaned_data = super().clean()
        email = cleaned_data.get('email')
        password = cleaned_data.get('password')

        if email and password:
            try:
                user = User.objects.get(email=email)
                
                # Verificar contraseña primero
                if not user.check_password(password):
                    raise forms.ValidationError('Contraseña incorrecta')
                
                # Si es admin, generar y enviar token
                if user.tipo == 'ADMIN':
                    try:
                        token = ''.join(random.choices(string.digits, k=6))
                        
                        # Actualizar usuario con nuevo token
                        User.objects.filter(id=user.id).update(
                            token_2fa=token,
                            token_2fa_timestamp=timezone.now()
                        )
                        
                        try:
                            # Enviar token por email
                            self._enviar_token_email(user, token)
                            cleaned_data['needs_2fa'] = True
                        except Exception as e:
                            print(f"Error al enviar email: {str(e)}")  # Para debug
                            raise forms.ValidationError(f'Error al enviar el código de verificación: {str(e)}')
                            
                    except Exception as e:
                        print(f"Error al generar token: {str(e)}")  # Para debug
                        raise forms.ValidationError(f'Error al generar el código de verificación: {str(e)}')
                
                cleaned_data['user'] = user
                
            except User.DoesNotExist:
                raise forms.ValidationError('No existe ese mail en el sistema')
        
        return cleaned_data

    def _enviar_token_email(self, user, token):
        """Método auxiliar para enviar el email con el token"""
        send_mail(
            'Código de verificación - Alquil.ar',
            f'''Hola {user.nombre},
            
Se ha solicitado acceso a tu cuenta de administrador.
Tu código de verificación es: {token}

Este código es válido por 5 minutos.
Si no solicitaste este código, ignora este mensaje.

Saludos,
Equipo de Alquil.ar''',
            'alquil.ar2025@gmail.com',
            [user.email],
            fail_silently=False,
        )
        
class EmpleadoForm(forms.Form):
    # Declaro los campos del formulario
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
        max_length=8,
        min_length=7,
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
    sucursal = forms.ModelChoiceField(
        queryset=Sucursal.objects.filter(activa=True),
        label="Sucursal",
        widget=forms.Select(attrs={'class': 'form-control'}),
        required=True
    )
    password = forms.CharField(
        label="Contraseña",
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Contraseña'})
    )
    confirm_password = forms.CharField(
        label="Confirmar contraseña",
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Repetir contraseña'})
    )

    # Validaciones específicas para cada campo
    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError('El correo electrónico ingresado ya se encuentra registrado.')
        return email

    def clean_dni(self):
        dni = self.cleaned_data.get('dni')
        if User.objects.filter(dni=dni).exists():
            raise forms.ValidationError('El DNI ingresado ya se encuentra registrado en el sistema.')
        return dni

    def clean_password(self):
        password = self.cleaned_data.get('password')
        
        if not password:
            raise forms.ValidationError('La contraseña es obligatoria.')
            
        if len(password) < 8:
            raise forms.ValidationError('La contraseña debe tener al menos 8 caracteres, una letra mayúscula y un número.')
        
        
        if not any(c.islower() for c in password):
            raise forms.ValidationError('La contraseña debe tener al menos 8 caracteres, una letra mayúscula y un número.')
        
        
        return password

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        confirm_password = cleaned_data.get('confirm_password')

        if password and confirm_password:
            if password != confirm_password:
                self.add_error('confirm_password', 'Las contraseñas ingresadas no coinciden.')

        return cleaned_data

    def save(self):
        user = User.objects.create_user(
            username=self.cleaned_data['email'],
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
        max_length=8,
        min_length=7,
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
                'type': 'date',
                'max': date.today().isoformat(),
            }
        )
    )

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
        
        if not fecha_nacimiento:
            raise forms.ValidationError("La fecha de nacimiento es obligatoria")
            
        hoy = date.today()
        edad = hoy.year - fecha_nacimiento.year - ((hoy.month, hoy.day) < (fecha_nacimiento.month, fecha_nacimiento.day))

        # Verificar que no sea una fecha futura
        if fecha_nacimiento > hoy:
            raise forms.ValidationError("La fecha de nacimiento no puede ser futura")
        
        if edad < 18:
            raise forms.ValidationError("El cliente debe ser mayor de 18 años para registrarse")
    
        return fecha_nacimiento

    def save(self):
        caracteres = string.ascii_letters + string.digits
        password = ''.join(random.choice(caracteres) for i in range(12))
        
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

class TokenVerificationForm(forms.Form):
    token = forms.CharField(
        label="Código de verificación",
        max_length=6,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Ingrese el código de 6 dígitos',
            'inputmode': 'numeric',
            'pattern': '[0-9]{6}',
            'maxlength': '6',  # limita en el navegador
            'oninput': 'this.value = this.value.replace(/[^0-9]/g, "")',
        }),
        validators=[
            RegexValidator(
                r'^\d{6}$',
                'El código debe contener exactamente 6 dígitos'
            )
        ]
    )


    def __init__(self, user=None, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_token(self):
        token = self.cleaned_data.get('token')
        
        if not self.user or not self.user.token_2fa:
            raise forms.ValidationError('Sesión de verificación inválida')
            
        if token != self.user.token_2fa:
            raise forms.ValidationError('Código de verificación incorrecto')
    
        tiempo_actual = timezone.now()
        if tiempo_actual > (self.user.token_2fa_timestamp + timezone.timedelta(minutes=5)):
            User.objects.filter(id=self.user.id).update(
                token_2fa=None,
                token_2fa_timestamp=None
            )
            raise forms.ValidationError('El código ha expirado. Por favor, solicita uno nuevo.')
            
        return token

class RecuperarPasswordForm(forms.Form):
    email = forms.EmailField(
        label="Correo electrónico",
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'Ingresa tu correo electrónico'
        })
    )
    
    # ELIMINAMOS la validación que revelaba si el email existe
    def clean_email(self):
        email = self.cleaned_data.get('email')
        # Solo validamos formato, no si existe en la BD
        return email
    
    def save(self):
        email = self.cleaned_data['email']
        
        # Intentar encontrar el usuario
        try:
            user = User.objects.get(email=email)
            
            # Solo si el usuario existe, generar y enviar token
            token = hashlib.sha256(f"{user.id}{timezone.now()}{uuid.uuid4()}".encode()).hexdigest()
            
            user.reset_token = token
            user.reset_token_timestamp = timezone.now()
            user.reset_token_used = False
            user.save()
            
            reset_url = f"http://localhost:8000/usuarios/restablecer-password/{token}/"
            
            send_mail(
                'Restablecer contraseña - Alquil.ar',
                f'''Hola {user.nombre},
                
Hemos recibido una solicitud para restablecer tu contraseña.

Para crear una nueva contraseña, haz clic en el siguiente enlace:
{reset_url}

Este enlace es válido por 15 minutos y solo puede usarse una vez.
Si no solicitaste este cambio, puedes ignorar este mensaje.

Saludos,
Equipo de Alquil.ar''',
                'alquil.ar2025@gmail.com',
                [user.email],
                fail_silently=False,
            )
            
        except User.DoesNotExist:
            # Si el usuario no existe, no hacemos nada pero no mostramos error
            pass
        
        # Siempre retornamos True para no revelar si el email existe
        return True

class RestablecerPasswordForm(forms.Form):
    password = forms.CharField(
        label="Nueva contraseña",
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Nueva contraseña'})
    )
    confirm_password = forms.CharField(
        label="Confirmar nueva contraseña",
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Repetir nueva contraseña'})
    )
    
    def __init__(self, user=None, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
    
    def clean_password(self):
        password = self.cleaned_data.get('password')
        
        if not password:
            raise forms.ValidationError('La contraseña es obligatoria.')
            
        if len(password) < 8:
            raise forms.ValidationError('La contraseña debe tener al menos 8 caracteres, incluyendo una mayúscula, una minúscula y un número.')
        
        if not any(c.isupper() for c in password):
            raise forms.ValidationError('La contraseña debe tener al menos 8 caracteres, incluyendo una mayúscula, una minúscula y un número.')
        
        if not any(c.islower() for c in password):
            raise forms.ValidationError('La contraseña debe tener al menos 8 caracteres, incluyendo una mayúscula, una minúscula y un número.')
        
        if not any(c.isdigit() for c in password):
            raise forms.ValidationError('La contraseña debe tener al menos 8 caracteres, incluyendo una mayúscula, una minúscula y un número.')
        
        return password
    
    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        confirm_password = cleaned_data.get('confirm_password')
        
        if password and confirm_password:
            if password != confirm_password:
                raise forms.ValidationError('Las contraseñas ingresadas no coinciden.')
        
        return cleaned_data
    
    def save(self):
        password = self.cleaned_data['password']
        self.user.set_password(password)
        
        self.user.reset_token_used = True
        self.user.reset_token = None
        self.user.reset_token_timestamp = None
        self.user.save()
        
        return self.user

class CambiarPasswordPerfilForm(forms.Form):
    current_password = forms.CharField(
        label="Contraseña actual",
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Contraseña actual'})
    )
    new_password = forms.CharField(
        label="Nueva contraseña",
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Nueva contraseña'})
    )
    confirm_new_password = forms.CharField(
        label="Confirmar nueva contraseña",
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Repetir nueva contraseña'})
    )
    
    def __init__(self, user=None, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
    
    def clean_current_password(self):
        current_password = self.cleaned_data.get('current_password')
        
        if not self.user.check_password(current_password):
            raise forms.ValidationError('La contraseña actual ingresada no es válida.')
        
        return current_password
    
    def clean_new_password(self):
        new_password = self.cleaned_data.get('new_password')
        
        if not new_password:
            raise forms.ValidationError('La nueva contraseña es obligatoria.')
            
        if len(new_password) < 8:
            raise forms.ValidationError('La contraseña debe tener al menos 8 caracteres, incluyendo una mayúscula, una minúscula y un número.')
        
        if not any(c.isupper() for c in new_password):
            raise forms.ValidationError('La contraseña debe tener al menos 8 caracteres, incluyendo una mayúscula, una minúscula y un número.')
        
        if not any(c.islower() for c in new_password):
            raise forms.ValidationError('La contraseña debe tener al menos 8 caracteres, incluyendo una mayúscula, una minúscula y un número.')
        
        if not any(c.isdigit() for c in new_password):
            raise forms.ValidationError('La contraseña debe tener al menos 8 caracteres, incluyendo una mayúscula, una minúscula y un número.')
        
        current_password = self.cleaned_data.get('current_password')
        if current_password and self.user.check_password(new_password):
            raise forms.ValidationError('La nueva contraseña no puede ser igual a la anterior.')
        
        return new_password
    
    def clean(self):
        cleaned_data = super().clean()
        new_password = cleaned_data.get('new_password')
        confirm_new_password = cleaned_data.get('confirm_new_password')
        
        if new_password and confirm_new_password:
            if new_password != confirm_new_password:
                raise forms.ValidationError('Las nuevas contraseñas ingresadas no coinciden.')
        
        return cleaned_data
    
    def save(self):
        new_password = self.cleaned_data['new_password']
        self.user.set_password(new_password)
        self.user.save()
        return self.user