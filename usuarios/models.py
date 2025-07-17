# usuarios/models.py
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator, MinValueValidator, MaxValueValidator
from django.db.models.signals import pre_save
from django.dispatch import receiver
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.core.mail import EmailMessage
from django.conf import settings

# Aca van las declaraciones de las tablas de la base de datos

class Sucursal(models.Model):
    nombre = models.CharField(max_length=100)
    direccion = models.CharField(max_length=200)
    telefono = models.CharField(max_length=20, default="0")  # ✅ Campo teléfono agregado
    latitud = models.FloatField()
    longitud = models.FloatField()
    activa = models.BooleanField(default=True)
    # Nuevo campo para identificar sucursales eliminadas
    es_placeholder = models.BooleanField(default=False)

    def __str__(self):
        return self.nombre
        
    def clean(self):
        """
        Validar que no se pueda desactivar una sucursal si tiene reservas activas
        """
        # Si estamos desactivando la sucursal (cambiando activa de True a False)
        if not self.activa and self.pk:
            # Verificar si el valor original era True (estamos desactivando)
            original = Sucursal.objects.get(pk=self.pk)
            if original.activa:
                # Importar aquí para evitar importaciones circulares
                from reservas.models import Reserva
                
                # Verificar si hay reservas activas para esta sucursal
                active_reservations = Reserva.objects.filter(
                    sucursal_retiro=self
                ).exclude(
                    estado='FINALIZADA'
                ).exists()
                
                if active_reservations:
                    from django.core.exceptions import ValidationError
                    # Usar un error simple de texto sin formato de diccionario
                    raise ValidationError("No se puede desactivar una sucursal con reservas en curso")
        
        return super().clean()
        
    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)
        
    def delete(self, *args, **kwargs):
        """
        Override the delete method to prevent deletion if the branch
        has machinery associated or active reservations
        """
        # Check if there are any machinery stocks associated with this sucursal
        has_machinery = self.stocks.exists()
        
        if has_machinery:
            from django.db.models.deletion import ProtectedError
            raise ProtectedError(
                f"No se puede eliminar la sucursal '{self.nombre}' porque tiene maquinarias asociadas. Elimine primero las maquinarias de esta sucursal.",
                self
            )
        
        # Import here to avoid circular imports
        from reservas.models import Reserva
        
        # Check if there are any non-finalized reservations for this branch
        non_finalized_reservations = Reserva.objects.filter(
            sucursal_retiro=self
        ).exclude(
            estado='FINALIZADA'
        )
        
        if non_finalized_reservations.exists():
            from django.db.models.deletion import ProtectedError
            raise ProtectedError(
                f"No se puede eliminar la sucursal '{self.nombre}' porque tiene reservas que no están finalizadas.",
                self
            )
        
        # Check if there are any finalized reservations for this branch
        finalized_reservations = Reserva.objects.filter(
            sucursal_retiro=self, 
            estado='FINALIZADA'
        ).exists()
        
        if finalized_reservations:
            # Get or create a placeholder for sucursal
            from usuarios.views import get_or_create_deleted_sucursal_placeholder
            sucursal_placeholder = get_or_create_deleted_sucursal_placeholder()
            
            # Transfer all finalized reservations to the placeholder
            Reserva.objects.filter(
                sucursal_retiro=self,
                estado='FINALIZADA'
            ).update(sucursal_retiro=sucursal_placeholder)
            
            # Now we can safely delete the sucursal
            return super().delete(*args, **kwargs)
        
        # If there are no reservations at all, just delete normally
        super().delete(*args, **kwargs)

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
    
    def get_full_name(self):
        """Retorna el nombre completo del usuario"""
        # Si tiene first_name y last_name definidos, usarlos
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        # De lo contrario, usar el campo nombre personalizado
        elif self.nombre:
            return self.nombre
        # Como último recurso, usar el username
        else:
            return self.username
        
    def _redondear_a_medio(self, valor):
        """
        Redondea un valor al 0.5 más cercano de forma consistente.
        Ejemplos: 1.2 -> 1.0, 1.25 -> 1.5, 1.7 -> 1.5, 1.75 -> 2.0
        """
        import math
        # Multiplicamos por 2, redondeamos normalmente hacia arriba en caso de empate, y dividimos por 2
        return math.floor(valor * 2 + 0.5) / 2

    def actualizar_calificacion_promedio(self):
        """
        Actualiza la calificación promedio del cliente basado en su historial de calificaciones.
        Todos los clientes comienzan con una calificación inicial de 5 estrellas.
        Las nuevas calificaciones se promedian CON la calificación inicial de 5 estrellas.
        
        Ejemplo: Cliente con calificación inicial de 5, recibe una calificación de 1
        Promedio = (5 + 1) / 2 = 3.0 estrellas
        """
        from usuarios.calificaciones import CalificacionCliente
        
        # Obtener todas las calificaciones del cliente
        calificaciones = CalificacionCliente.objects.filter(cliente=self)
        
        # Calcular el promedio considerando la calificación inicial de 5
        if calificaciones.exists():
            # Sumar todas las calificaciones registradas
            total_calificaciones = sum(c.calificacion for c in calificaciones)
            # Incluir la calificación inicial de 5 en el cálculo
            total_calificaciones += 5.0
            # Contar todas las calificaciones + la inicial
            total_count = calificaciones.count() + 1
            
            # Calcular el promedio
            promedio = total_calificaciones / total_count
            
            # Actualizar la calificación del cliente (redondear al 0.5 más cercano)
            # Usamos una función de redondeo personalizada para evitar problemas con round half to even
            self.calificacion = self._redondear_a_medio(promedio)
            self.save(update_fields=['calificacion'])
        else:
            # Si no hay calificaciones, mantener la calificación inicial de 5
            self.calificacion = 5.0
            self.save(update_fields=['calificacion'])
        
        return self.calificacion

