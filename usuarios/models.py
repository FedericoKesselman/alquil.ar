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

    def get_stock_disponible(self, maquinaria, fecha_inicio, fecha_fin, cantidad_solicitada):
        """
        Calcula el stock disponible de una maquinaria en esta sucursal para un rango de fechas
        """
        from reservas.models import Reserva
        
        # Obtener el stock total de la maquinaria en esta sucursal
        try:
            stock_total = self.stocks.get(maquinaria=maquinaria).stock
        except:
            return 0

        # Obtener todas las reservas que se solapan con el rango de fechas
        reservas_solapadas = Reserva.objects.filter(
            sucursal_retiro=self,
            maquinaria=maquinaria,
            estado__in=['pendiente', 'confirmada', 'en_curso'],
            fecha_inicio__lte=fecha_fin,
            fecha_fin__gte=fecha_inicio
        )

        # Calcular el máximo de unidades reservadas en cualquier día del rango
        max_reservadas = 0
        for reserva in reservas_solapadas:
            max_reservadas = max(max_reservadas, reserva.cantidad_solicitada)

        # El stock disponible es el stock total menos el máximo de unidades reservadas
        return stock_total - max_reservadas

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
    fecha_nacimiento = models.DateField()  
    sucursal = models.ForeignKey(Sucursal, on_delete=models.SET_NULL, null=True, blank=True)
    calificacion = models.FloatField(
        default=5.0, 
        verbose_name="Calificación del cliente",
        help_text="Calificación del cliente en escala de 0.5 a 5 estrellas"
    )
    
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
        
    def actualizar_calificacion_promedio(self):
        """
        Actualiza la calificación promedio del cliente basado en su historial de calificaciones.
        """
        from usuarios.calificaciones import CalificacionCliente
        
        # Obtener todas las calificaciones del cliente
        calificaciones = CalificacionCliente.objects.filter(cliente=self)
        
        if calificaciones.exists():
            # Calcular el promedio
            total_calificaciones = sum(c.calificacion for c in calificaciones)
            promedio = total_calificaciones / calificaciones.count()
            
            # Actualizar la calificación del cliente
            self.calificacion = round(promedio * 2) / 2  # Redondear al 0.5 más cercano
            self.save(update_fields=['calificacion'])
        
        return self.calificacion