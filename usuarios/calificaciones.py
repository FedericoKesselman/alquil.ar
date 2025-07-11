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