# Signal para prevenir desactivación de sucursal con reservas activas
@receiver(pre_save, sender=Sucursal)
def prevent_sucursal_deactivation(sender, instance, **kwargs):
    """
    Prevent deactivation of a Sucursal if it has active reservations
    """
    # Only run for existing branches, not for new ones
    if not instance.pk:
        return
    
    # Check if we're deactivating the branch
    try:
        # Get the original branch from the database
        original = Sucursal.objects.get(pk=instance.pk)
        
        # If we're changing from active to inactive
        if original.activa and not instance.activa:
            # Check for active reservations
            from reservas.models import Reserva
            has_active_reservations = Reserva.objects.filter(
                sucursal_retiro=instance
            ).exclude(
                estado='FINALIZADA'
            ).exists()
            
            if has_active_reservations:
                # Use a simple error message without JSON formatting
                raise ValidationError("No se puede desactivar una sucursal con reservas en curso")
    except Sucursal.DoesNotExist:
        # This should not happen, but just in case
        pass


class Cupon(models.Model):
    """
    Modelo para representar cupones de descuento asignados a clientes específicos.
    Pueden ser de tipo porcentaje o monto fijo.
    """
    TIPO_CHOICES = [
        ('PORCENTAJE', 'Porcentaje'),
        ('MONTO', 'Monto Fijo'),
    ]
    
    cliente = models.ForeignKey('Usuario', on_delete=models.CASCADE, related_name='cupones', 
                              limit_choices_to={'tipo': 'CLIENTE'})
    codigo = models.CharField(max_length=20, unique=True)
    tipo = models.CharField(max_length=10, choices=TIPO_CHOICES)
    valor = models.DecimalField(max_digits=10, decimal_places=2)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_vencimiento = models.DateField()
    usado = models.BooleanField(default=False)
    reserva_uso = models.OneToOneField('reservas.Reserva', on_delete=models.SET_NULL, 
                                     null=True, blank=True, related_name='cupon_aplicado')
    
    class Meta:
        verbose_name = 'Cupón'
        verbose_name_plural = 'Cupones'
        ordering = ['-fecha_creacion']
    
    def __str__(self):
        if self.tipo == 'PORCENTAJE':
            return f"Cupón {self.valor}% para {self.cliente.nombre}"
        else:
            return f"Cupón ${self.valor} para {self.cliente.nombre}"
    
    def is_valid(self):
        """Verifica si el cupón está vigente y no ha sido usado."""
        today = timezone.now().date()
        return not self.usado and self.fecha_vencimiento >= today
    
    def clean(self):
        """Validaciones para el cupón"""
        # Validar que el valor sea positivo
        if self.valor <= 0:
            raise ValidationError("El valor del cupón debe ser mayor a cero.")
            
        # Validar que los porcentajes estén entre 1 y 99
        if self.tipo == 'PORCENTAJE' and (self.valor < 1 or self.valor > 99):
            raise ValidationError("El porcentaje debe estar entre 1 y 99.")
            
        # Validar que la fecha de vencimiento sea futura
        today = timezone.now().date()
        if self.fecha_vencimiento < today:
            raise ValidationError("La fecha de vencimiento debe ser futura.")
            
        # Validar que el cliente sea de tipo CLIENTE
        if self.cliente_id and self.cliente.tipo != 'CLIENTE':
            raise ValidationError("El cupón solo puede asignarse a usuarios de tipo CLIENTE.")
    
    def enviar_notificacion_cupon_creado(self):
        """Envía un correo electrónico al cliente notificando que se le ha asignado un nuevo cupón"""
        try:
            # Determinar el texto del valor según el tipo de cupón
            if self.tipo == 'PORCENTAJE':
                valor_texto = f"{self.valor}% de descuento"
                valor_display = f"{self.valor}%"
            else:
                valor_texto = f"${self.valor} de descuento"
                valor_display = f"${self.valor:,.2f}"
            
            # Formatear la fecha de vencimiento
            fecha_vencimiento_str = self.fecha_vencimiento.strftime('%d/%m/%Y')
            
            # Crear el mensaje con formato HTML
            mensaje = f"""
            <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <h2 style="color: #2c3e50;">¡Nuevo Cupón de Descuento Asignado!</h2>
                <p>Estimado/a {self.cliente.get_full_name()},</p>
                <p>Nos complace informarle que se le ha asignado un nuevo cupón de descuento en Alquil.ar:</p>
                
                <div style="background-color: #e8f5e8; padding: 20px; border-radius: 8px; margin: 20px 0; border-left: 5px solid #28a745;">
                    <h3 style="color: #28a745; margin-top: 0;">🎟️ Detalles del Cupón</h3>
                    <ul style="list-style: none; padding: 0;">
                        <li style="margin: 8px 0;"><strong>Código:</strong> <span style="background-color: #f8f9fa; padding: 4px 8px; border-radius: 4px; font-family: monospace; font-size: 1.1em;">{self.codigo}</span></li>
                        <li style="margin: 8px 0;"><strong>Descuento:</strong> {valor_display}</li>
                        <li style="margin: 8px 0;"><strong>Fecha de vencimiento:</strong> {fecha_vencimiento_str}</li>
                    </ul>
                </div>
                
                <div style="background-color: #f8f9fa; padding: 15px; border-radius: 5px; margin: 20px 0;">
                    <h4 style="color: #495057; margin-top: 0;">💡 ¿Cómo usar tu cupón?</h4>
                    <ol>
                        <li>Selecciona la maquinaria que deseas alquilar</li>
                        <li>Completa los datos de tu reserva</li>
                        <li>En el paso de confirmación, selecciona alguno de tus cupones disponibles</strong></li>
                        <li>¡Disfruta tu descuento de {valor_display}!</li>
                    </ol>
                </div>
                
                <div style="background-color: #fff3cd; padding: 12px; border-radius: 5px; margin: 20px 0; border-left: 4px solid #ffc107;">
                    <p style="margin: 0; color: #856404;"><strong>⚠️ Recordatorio:</strong> Este cupón vence el {fecha_vencimiento_str}. ¡No olvides usarlo antes de esa fecha!</p>
                </div>
                
                <p>Gracias por confiar en Alquil.ar para sus necesidades de alquiler de maquinaria.</p>
                
                <p style="color: #666; font-size: 0.9em; margin-top: 30px;">
                    Si tiene alguna consulta sobre este cupón, no dude en contactarnos.<br>
                    Saludos cordiales,<br>
                    El equipo de Alquil.ar
                </p>
            </body>
            </html>
            """
            
            # Configurar el email
            subject = f'¡Nuevo Cupón de Descuento Disponible! - {valor_display}'
            from_email = settings.EMAIL_HOST_USER
            to_email = self.cliente.email
            
            # Crear el mensaje
            email = EmailMessage(
                subject=subject,
                body=mensaje,
                from_email=from_email,
                to=[to_email]
            )
            email.content_subtype = "html"  # Indicar que el contenido es HTML
            
            # Enviar el email
            email.send()
            return True
            
        except Exception as e:
            print(f"Error al enviar email de notificación de cupón: {str(e)}")
            return False
    
    def save(self, *args, **kwargs):
        """Override del método save para enviar email cuando se crea un nuevo cupón"""
        # Verificar si es un nuevo cupón (no tiene pk)
        is_new = self.pk is None
        
        # Llamar al método save original
        super().save(*args, **kwargs)
        
        # Si es un nuevo cupón, enviar email de notificación
        if is_new:
            try:
                self.enviar_notificacion_cupon_creado()
            except Exception as e:
                print(f"Error al enviar notificación de cupón creado: {str(e)}")