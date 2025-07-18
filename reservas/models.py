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


class Reembolso(models.Model):
    """
    Modelo para registrar los reembolsos realizados a clientes.
    Guarda información sobre el cliente, monto reembolsado y la reserva asociada.
    """
    cliente = models.ForeignKey(Usuario, on_delete=models.CASCADE, related_name='reembolsos', null=True)
    reserva = models.ForeignKey('Reserva', on_delete=models.CASCADE, related_name='reembolsos', null=True)
    monto = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    fecha_reembolso = models.DateTimeField(auto_now_add=True)
    dni_cliente = models.CharField(max_length=20, blank=True, default='')
    
    def __str__(self):
        reserva_id = self.reserva.id if self.reserva else 'N/A'
        return f"Reembolso #{self.id} - Reserva #{reserva_id} - ${self.monto}"
    
    def save(self, *args, **kwargs):
        # Asegurar que el DNI del cliente se guarde correctamente
        if not self.dni_cliente and self.cliente:
            self.dni_cliente = self.cliente.dni
        super().save(*args, **kwargs)


class Reserva(models.Model):
    ESTADO_CHOICES = [
        ('PENDIENTE_PAGO', 'Pendiente de Pago'),
        ('CONFIRMADA', 'Confirmada'),
        ('ENTREGADA', 'Entregada'),
        ('CANCELADA', 'Cancelada'),
        ('FINALIZADA', 'Finalizada'),
        ('NO_DEVUELTA', 'No Devuelta'),
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
    
    # Información del cupón aplicado
    descuento_aplicado = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    precio_antes_descuento = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    
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

    def enviar_confirmacion_reembolso(self, monto_reembolso, porcentaje_reembolso):
        """Envía un correo electrónico al cliente con los detalles del reembolso"""
        # Obtener la dirección de la sucursal
        sucursal_direccion = self.sucursal_retiro.direccion if self.sucursal_retiro else "No especificada"
        
        # Mensaje adicional basado en el monto del reembolso
        mensaje_reembolso = ""
        if porcentaje_reembolso > 0:
            mensaje_reembolso = f"""
            <div style="background-color: #e9ecef; padding: 15px; border-radius: 5px; margin: 20px 0;">
                <p><strong>Detalles del Reembolso:</strong></p>
                <p>Monto a reembolsar: ${monto_reembolso:.2f} ({porcentaje_reembolso}% del total)</p>
                <p>Para recibir su reembolso, por favor acérquese a la sucursal {self.sucursal_retiro.nombre} 
                con su documento de identidad y el código de reserva.</p>
                <p>Dirección: {sucursal_direccion}</p>
            </div>
            """
        else:
            mensaje_reembolso = """
            <div style="background-color: #f8d7da; padding: 15px; border-radius: 5px; margin: 20px 0;">
                <p><strong>Información sobre el Reembolso:</strong></p>
                <p>De acuerdo a nuestra política de cancelación, su reserva no califica para un reembolso monetario
                debido al tiempo transcurrido hasta la fecha de inicio del alquiler.</p>
                <p>Si tiene alguna duda, puede contactarnos o acercarse a la sucursal para más información.</p>
            </div>
            """
        
        # Crear el mensaje con formato HTML
        mensaje = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <h2 style="color: #2c3e50;">Confirmación de Cancelación de Reserva</h2>
            <p>Estimado/a {self.cliente.get_full_name()},</p>
            <p>Su solicitud de cancelación de reserva ha sido procesada correctamente. A continuación encontrará los detalles:</p>
            
            <div style="background-color: #f8f9fa; padding: 15px; border-radius: 5px; margin: 20px 0;">
                <p><strong>Detalles de la Reserva Cancelada:</strong></p>
                <ul>
                    <li>Código de Reserva: {self.codigo_reserva}</li>
                    <li>Maquinaria: {self.maquinaria.nombre}</li>
                    <li>Cantidad: {self.cantidad_solicitada} unidad/es</li>
                    <li>Fecha de inicio (original): {self.fecha_inicio.strftime('%d/%m/%Y')}</li>
                    <li>Fecha de fin (original): {self.fecha_fin.strftime('%d/%m/%Y')}</li>
                    <li>Sucursal: {self.sucursal_retiro.nombre}</li>
                </ul>
            </div>
            
            {mensaje_reembolso}
            
            <p style="color: #666; font-size: 0.9em; margin-top: 30px;">
                Si tiene alguna consulta, no dude en contactarnos.<br>
                Saludos cordiales,<br>
                El equipo de Alquil.ar
            </p>
        </body>
        </html>
        """
        
        # Configurar el email
        subject = f'Confirmación de Cancelación - Reserva {self.codigo_reserva}'
        from_email = settings.EMAIL_HOST_USER
        to_email = self.cliente.email
        
        # Crear el mensaje
        from django.core.mail import EmailMessage
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
            print(f"Error al enviar email de reembolso: {str(e)}")
            return False

    def clean(self):
        """Validaciones del modelo"""
        errors = {}
        
        # Validar que las fechas sean coherentes
        if self.fecha_inicio and self.fecha_fin:
            if self.fecha_inicio > self.fecha_fin:
                errors['fecha_fin'] = "La fecha de fin debe ser posterior a la fecha de inicio."
            
            # Solo validar que la fecha no sea pasada si es una reserva nueva
            if not self.pk and self.fecha_inicio < timezone.now().date():
                errors['fecha_inicio'] = "La fecha de inicio no puede ser anterior a hoy."
        
        # Validar días mínimos y máximos
        if self.fecha_inicio and self.fecha_fin and self.maquinaria:
            dias_reserva = (self.fecha_fin - self.fecha_inicio).days + 1  # <--- CORREGIDO
            
            if dias_reserva < self.maquinaria.minimo:
                errors['fecha_fin'] = f"La reserva debe ser de mínimo {self.maquinaria.minimo} días."
            
            if dias_reserva > self.maquinaria.maximo:
                errors['fecha_fin'] = f"La reserva no puede exceder {self.maquinaria.maximo} días."
        
        # Validar que la cantidad solicitada sea válida
        if self.cantidad_solicitada and self.cantidad_solicitada <= 0:
            errors['cantidad_solicitada'] = "La cantidad debe ser mayor a 0."
        
        # Validar que el cliente sea realmente cliente (solo si el cliente está establecido)
        # Esto es necesario porque durante la validación del formulario, cliente puede no estar establecido todavía
        try:
            if self.cliente and self.cliente.tipo != 'CLIENTE':
                # Si hay un empleado procesador, significa que es una reserva creada por un empleado
                if not self.empleado_procesador:
                    errors['cliente'] = "Solo los usuarios tipo CLIENTE pueden hacer reservas."
        except Reserva.cliente.RelatedObjectDoesNotExist:
            # El cliente aún no está establecido, lo cual es válido durante la validación del formulario
            pass
        
        # Validar que el empleado procesador sea empleado (si existe)
        if self.empleado_procesador and self.empleado_procesador.tipo != 'EMPLEADO':
            errors['empleado_procesador'] = "Solo usuarios tipo EMPLEADO pueden procesar reservas."
        
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        
        # Calcular precio total si no está definido, con posible recargo
        if not self.precio_total and self.maquinaria and self.fecha_inicio and self.fecha_fin:
            dias = (self.fecha_fin - self.fecha_inicio).days + 1  # +1 para incluir el día de inicio
            precio_por_dia, _ = self.maquinaria.get_precio_para_cliente(self.cliente)
            precio_base = precio_por_dia * dias * self.cantidad_solicitada
            
            # Guardar el precio antes del descuento si hay descuento
            if self.descuento_aplicado > 0 and not self.precio_antes_descuento:
                self.precio_antes_descuento = precio_base
                self.precio_total = precio_base - self.descuento_aplicado
            else:
                self.precio_total = precio_base
        
        super().save(*args, **kwargs)

    @property
    def dias_reserva(self):
        """Calcula la cantidad de días de la reserva"""
        if self.fecha_inicio and self.fecha_fin:
            return (self.fecha_fin - self.fecha_inicio).days + 1  # +1 para incluir el día de inicio
        return 0    @property
    def precio_por_dia_total(self):
        """Precio por día considerando la cantidad solicitada y posible recargo"""
        precio_por_dia, _ = self.maquinaria.get_precio_para_cliente(self.cliente)
        return precio_por_dia * self.cantidad_solicitada
        
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
        # For NULL estado (incomplete reservations), just return True but don't delete here
        # The view will handle the deletion for these
        if self.estado is None:
            return True
            
        # For regular reservations with valid estado
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
        Cancela una reserva. No modifica el stock de la maquinaria.
        No permite cancelar reservas activas (dentro del período de alquiler)
        para clientes, pero sí para empleados y administradores.
        
        Returns:
            bool: True si se canceló exitosamente
        """
        # Verificar que la reserva esté en estado válido para cancelación
        if self.estado not in ['PENDIENTE_PAGO', 'CONFIRMADA']:
            return False
        
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
                    'sucursal_id': suc.id                })
                
        disponible = len(sucursales_disponibles) > 0
        
        if disponible:
            mensaje = f"Disponible en {len(sucursales_disponibles)} sucursal(es)"
        else:
            mensaje = "No hay disponibilidad para las fechas y cantidad solicitadas"
        
        return {
            'disponible': disponible,            'sucursales_disponibles': sucursales_disponibles,
            'mensaje': mensaje
        }
        
    def finalizar_reserva(self):
        """
        Finaliza una reserva. No modifica el stock de la maquinaria.
        
        Returns:
            bool: True si se finalizó exitosamente
        """
        # Permitir finalizar reservas que estén en estado CONFIRMADA, CANCELADA, ENTREGADA o NO_DEVUELTA
        if self.estado not in ['CONFIRMADA', 'CANCELADA', 'ENTREGADA', 'NO_DEVUELTA']:
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
    
    def is_active(self):
        """
        Verifica si la reserva está activa, es decir, si la fecha actual
        está dentro del rango de fecha_inicio y fecha_fin.        
        Returns:
            bool: True si la fecha actual está en el rango, False en caso contrario
        """
        today = timezone.now().date()
        return self.estado == 'CONFIRMADA' and self.fecha_inicio <= today <= self.fecha_fin
        
    def reembolsar_reserva(self):
        """
        Marca la reserva como cancelada por el cliente.
        No modifica el stock de la maquinaria.
        El reembolso efectivo solo se registra cuando un empleado finaliza la reserva cancelada.
        
        No permite reembolsar reservas activas (dentro del período de alquiler).
        
        Returns:
            bool: True si la cancelación se procesó correctamente, False en caso contrario.
        """
        # Verificar que la reserva esté confirmada
        if self.estado != 'CONFIRMADA':
            return False
        
        # Verificar si la reserva está dentro de su período activo
        today = timezone.now().date()
        if self.fecha_inicio <= today <= self.fecha_fin:
            # No permitir reembolso para reservas activas
            return False
            
        # Cambiar estado a cancelada
        self.estado = 'CANCELADA'
        self.save()
        
        return True
        
    def calcular_monto_reembolso(self, fecha_actual=None):
        """
        Calcula el monto a reembolsar según la política de la maquinaria.
        
        Args:
            fecha_actual: La fecha desde la que calcular los días hasta el inicio 
                         (por defecto la fecha actual del sistema)
                         
        Returns:
            tuple: (monto_reembolso, porcentaje_reembolso)
        """
        if not fecha_actual:
            fecha_actual = timezone.now().date()
            
        # Calcular días hasta el inicio de la reserva
        dias_hasta_inicio = (self.fecha_inicio - fecha_actual).days
        
        # Determinar el porcentaje de reembolso según los días
        if dias_hasta_inicio > self.maquinaria.cantDias_total:
            # Reembolso total (100%)
            return float(self.precio_total), 100
        elif dias_hasta_inicio > self.maquinaria.cantDias_parcial:
            # Reembolso parcial (50%)
            return float(self.precio_total) * 0.5, 50
        else:
            # Sin reembolso (0%)
            return 0, 0
    
    def verificar_vencimiento(self):
        """
        Verifica si la fecha de fin ha pasado sin que la reserva haya sido finalizada,
        y en ese caso actualiza el estado a NO_DEVUELTA.
        
        Returns:
            bool: True si se actualizó el estado, False en caso contrario
        """
        # Solo comprobar reservas ENTREGADAS (anteriormente solo comprobaba CONFIRMADAS)
        if self.estado != 'ENTREGADA':
            return False
            
        # Si la fecha de fin ha pasado y aún no está finalizada o marcada como no devuelta
        # Una reserva se considera vencida cuando su día de fin ya ha pasado completamente
        if self.fecha_fin < timezone.now().date():
            self.estado = 'NO_DEVUELTA'
            self.save(update_fields=['estado'])
            return True
            
        return False
        
    @classmethod
    def actualizar_reservas_vencidas(cls):
        """
        Método de clase que actualiza todas las reservas entregadas que ya han pasado su fecha
        de fin y las marca como NO_DEVUELTA.
        
        Returns:
            int: Número de reservas actualizadas
        """
        # Obtener todas las reservas entregadas cuya fecha de fin ha pasado
        # Una reserva se considera vencida cuando su día de fin ya ha pasado completamente
        hoy = timezone.now().date()
        contador = cls.objects.filter(
            estado='ENTREGADA',
            fecha_fin__lt=hoy  # fecha_fin < hoy significa que el día de fin ya pasó
        ).update(estado='NO_DEVUELTA')
            
        return contador
        
    @classmethod
    def limpiar_reservas_abandonadas(cls):
        """
        Elimina reservas que han permanecido en estado PENDIENTE_PAGO por más de 30 minutos.
        Estas son consideradas abandonadas (el cliente comenzó el proceso de pago pero no lo completó).
        
        Returns:
            int: Número de reservas eliminadas
        """
        # Definir el tiempo límite (30 minutos atrás)
        tiempo_limite = timezone.now() - timedelta(minutes=30)
        
        # Identificar reservas abandonadas
        reservas_abandonadas = cls.objects.filter(
            estado='PENDIENTE_PAGO',
            fecha_creacion__lt=tiempo_limite
        )
        
        # Contar y eliminar reservas abandonadas
        count = reservas_abandonadas.count()
        if count > 0:
            # Registrar en log antes de eliminar
            for reserva in reservas_abandonadas:
                logging.info(f"Eliminando reserva abandonada #{reserva.id} de {reserva.cliente} - "
                            f"Maquinaria: {reserva.maquinaria.nombre}, "
                            f"Creada: {reserva.fecha_creacion}")
            
            # Eliminar reservas
            reservas_abandonadas.delete()
            
        return count
    
    def marcar_entregada(self):
        """
        Marca una reserva como entregada al cliente.
        Solo se pueden marcar como entregadas las reservas en estado CONFIRMADA.
        
        Returns:
            bool: True si se marcó como entregada exitosamente
        """
        # Solo permitir marcar como entregadas reservas en estado CONFIRMADA
        if self.estado != 'CONFIRMADA':
            return False
        
        # Verificar que la fecha de inicio sea menor o igual a hoy
        from datetime import date
        if self.fecha_inicio > date.today():
            return False
        
        # Cambiar estado a entregada
        self.estado = 'ENTREGADA'
        self.save()
        
        return True
    
    @classmethod
    def finalizar_reservas_no_retiradas(cls):
        """
        Método de clase que finaliza todas las reservas confirmadas que ya han pasado su fecha
        de fin y nunca fueron retiradas (nunca pasaron a estado ENTREGADA). Además, envía
        un correo electrónico al cliente notificándole sobre la finalización de su reserva.
        
        Returns:
            int: Número de reservas finalizadas
        """
        # Obtener todas las reservas confirmadas cuya fecha de fin ha pasado (es menor o igual a la fecha actual)
        # Una reserva se considera vencida cuando su día de fin ya ha pasado completamente
        hoy = timezone.now().date()
        reservas = cls.objects.filter(
            estado='CONFIRMADA',
            fecha_fin__lt=hoy  # fecha_fin < hoy significa que el día de fin ya pasó
        )
        
        contador = 0
        for reserva in reservas:
            if reserva.finalizar_reserva():
                # Enviar correo de notificación al cliente
                reserva.enviar_notificacion_vencimiento()
                contador += 1
                
        return contador
        
    def enviar_notificacion_vencimiento(self):
        """
        Envía una notificación por email al cliente informando que su reserva ha expirado
        sin ser retirada y ha sido finalizada automáticamente.
        
        Returns:
            bool: True si el email se envió correctamente, False en caso contrario
        """
        # Crear el mensaje con formato HTML
        mensaje = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <h2 style="color: #2c3e50;">Notificación de Reserva Expirada</h2>
            <p>Estimado/a {self.cliente.get_full_name()},</p>
            <p>Le informamos que su reserva ha expirado sin ser retirada y ha sido finalizada automáticamente.</p>
            
            <div style="background-color: #f8f9fa; padding: 15px; border-radius: 5px; margin: 20px 0;">
                <p><strong>Detalles de la Reserva:</strong></p>
                <ul>
                    <li>Maquinaria: {self.maquinaria.nombre}</li>
                    <li>Cantidad: {self.cantidad_solicitada} unidad/es</li>
                    <li>Fecha de inicio: {self.fecha_inicio.strftime('%d/%m/%Y')}</li>
                    <li>Fecha de fin: {self.fecha_fin.strftime('%d/%m/%Y')}</li>
                    <li>Sucursal: {self.sucursal_retiro.nombre}</li>
                </ul>
            </div>
            
            <p>Si tiene alguna consulta o desea realizar una nueva reserva, no dude en contactarnos.</p>
            
            <p style="color: #666; font-size: 0.9em; margin-top: 30px;">
                Saludos cordiales,<br>
                El equipo de Alquil.ar
            </p>
        </body>
        </html>
        """
        
        # Configurar el email
        subject = f'Notificación de Reserva Expirada - Alquil.ar'
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
            print(f"Error al enviar notificación de vencimiento: {str(e)}")
            return False