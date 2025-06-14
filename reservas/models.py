# reservas/models.py
from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import datetime, timedelta
from usuarios.models import Usuario, Sucursal
from maquinarias.models import Maquinaria
import random
from django.core.mail import send_mail
from django.conf import settings
import socket
from django.core.mail import EmailMessage
import logging


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
    codigo_reserva = models.CharField(max_length=6, blank=True, null=True, unique=True)
    
    class Meta:
        verbose_name = "Reserva"
        verbose_name_plural = "Reservas"
        ordering = ['-fecha_creacion']

    def __str__(self):
        return f"Reserva #{self.id} - {self.cliente.get_full_name()} - {self.maquinaria.nombre}"

    def generar_codigo_reserva(self):
        """Genera un código único de 6 dígitos para la reserva"""
        import random
        import string
        
        # Generar un código de 6 dígitos
        codigo = ''.join(random.choices(string.digits, k=6))
        
        # Verificar que el código no exista
        while Reserva.objects.filter(codigo_reserva=codigo).exists():
            codigo = ''.join(random.choices(string.digits, k=6))
        
        # Asignar el código a la reserva
        self.codigo_reserva = codigo
        return codigo

    def enviar_codigo_reserva(self):
        """Envía el código de reserva por email al cliente"""
        # Generar el código si no existe
        if not self.codigo_reserva:
            self.generar_codigo_reserva()
            self.save()
        
        # Obtener la dirección de la sucursal
        sucursal_direccion = self.sucursal_retiro.direccion if self.sucursal_retiro else "No especificada"
        
        # Crear el mensaje con formato HTML
        mensaje = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <h2 style="color: #2c3e50;">Confirmación de Reserva</h2>
            <p>Estimado/a {self.cliente.get_full_name()},</p>
            <p>Su reserva ha sido confirmada. A continuación encontrará los detalles:</p>
            
            <div style="background-color: #f8f9fa; padding: 15px; border-radius: 5px; margin: 20px 0;">
                <p><strong>Detalles de la Reserva:</strong></p>
                <ul>
                    <li>Maquinaria: {self.maquinaria.nombre}</li>
                    <li>Cantidad: {self.cantidad_solicitada} unidad/es</li>
                    <li>Fecha de inicio: {self.fecha_inicio.strftime('%d/%m/%Y')}</li>
                    <li>Fecha de fin: {self.fecha_fin.strftime('%d/%m/%Y')}</li>
                    <li>Sucursal de retiro y devolución: {self.sucursal_retiro.nombre}</li>
                    <li>Dirección de retiro y devolución: {sucursal_direccion}</li>
                </ul>
                <p>Recuerde que debe devolver la maquinaria en la misma sucursal de la que fue retirada.</p>
            </div>
            
            <p>Su código de reserva es:</p>
            <div style="background-color: #e9ecef; padding: 15px; border-radius: 5px; text-align: center; margin: 20px 0;">
                <h1 style="color: #2c3e50; margin: 0; font-size: 32px;"><strong>{self.codigo_reserva}</strong></h1>
            </div>
            
            <p>Por favor, presente este código al momento de retirar la maquinaria.</p>
            
            <p style="color: #666; font-size: 0.9em; margin-top: 30px;">
                Si tiene alguna consulta, no dude en contactarnos.<br>
                Saludos cordiales,<br>
                El equipo de Alquil.ar
            </p>
        </body>
        </html>
        """
        
        # Configurar el email
        subject = f'Código de Reserva - {self.codigo_reserva}'
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
        try:
            email.send()
            return True
        except Exception as e:
            print(f"Error al enviar email: {str(e)}")
            return False

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

    def confirmar_reserva(self):
        """
        Confirma la reserva y actualiza su estado.
        Retorna True si la confirmación fue exitosa, False en caso contrario.
        """
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            # Verificar stock disponible
            if not self.actualizar_stock_maquinaria():
                return False
            
            # Actualizar estado de la reserva
            self.estado = 'CONFIRMADA'
            self.fecha_confirmacion = timezone.now()
            self.save()
            
            # Enviar email de confirmación
            try:
                self.enviar_codigo_reserva()
            except Exception as e:
                logger.error(f"Error al enviar código de reserva: {str(e)}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error al confirmar reserva: {str(e)}")
            return False

    def cancelar_reserva(self):
        """
        Cancela una reserva y restaura el stock si estaba confirmada.
        
        Returns:
            bool: True si se canceló exitosamente
        """
        if self.estado not in ['PENDIENTE_PAGO', 'CONFIRMADA']:
            return False
        
        # Si la reserva estaba confirmada, restaurar el stock
        if self.estado == 'CONFIRMADA':
            try:
                maquinaria_stock = self.maquinaria.stocks.get(sucursal=self.sucursal_retiro)
                maquinaria_stock.stock_disponible += self.cantidad_solicitada
                maquinaria_stock.save()
            except Exception as e:
                print(f"Error al restaurar stock: {str(e)}")
        
        # Cambiar estado a cancelada
        self.estado = 'CANCELADA'
        self.save()
        
        return True

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
        # Verificar disponibilidad por sucursal
        sucursales_disponibles = []
        
        if sucursal:
            # Verificar solo una sucursal específica si está activa
            if not sucursal.activa:
                return {
                    'disponible': False,
                    'sucursales_disponibles': [],
                    'mensaje': "La sucursal seleccionada no está activa"
                }
            sucursales_a_verificar = [sucursal]
        else:
            # Verificar todas las sucursales activas que tienen stock de esta maquinaria
            sucursales_a_verificar = Sucursal.objects.filter(
                activa=True,
                stocks__maquinaria=maquinaria,
                stocks__stock__gte=cantidad_solicitada
            ).distinct()
        
        for suc in sucursales_a_verificar:
            # Obtener el stock disponible en esta sucursal
            try:
                stock_sucursal = maquinaria.stocks.get(sucursal=suc)
                stock_disponible_actual = stock_sucursal.stock_disponible
            except:
                continue
            
            # Si no hay suficiente stock base, continuar con la siguiente sucursal
            if stock_disponible_actual < cantidad_solicitada:
                continue
            
            # Obtener reservas confirmadas que se solapan con el rango de fechas
            reservas_solapadas = cls.objects.filter(
                maquinaria=maquinaria,
                sucursal_retiro=suc,
                estado='CONFIRMADA',
                fecha_inicio__lt=fecha_fin,
                fecha_fin__gt=fecha_inicio
            )
            
            if excluir_reserva:
                reservas_solapadas = reservas_solapadas.exclude(id=excluir_reserva)
            
            # Calcular cuántas unidades están reservadas en el período
            cantidad_reservada = sum([r.cantidad_solicitada for r in reservas_solapadas])
            
            # Verificar si hay suficiente stock disponible considerando las reservas
            stock_final_disponible = stock_disponible_actual - cantidad_reservada
            
            if stock_final_disponible >= cantidad_solicitada:
                sucursales_disponibles.append({
                    'sucursal': suc,
                    'stock_disponible': stock_final_disponible,
                    'stock_total': stock_sucursal.stock,
                    'sucursal_id': suc.id
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

    def finalizar_reserva(self):
        """
        Finaliza una reserva y restaura el stock disponible.
        
        Returns:
            bool: True si se finalizó exitosamente
        """
        if self.estado != 'CONFIRMADA':
            return False
        
        # Restaurar el stock disponible
        try:
            maquinaria_stock = self.maquinaria.stocks.get(sucursal=self.sucursal_retiro)
            maquinaria_stock.stock_disponible += self.cantidad_solicitada
            maquinaria_stock.save()
        except Exception as e:
            print(f"Error al restaurar stock al finalizar reserva: {str(e)}")
            return False
        
        # Cambiar estado a finalizada
        self.estado = 'FINALIZADA'
        self.save()
        
        return True

    def actualizar_stock_maquinaria(self):
        """
        Verifica el stock disponible de la maquinaria.
        Retorna True si hay stock suficiente, False en caso contrario.
        """
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            # Obtener la maquinaria y su stock en la sucursal
            maquinaria = self.maquinaria
            try:
                maquinaria_stock = maquinaria.stocks.get(sucursal=self.sucursal_retiro)
                stock_total = maquinaria_stock.stock_disponible
            except Exception:
                raise ValueError(f"No hay stock registrado para esta maquinaria en la sucursal {self.sucursal_retiro.nombre}")
            
            logger.info(f"Verificando stock para maquinaria {maquinaria.nombre} en sucursal {self.sucursal_retiro.nombre}")
            logger.info(f"Stock total en sucursal: {stock_total}")
            
            # Obtener todas las reservas confirmadas que se superponen con las fechas de esta reserva
            reservas_superpuestas = Reserva.objects.filter(
                maquinaria=maquinaria,
                sucursal_retiro=self.sucursal_retiro,
                estado='CONFIRMADA',
                fecha_inicio__lte=self.fecha_fin,
                fecha_fin__gte=self.fecha_inicio
            ).exclude(id=self.id)  # Excluir esta reserva si ya existe
            
            # Calcular el stock reservado en las fechas superpuestas
            stock_reservado = sum(reserva.cantidad_solicitada for reserva in reservas_superpuestas)
            logger.info(f"Stock reservado en fechas superpuestas: {stock_reservado}")
            
            # Verificar si hay suficiente stock
            stock_disponible = stock_total - stock_reservado
            logger.info(f"Stock disponible: {stock_disponible}")
            
            if self.cantidad_solicitada > stock_disponible:
                # Obtener detalles de las reservas superpuestas
                reservas_info = []
                for reserva in reservas_superpuestas:
                    reservas_info.append(
                        f"Reserva del {reserva.fecha_inicio} al {reserva.fecha_fin} "
                        f"({reserva.cantidad_solicitada} unidad/es)"
                    )
                
                mensaje_error = (
                    f"No hay stock suficiente para las fechas solicitadas.\n"
                    f"Stock total en sucursal: {stock_total}\n"
                    f"Ya reservado: {stock_reservado}\n"
                    f"Solicitado: {self.cantidad_solicitada}\n"
                    f"Stock disponible: {stock_disponible}\n\n"
                    f"Reservas existentes en estas fechas:\n" + 
                    "\n".join(reservas_info)
                )
                logger.warning(mensaje_error)
                raise ValueError(mensaje_error)
            
            return True
            
        except ValueError as e:
            raise e
        except Exception as e:
            logger.error(f"Error al verificar stock: {str(e)}")
            return False