from django.db import models
from usuarios.models import Usuario
from reservas.models import Reserva

class CalificacionCliente(models.Model):
    """
    Modelo para almacenar el historial de calificaciones de los clientes.
    Cada calificación está asociada a una reserva específica.
    
    Lógica del sistema de calificaciones:
    - Todos los clientes comienzan con una calificación inicial de 5 estrellas.
    - Cuando se asignan nuevas calificaciones, estas se promedian CON la calificación inicial de 5 estrellas.
    - El promedio se calcula como: (calificación_inicial + suma_calificaciones_recibidas) / (1 + número_calificaciones_recibidas)
    
    Ejemplo:
    - Cliente nuevo: 5 estrellas (por defecto)
    - Recibe 1 estrella: (5 + 1) / 2 = 3 estrellas
    - Recibe otra calificación de 3 estrellas: (5 + 1 + 3) / 3 = 3 estrellas
    """
    cliente = models.ForeignKey(
        Usuario,
        on_delete=models.CASCADE,
        related_name='calificaciones',
        verbose_name="Cliente"
    )
    reserva = models.OneToOneField(
        Reserva,
        on_delete=models.CASCADE,
        related_name='calificacion_cliente',
        verbose_name="Reserva"
    )
    calificacion = models.FloatField(
        verbose_name="Calificación",
        help_text="Calificación del cliente en escala de 0.5 a 5 estrellas"
    )
    fecha_calificacion = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Fecha de calificación"
    )
    observaciones = models.TextField(
        blank=True,
        null=True,
        verbose_name="Observaciones"
    )

    class Meta:
        verbose_name = "Calificación de cliente"
        verbose_name_plural = "Calificaciones de clientes"
        ordering = ['-fecha_calificacion']

    def __str__(self):
        return f"Calificación de {self.cliente.get_full_name()} - {self.calificacion} estrellas"

def obtener_calificacion_promedio_cliente(cliente_id):
    """
    Obtiene la calificación promedio de un cliente
    Todos los clientes comienzan con una calificación inicial de 5 estrellas
    El promedio se calcula como: (calificación_inicial + suma_calificaciones_recibidas) / (1 + número_calificaciones_recibidas)
    
    Args:
        cliente_id: ID del cliente
    
    Returns:
        float: Calificación promedio redondeada a un decimal, o None si el cliente no existe
    """
    try:
        # Convertir cliente_id a entero si es una cadena
        if isinstance(cliente_id, str) and cliente_id.isdigit():
            cliente_id = int(cliente_id)
            
        # Verificar que el cliente exista
        cliente = Usuario.objects.get(id=cliente_id, tipo="CLIENTE")
        
        # Obtener todas las calificaciones del cliente
        calificaciones = CalificacionCliente.objects.filter(cliente=cliente)
        
        if not calificaciones.exists():
            # Si no tiene calificaciones, devolver la calificación inicial (5)
            return 5.0
        
        # Sumar todas las calificaciones recibidas
        suma_calificaciones = sum(c.calificacion for c in calificaciones)
        
        # Calcular el promedio: (5 + suma) / (1 + count)
        # Incluimos la calificación inicial de 5 estrellas
        promedio = (5 + suma_calificaciones) / (1 + calificaciones.count())
        
        # Redondear a múltiplos de 0.5
        return round(promedio * 2) / 2
    except Usuario.DoesNotExist:
        return None
    except Exception as e:
        # En caso de cualquier error, loggear y devolver None
        print(f"Error al calcular calificación para cliente {cliente_id}: {str(e)}")
        return None
