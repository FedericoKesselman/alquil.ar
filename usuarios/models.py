# usuarios/models.py
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator

# Aca van las declaraciones de las tablas de la base de datos

class Sucursal(models.Model):
    nombre = models.CharField(max_length=100)
    direccion = models.CharField(max_length=200)
    telefono = models.CharField(max_length=20, default="0")  # ✅ Campo teléfono agregado
    latitud = models.FloatField()
    longitud = models.FloatField()
    activa = models.BooleanField(default=True)

    def __str__(self):
        return self.nombre

class Usuario(AbstractUser):
    TIPO_CHOICES = [
        ('CLIENTE', 'Cliente'),
        ('EMPLEADO', 'Empleado'),
        ('ADMIN', 'Administrador'),
    ]
    
    nombre = models.CharField(max_length=200)
    tipo = models.CharField(
        max_length=10,
        choices=TIPO_CHOICES,
        default='CLIENTE',
        verbose_name="Tipo de usuario"
    )
    dni = models.CharField(max_length=20, unique=True)
    email = models.CharField(max_length=200, unique=True)
    telefono = models.CharField(max_length=20)
    sucursal = models.ForeignKey(Sucursal, on_delete=models.SET_NULL, null=True, blank=True)
    
    # Campos para 2FA
    token_2fa = models.CharField(
        max_length=6,
        null=True,
        blank=True,
        verbose_name="Token de verificación"
    )
    token_2fa_timestamp = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Timestamp del token"
    )
    
    # Campos para recuperación de contraseña
    reset_token = models.CharField(
        max_length=64,
        null=True,
        blank=True,
        verbose_name="Token de recuperación"
    )
    reset_token_timestamp = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Timestamp del token de recuperación"
    )
    reset_token_used = models.BooleanField(
        default=False,
        verbose_name="Token usado"
    )
    
    def __str__(self):
        return f"{self.nombre} ({self.email})"