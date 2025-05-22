# usuarios/models.py
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator

class Sucursal(models.Model):
    nombre = models.CharField(max_length=100)
    direccion = models.CharField(max_length=200)
    telefono_regex = RegexValidator(
        regex=r'^\+?1?\d{9,15}$',
        message="El teléfono debe estar en formato: '+999999999'."
    )
    telefono = models.CharField(validators=[telefono_regex], max_length=17)
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
    
    tipo = models.CharField(max_length=10, choices=TIPO_CHOICES, default='CLIENTE')
    dni = models.CharField(max_length=20, unique=True, null=True, blank=True)
    telefono = models.CharField(max_length=20, null=True, blank=True)
    direccion = models.CharField(max_length=200, null=True, blank=True)
    sucursal = models.ForeignKey(Sucursal, on_delete=models.SET_NULL, null=True, blank=True)
    
    def __str__(self):
        return f"{self.get_full_name()} ({self.get_tipo_display()})"