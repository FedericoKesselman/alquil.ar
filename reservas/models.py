# reservas/models.py
from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import datetime, timedelta
from usuarios.models import Usuario, Sucursal
from maquinarias.models import Maquinaria


class Reserva(models.Model):
    ESTADO_CHOICES = [
        ('PENDIENTE_PAGO', 'Pendiente de Pago'),
        ('CONFIRMADA', 'Confirmada'),
        ('CANCELADA', 'Cancelada'),
        ('FINALIZADA', 'Finalizada'),
    ]
    
    TIPO_PAGO_CHOICES = [
        ('ONLINE', 'Pago Online'),
        ('PRESENCIAL', 'Pago Presencial'),
    ]

    # Información básica de la reserva
    cliente = models.ForeignKey(Usuario, on_delete=models.CASCADE, related_name='reservas')
    maquinaria = models.ForeignKey(Maquinaria, on_delete=models.CASCADE, related_name='reservas')
    sucursal_retiro = models.ForeignKey(Sucursal, on_delete=models.CASCADE, related_name='reservas_retiro')
    
    # Fechas y cantidad
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField()
    cantidad_solicitada = models.PositiveIntegerField()
    
    # Información de pago
    precio_total = models.DecimalField(max_digits=10, decimal_places=2)
    tipo_pago = models.CharField(max_length=12, choices=TIPO_PAGO_CHOICES, default='ONLINE')
    
    # Estado y seguimiento
    estado = models.CharField(max_length=15, choices=ESTADO_CHOICES, default='PENDIENTE_PAGO')
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_confirmacion = models.DateTimeField(null=True, blank=True)
    
    # Empleado que procesó la reserva (si es presencial)
    empleado_procesador = models.ForeignKey(
        Usuario, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='reservas_procesadas'
    )
    
    # Información adicional
    observaciones = models.TextField(blank=True, null=True)
    
    class Meta:
        verbose_name = "Reserva"
        verbose_name_plural = "Reservas"
        ordering = ['-fecha_creacion']

    def __str__(self):
        return f"Reserva #{self.id} - {self.cliente.get_full_name()} - {self.maquinaria.nombre}"

    def clean(self):
        """Validaciones del modelo"""
        errors = {}
        
        # Validar que las fechas sean coherentes
        if self.fecha_inicio and self.fecha_fin:
            if self.fecha_inicio >= self.fecha_fin:
                errors['fecha_fin'] = "La fecha de fin debe ser posterior a la fecha de inicio."
            
            if self.fecha_inicio < timezone.now().date():
                errors['fecha_inicio'] = "La fecha de inicio no puede ser anterior a hoy."
        
        # Validar días mínimos y máximos
        if self.fecha_inicio and self.fecha_fin and self.maquinaria:
            dias_reserva = (self.fecha_fin - self.fecha_inicio).days
            
            if dias_reserva < self.maquinaria.minimo:
                errors['fecha_fin'] = f"La reserva debe ser de mínimo {self.maquinaria.minimo} días."
            
            if dias_reserva > self.maquinaria.maximo:
                errors['fecha_fin'] = f"La reserva no puede exceder {self.maquinaria.maximo} días."
        
        # Validar que la cantidad solicitada sea válida
        if self.cantidad_solicitada and self.cantidad_solicitada <= 0:
            errors['cantidad_solicitada'] = "La cantidad debe ser mayor a 0."
        
        # Validar que el cliente sea realmente cliente
        if self.cliente and self.cliente.tipo != 'CLIENTE':
            # Si hay un empleado procesador, significa que es una reserva creada por un empleado
            if not self.empleado_procesador:
                errors['cliente'] = "Solo los usuarios tipo CLIENTE pueden hacer reservas."
        
        # Validar que el empleado procesador sea empleado (si existe)
        if self.empleado_procesador and self.empleado_procesador.tipo != 'EMPLEADO':
            errors['empleado_procesador'] = "Solo usuarios tipo EMPLEADO pueden procesar reservas."
        
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        
        # Calcular precio total si no está definido
        if not self.precio_total and self.maquinaria and self.fecha_inicio and self.fecha_fin:
            dias = (self.fecha_fin - self.fecha_inicio).days
            self.precio_total = self.maquinaria.precio_por_dia * dias * self.cantidad_solicitada
        
        super().save(*args, **kwargs)

    @property
    def dias_reserva(self):
        """Calcula la cantidad de días de la reserva"""
        if self.fecha_inicio and self.fecha_fin:
            return (self.fecha_fin - self.fecha_inicio).days
        return 0

    @property
    def precio_por_dia_total(self):
        """Precio por día considerando la cantidad solicitada"""
        return self.maquinaria.precio_por_dia * self.cantidad_solicitada

    def confirmar_pago(self, empleado=None):
        """Confirma el pago de la reserva"""
        if self.estado == 'PENDIENTE_PAGO':
            self.estado = 'CONFIRMADA'
            self.fecha_confirmacion = timezone.now()
            if empleado:
                self.empleado_procesador = empleado
            self.save()
            return True
        return False

    def cancelar(self):
        """Cancela la reserva"""
        if self.estado in ['PENDIENTE_PAGO', 'CONFIRMADA']:
            self.estado = 'CANCELADA'
            self.save()
            return True
        return False

    @classmethod
    def verificar_disponibilidad(cls, maquinaria, fecha_inicio, fecha_fin, cantidad_solicitada, sucursal=None, excluir_reserva=None):
        """
        Verifica si hay disponibilidad para una reserva en el rango de fechas especificado
        
        Args:
            maquinaria: Instancia de Maquinaria
            fecha_inicio: Fecha de inicio de la reserva
            fecha_fin: Fecha de fin de la reserva
            cantidad_solicitada: Cantidad de maquinarias solicitadas
            sucursal: Sucursal específica (opcional)
            excluir_reserva: ID de reserva a excluir de la verificación (para ediciones)
        
        Returns:
            dict: {
                'disponible': bool,
                'sucursales_disponibles': list,
                'mensaje': str
            }
        """
        # Obtener reservas que se solapan con el rango de fechas
        reservas_solapadas = cls.objects.filter(
            maquinaria=maquinaria,
            estado__in=['CONFIRMADA', 'PENDIENTE_PAGO'],
            fecha_inicio__lt=fecha_fin,
            fecha_fin__gt=fecha_inicio
        )
        
        if excluir_reserva:
            reservas_solapadas = reservas_solapadas.exclude(id=excluir_reserva)
        
        # Verificar disponibilidad por sucursal
        sucursales_disponibles = []
        
        if sucursal:
            # Verificar solo una sucursal específica
            sucursales_a_verificar = [sucursal]
        else:
            # Verificar todas las sucursales que tienen stock de esta maquinaria
            sucursales_a_verificar = Sucursal.objects.filter(
                stocks__maquinaria=maquinaria,
                stocks__stock__gte=cantidad_solicitada
            ).distinct()
        
        for suc in sucursales_a_verificar:
            # Obtener el stock disponible en esta sucursal
            stock_sucursal = maquinaria.stocks.filter(sucursal=suc).first()
            if not stock_sucursal or stock_sucursal.stock < cantidad_solicitada:
                continue
            
            # Calcular cuántas unidades están reservadas en esta sucursal para el rango de fechas
            reservas_sucursal = reservas_solapadas.filter(sucursal_retiro=suc)
            cantidad_reservada = sum([r.cantidad_solicitada for r in reservas_sucursal])
            
            # Verificar si hay suficiente stock disponible
            stock_disponible = stock_sucursal.stock - cantidad_reservada
            
            if stock_disponible >= cantidad_solicitada:
                sucursales_disponibles.append({
                    'sucursal': suc,
                    'stock_disponible': stock_disponible,
                    'stock_total': stock_sucursal.stock
                })
        
        disponible = len(sucursales_disponibles) > 0
        
        if disponible:
            mensaje = f"Disponible en {len(sucursales_disponibles)} sucursal(es)"
        else:
            mensaje = "No hay disponibilidad para las fechas y cantidad solicitadas"
        
        return {
            'disponible': disponible,
            'sucursales_disponibles': sucursales_disponibles,
            'mensaje': mensaje
        }

    @classmethod
    def get_reservas_por_periodo(cls, fecha_inicio, fecha_fin, maquinaria=None, sucursal=None):
        """Obtiene todas las reservas en un período específico"""
        reservas = cls.objects.filter(
            estado__in=['CONFIRMADA', 'PENDIENTE_PAGO'],
            fecha_inicio__lte=fecha_fin,
            fecha_fin__gte=fecha_inicio
        )
        
        if maquinaria:
            reservas = reservas.filter(maquinaria=maquinaria)
        
        if sucursal:
            reservas = reservas.filter(sucursal_retiro=sucursal)
        
        return reservas