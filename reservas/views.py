# reservas/views.py
import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse, HttpResponseForbidden
from django.core.paginator import Paginator
from django.db.models import Q
from django.utils import timezone
from datetime import datetime, timedelta
from usuarios.decorators import solo_cliente, solo_empleado, solo_admin
from usuarios.models import Usuario, Sucursal, Cupon
from maquinarias.models import Maquinaria, MaquinariaStock
from .models import Reserva
from .forms import (
    ReservaForm, SeleccionSucursalForm, ConfirmacionPagoForm,
    BusquedaReservasForm, EditarReservaForm, ReservaEmpleadoForm,
    ReservaPorCodigoForm, DevolucionForm
)
from .forms_cupon import AplicarCuponForm
import decimal
from .forms_cupon import AplicarCuponForm
import logging
import os
import mercadopago
from django.urls import reverse
from dotenv import load_dotenv
from django.views.decorators.csrf import csrf_exempt

load_dotenv()

# Mercado Pago Configuration
MP_ACCESS_TOKEN = os.getenv('MP_ACCESS_TOKEN')
MP_PUBLIC_KEY = os.getenv('MP_PUBLIC_KEY')
NGROK_URL = os.getenv('NGROK_URL')

sdk = mercadopago.SDK(MP_ACCESS_TOKEN)

@login_required
def crear_reserva(request, maquinaria_id):
    """Vista unificada para crear reservas (clientes y empleados)"""
    if request.user.tipo not in ['CLIENTE', 'EMPLEADO']:
        messages.error(request, "No tiene permisos para crear reservas.")
        return redirect('home')

    maquinaria = get_object_or_404(Maquinaria, id=maquinaria_id)
    
    # Verificar si hay stock disponible en alguna sucursal
    stock_total = maquinaria.get_stock_total()
    if stock_total <= 0:
        messages.error(request, "No hay stock disponible de esta maquinaria en ninguna sucursal.")
        return redirect('maquinaria_list')
    
    if request.method == 'POST':
        # Inicializar el formulario con los datos POST
        form = ReservaForm(request.POST, maquinaria=maquinaria, usuario=request.user)
        
        # Verificar si el formulario es válido
        if form.is_valid():
            # Si es cliente, verificar que no tenga una reserva activa o cancelada
            if request.user.tipo == 'CLIENTE':
                reserva_existente = Reserva.objects.filter(
                    cliente=request.user,
                    estado__in=['CONFIRMADA', 'CANCELADA']
                ).exists()
                
                if reserva_existente:
                    messages.error(request, "No puedes crear una nueva reserva porque tienes una reserva activa o cancelada.")
                    return redirect('home')
                    
                # Eliminar cualquier reserva previa en estado PENDIENTE_PAGO
                reservas_pendientes = Reserva.objects.filter(
                    cliente=request.user,
                    estado='PENDIENTE_PAGO'
                )
                if reservas_pendientes.exists():
                    count = reservas_pendientes.count()
                    reservas_pendientes.delete()
                    logging.info(f"Se eliminaron {count} reservas pendientes de pago del cliente {request.user.id}")
            # Si es empleado, la verificación del cliente se hace en el clean() del formulario
            
            # Verificar disponibilidad para las fechas y cantidad solicitadas
            fecha_inicio = form.cleaned_data['fecha_inicio']
            fecha_fin = form.cleaned_data['fecha_fin']
            cantidad = form.cleaned_data['cantidad_solicitada']
            sucursal = form.cleaned_data['sucursal_retiro']
            
            # Obtener reservas existentes que se superponen con las fechas solicitadas
            reservas_superpuestas = Reserva.objects.filter(
                maquinaria=maquinaria,
                sucursal_retiro=sucursal,
                estado='CONFIRMADA',
                fecha_inicio__lte=fecha_fin,
                fecha_fin__gte=fecha_inicio
            )
            
            # Calcular stock ocupado en esas fechas
            stock_ocupado = sum(reserva.cantidad_solicitada for reserva in reservas_superpuestas)
            
            # Obtener stock total de la sucursal
            try:
                stock_sucursal = maquinaria.stocks.get(sucursal=sucursal)
                stock_disponible = stock_sucursal.stock - stock_ocupado
                
                if stock_disponible < cantidad:
                    messages.error(
                        request, 
                        f"No hay suficiente stock disponible en la sucursal seleccionada para las fechas elegidas. "
                        f"Stock disponible: {stock_disponible}, Cantidad solicitada: {cantidad}"
                    )
                    return redirect('home')
            except MaquinariaStock.DoesNotExist:
                messages.error(request, "La sucursal seleccionada no tiene stock asignado para esta maquinaria.")
                return redirect('home')
            
            reserva = form.save(commit=False)
            reserva.maquinaria = maquinaria
            
            # Si es empleado, obtener el cliente del DNI
            if request.user.tipo == 'EMPLEADO':
                # El cliente se encontró a partir del DNI en el clean() del formulario
                cliente = form.cleaned_data['cliente']
                reserva.cliente = cliente
                
            # Calcular precio total con posible recargo para clientes con baja calificación
            dias = (reserva.fecha_fin - reserva.fecha_inicio).days + 1  # +1 para incluir el día de inicio
            precio_por_dia, _ = maquinaria.get_precio_para_cliente(reserva.cliente)
            # Redondear a 2 decimales para evitar errores de validación
            precio_total = precio_por_dia * dias * reserva.cantidad_solicitada
            precio_total_decimal = decimal.Decimal(str(precio_total)).quantize(decimal.Decimal('0.01'), rounding=decimal.ROUND_HALF_UP)
            
            if request.user.tipo == 'EMPLEADO':
                # Para empleados, guardar datos en sesión y redirigir a la página de confirmación
                request.session['reserva_data'] = {
                    'cliente_id': cliente.id,
                    'cliente_dni': cliente.dni,  # Guardar el DNI del cliente
                    'maquinaria_id': maquinaria.id,
                    'fecha_inicio': form.cleaned_data['fecha_inicio'].isoformat(),
                    'fecha_fin': form.cleaned_data['fecha_fin'].isoformat(),
                    'cantidad_solicitada': form.cleaned_data['cantidad_solicitada'],
                    'sucursal_retiro_id': form.cleaned_data['sucursal_retiro'].id,
                    'precio_total': str(precio_total_decimal),
                    'empleado_id': request.user.id
                }
                return redirect('reservas:confirmar_reservas')
            else:
                # Para clientes, guardar datos en sesión y redirigir a la página de confirmación/pago
                request.session['reserva_data'] = {
                    'cliente_id': request.user.id,
                    'maquinaria_id': maquinaria.id,
                    'fecha_inicio': form.cleaned_data['fecha_inicio'].isoformat(),
                    'fecha_fin': form.cleaned_data['fecha_fin'].isoformat(),
                    'cantidad_solicitada': form.cleaned_data['cantidad_solicitada'],
                    'sucursal_retiro_id': form.cleaned_data['sucursal_retiro'].id,
                    'precio_total': str(precio_total_decimal)
                }
                return redirect('reservas:confirmar_reserva_cliente')
        else:
            messages.error(request, "Por favor, corrija los errores en el formulario.")
    else:
        initial_data = {
            'maquinaria': maquinaria.id
        }
        if request.user.tipo == 'CLIENTE':
            initial_data['cliente'] = request.user.id
        form = ReservaForm(initial=initial_data, maquinaria=maquinaria, usuario=request.user)
    
    context = {
        'form': form,
        'maquinaria': maquinaria,
        'titulo': 'Crear Reserva'
    }
    
    # Añadir información de recargo si el usuario es un cliente con baja calificación
    if request.user.tipo == 'CLIENTE':
        if request.user.calificacion <= 1.0:
            context['aplicar_recargo'] = True
            context['porcentaje_recargo'] = 30
        elif request.user.calificacion <= 2.0:
            context['aplicar_recargo'] = True
            context['porcentaje_recargo'] = 20
        
    return render(request, 'reservas/crear_reserva.html', context)


@login_required
@solo_empleado
def confirmar_reservas(request):
    """
    Vista para confirmar reservas pendientes.
    Solo accesible por empleados.
    """
    logger = logging.getLogger(__name__)

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'confirmar':
            try:
                # Obtener datos de la reserva de la sesión
                reserva_data = request.session.get('reserva_data')
                if not reserva_data:
                    messages.error(request, "No hay datos de reserva para confirmar")
                    return redirect('home')

                # Verificar si el cliente ya tiene una reserva confirmada o cancelada
                cliente = Usuario.objects.get(id=reserva_data['cliente_id'])
                reserva_existente = Reserva.objects.filter(
                    cliente=cliente,
                    estado__in=['CONFIRMADA', 'CANCELADA']
                ).exists()

                if reserva_existente:
                    messages.error(request, "El cliente ya tiene una reserva activa o cancelada. No puede tener más de una reserva.")
                    return redirect('home')
                    
                # Eliminar cualquier reserva previa en estado PENDIENTE_PAGO
                reservas_pendientes = Reserva.objects.filter(
                    cliente=cliente,
                    estado='PENDIENTE_PAGO'
                )
                if reservas_pendientes.exists():
                    count = reservas_pendientes.count()
                    reservas_pendientes.delete()
                    logger.info(f"Se eliminaron {count} reservas pendientes de pago del cliente {cliente.id}")

                # Obtener la maquinaria y cliente para calcular el precio total
                maquinaria = Maquinaria.objects.get(id=reserva_data['maquinaria_id'])
                cliente = Usuario.objects.get(id=reserva_data['cliente_id'])
                fecha_inicio = datetime.strptime(reserva_data['fecha_inicio'], '%Y-%m-%d').date()
                fecha_fin = datetime.strptime(reserva_data['fecha_fin'], '%Y-%m-%d').date()
                dias = (fecha_fin - fecha_inicio).days + 1

                # Aplicar recargo según calificación del cliente
                precio_por_dia, _ = maquinaria.get_precio_para_cliente(cliente)
                precio_base = precio_por_dia * dias * reserva_data['cantidad_solicitada']
                
                # Convertir a Decimal para mantener consistencia
                precio_base = decimal.Decimal(str(precio_base)).quantize(decimal.Decimal('0.01'), rounding=decimal.ROUND_HALF_UP)
                precio_total = precio_base

                # Aplicar descuento de cupón si existe
                descuento_aplicado = decimal.Decimal('0.00')
                precio_antes_descuento = None
                
                if 'codigo_cupon' in reserva_data and reserva_data['codigo_cupon']:
                    try:
                        codigo_cupon = reserva_data['codigo_cupon']
                        cupon = Cupon.objects.get(codigo=codigo_cupon)
                        
                        if 'descuento_aplicado' in reserva_data:
                            descuento_aplicado = decimal.Decimal(reserva_data['descuento_aplicado'])
                            
                            # Usar el precio_base de la sesión si está disponible
                            if 'precio_base' in reserva_data:
                                precio_antes_descuento = decimal.Decimal(reserva_data['precio_base'])
                            else:
                                precio_antes_descuento = precio_base
                                
                            precio_total = precio_antes_descuento - descuento_aplicado
                            print(f"=== CONFIRMAR EMPLEADO DEBUG ===")
                            print(f"Precio base: ${precio_antes_descuento}")
                            print(f"Descuento aplicado: ${descuento_aplicado}")
                            print(f"Precio total con descuento: ${precio_total}")
                    except Cupon.DoesNotExist:
                        logger.error(f"No se encontró el cupón con código {reserva_data['codigo_cupon']}")
                    except Exception as e:
                        logger.error(f"Error al aplicar el cupón: {str(e)}")

                # Round to 2 decimal places to ensure it fits the model constraint
                precio_total = decimal.Decimal(str(precio_total)).quantize(decimal.Decimal('0.01'), rounding=decimal.ROUND_HALF_UP)

                # Crear la reserva con estado PENDIENTE_PAGO
                reserva = Reserva.objects.create(
                    cliente_id=reserva_data['cliente_id'],
                    maquinaria_id=reserva_data['maquinaria_id'],
                    fecha_inicio=reserva_data['fecha_inicio'],
                    fecha_fin=reserva_data['fecha_fin'],
                    cantidad_solicitada=reserva_data['cantidad_solicitada'],
                    sucursal_retiro_id=reserva_data['sucursal_retiro_id'],
                    tipo_pago='PRESENCIAL',
                    estado='PENDIENTE_PAGO',
                    precio_total=precio_total,
                    empleado_procesador=request.user
                )
                
                # Si se aplicó un cupón, actualizar la reserva y el cupón
                if 'codigo_cupon' in reserva_data and reserva_data['codigo_cupon'] and descuento_aplicado > 0:
                    try:
                        cupon = Cupon.objects.get(codigo=reserva_data['codigo_cupon'])
                        
                        # Actualizar información del descuento y el precio final en la reserva
                        reserva.precio_antes_descuento = precio_antes_descuento if precio_antes_descuento else precio_base
                        reserva.descuento_aplicado = descuento_aplicado
                        reserva.precio_total = precio_total
                        reserva.save()
                        
                        # Marcar el cupón como usado y asociarlo a la reserva
                        cupon.usado = True
                        cupon.reserva_uso = reserva
                        cupon.save()
                        
                        logger.info(f"Cupón {cupon.codigo} aplicado a la reserva {reserva.id}")
                    except Exception as e:
                        logger.error(f"Error al finalizar la aplicación del cupón: {str(e)}")

                # Limpiar datos de la sesión
                del request.session['reserva_data']

                # Redirigir a la vista de QR
                return redirect('reservas:mostrar_qr_pago', reserva_id=reserva.id)

            except Exception as e:
                logger.error(f"Error al procesar la confirmación: {str(e)}")
                messages.error(request, "Error al procesar la confirmación")
                return redirect('home')

        elif action == 'cancelar':
            # Limpiar datos de la sesión
            if 'reserva_data' in request.session:
                del request.session['reserva_data']
            messages.info(request, "Reserva cancelada")
            return redirect('home')

    # GET request o aplicación de cupón
    reserva_data = request.session.get('reserva_data')
    if not reserva_data:
        messages.error(request, "No hay datos de reserva para confirmar")
        return redirect('home')

    # Obtener datos necesarios para mostrar en la confirmación
    cliente = Usuario.objects.get(id=reserva_data['cliente_id'])
    maquinaria = Maquinaria.objects.get(id=reserva_data['maquinaria_id'])
    sucursal = Sucursal.objects.get(id=reserva_data['sucursal_retiro_id'])

    # Calcular precio total para mostrar en la confirmación
    fecha_inicio = datetime.strptime(reserva_data['fecha_inicio'], '%Y-%m-%d').date()
    fecha_fin = datetime.strptime(reserva_data['fecha_fin'], '%Y-%m-%d').date()
    dias = (fecha_fin - fecha_inicio).days + 1

    # Aplicar recargo según calificación del cliente
    precio_por_dia, porcentaje_recargo = maquinaria.get_precio_para_cliente(cliente)
    precio_base = precio_por_dia * dias * reserva_data['cantidad_solicitada']
    
    # Redondear a 2 decimales
    precio_base = decimal.Decimal(str(precio_base)).quantize(decimal.Decimal('0.01'), rounding=decimal.ROUND_HALF_UP)
    precio_total = precio_base

    # Buscar cupones disponibles para el cliente
    cupones_disponibles = Cupon.objects.filter(
        cliente=cliente, 
        usado=False,
        fecha_vencimiento__gte=timezone.now().date()
    ).order_by('-fecha_creacion')

    # Inicializar variables para cupones
    cupon_aplicado = None
    descuento_aplicado = decimal.Decimal('0.00')
    
    # Verificar si se está aplicando un cupón
    if request.method == 'POST' and 'aplicar_cupon' in request.POST:
        # Crear formulario con los datos enviados
        form_cupon = AplicarCuponForm(request.POST, cliente=cliente, precio_reserva=precio_base)
        
        if form_cupon.is_valid():
            # Calcular descuento
            descuento_aplicado = form_cupon.get_descuento()
            precio_total = precio_base - descuento_aplicado
            
            # Obtener el cupón aplicado para mostrarlo
            codigo = form_cupon.cleaned_data.get('codigo_cupon')
            if codigo:
                try:
                    cupon_aplicado = Cupon.objects.get(codigo=codigo)
                except Cupon.DoesNotExist:
                    cupon_aplicado = None
            
            # Guardar el descuento en la sesión para cuando se confirme la reserva
            reserva_data['descuento_aplicado'] = str(descuento_aplicado)
            reserva_data['codigo_cupon'] = codigo
            reserva_data['precio_base'] = str(precio_base)  # También guardar el precio base
            request.session['reserva_data'] = reserva_data
            
            messages.success(request, f"¡Cupón aplicado correctamente! Descuento: ${descuento_aplicado}")
        else:
            # Mostrar errores del formulario si el cupón no es válido
            for field, errors in form_cupon.errors.items():
                for error in errors:
                    messages.error(request, f"Error en cupón: {error}")
    else:
        form_cupon = AplicarCuponForm(cliente=cliente, precio_reserva=precio_base)

    context = {
        'cliente': cliente,
        'maquinaria': maquinaria,
        'sucursal': sucursal,
        'fecha_inicio': reserva_data['fecha_inicio'],
        'fecha_fin': reserva_data['fecha_fin'],
        'cantidad_solicitada': reserva_data['cantidad_solicitada'],
        'precio_base': precio_base,
        'precio_total': precio_total,
        'titulo': 'Confirmar Reserva',
        'cupones_disponibles': cupones_disponibles,
        'form_cupon': form_cupon,
        'cupon_aplicado': cupon_aplicado,
        'descuento_aplicado': descuento_aplicado
    }

    return render(request, 'reservas/confirmar_reservas.html', context)


@login_required
@solo_cliente
def confirmar_reserva_cliente(request):
    """
    Vista para confirmar reservas pendientes por parte de clientes.
    Solo accesible por clientes.
    """
    logger = logging.getLogger(__name__)

    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'confirmar':
            try:
                # Obtener datos de la reserva de la sesión
                reserva_data = request.session.get('reserva_data')
                if not reserva_data:
                    messages.error(request, "No hay datos de reserva para confirmar")
                    return redirect('home')
                
                # Verificar si el cliente ya tiene una reserva confirmada o cancelada
                cliente = request.user
                reserva_existente = Reserva.objects.filter(
                    cliente=cliente,
                    estado__in=['CONFIRMADA', 'CANCELADA']
                ).exists()
                
                if reserva_existente:
                    messages.error(request, "Ya tienes una reserva activa o cancelada. No puedes tener más de una reserva.")
                    return redirect('home')
                
                # Eliminar cualquier reserva previa en estado PENDIENTE_PAGO
                reservas_pendientes = Reserva.objects.filter(
                    cliente=cliente,
                    estado='PENDIENTE_PAGO'
                )
                if reservas_pendientes.exists():
                    count = reservas_pendientes.count()
                    reservas_pendientes.delete()
                    logger.info(f"Se eliminaron {count} reservas pendientes de pago del cliente {cliente.id}")
                
                # Obtener la maquinaria para calcular el precio total
                maquinaria = Maquinaria.objects.get(id=reserva_data['maquinaria_id'])
                fecha_inicio = datetime.strptime(reserva_data['fecha_inicio'], '%Y-%m-%d').date()
                fecha_fin = datetime.strptime(reserva_data['fecha_fin'], '%Y-%m-%d').date()
                dias = (fecha_fin - fecha_inicio).days + 1  # +1 para incluir el día de inicio
                
                # Aplicar recargo según calificación del cliente
                precio_por_dia, _ = maquinaria.get_precio_para_cliente(cliente)
                precio_base = precio_por_dia * dias * int(reserva_data['cantidad_solicitada'])
                precio_total = precio_base
                
                # Aplicar descuento de cupón si existe
                descuento_aplicado = decimal.Decimal('0.00')
                precio_antes_descuento = None
                
                if 'codigo_cupon' in reserva_data and reserva_data['codigo_cupon']:
                    try:
                        codigo_cupon = reserva_data['codigo_cupon']
                        cupon = Cupon.objects.get(codigo=codigo_cupon)
                        
                        if 'descuento_aplicado' in reserva_data:
                            descuento_aplicado = decimal.Decimal(reserva_data['descuento_aplicado'])
                            
                            # Usar el precio_base de la sesión si está disponible
                            if 'precio_base' in reserva_data:
                                precio_antes_descuento = decimal.Decimal(reserva_data['precio_base'])
                            else:
                                precio_antes_descuento = precio_base
                                
                            precio_total = precio_antes_descuento - descuento_aplicado
                            print(f"=== CONFIRMAR CLIENTE DEBUG ===")
                            print(f"Precio base: ${precio_antes_descuento}")
                            print(f"Descuento aplicado: ${descuento_aplicado}")
                            print(f"Precio total con descuento: ${precio_total}")
                    except Cupon.DoesNotExist:
                        logger.error(f"No se encontró el cupón con código {reserva_data['codigo_cupon']}")
                    except Exception as e:
                        logger.error(f"Error al aplicar el cupón: {str(e)}")
                
                # Redondear a 2 decimales para evitar errores de validación
                precio_total = decimal.Decimal(str(precio_total)).quantize(decimal.Decimal('0.01'), rounding=decimal.ROUND_HALF_UP)
                
                # Crear la reserva
                reserva = Reserva.objects.create(
                    cliente=cliente,
                    maquinaria_id=reserva_data['maquinaria_id'],
                    fecha_inicio=reserva_data['fecha_inicio'],
                    fecha_fin=reserva_data['fecha_fin'],
                    cantidad_solicitada=int(reserva_data['cantidad_solicitada']),
                    sucursal_retiro_id=reserva_data['sucursal_retiro_id'],
                    tipo_pago='ONLINE',
                    estado='PENDIENTE_PAGO',
                    precio_total=precio_total
                )
                
                # Si se aplicó un cupón, actualizar la reserva y el cupón
                if 'codigo_cupon' in reserva_data and reserva_data['codigo_cupon'] and descuento_aplicado > 0:
                    try:
                        cupon = Cupon.objects.get(codigo=reserva_data['codigo_cupon'])
                        
                        # Asegurar que los valores son Decimal con 2 decimales máximo
                        if precio_antes_descuento:
                            precio_antes_descuento_decimal = decimal.Decimal(str(precio_antes_descuento)).quantize(
                                decimal.Decimal('0.01'), rounding=decimal.ROUND_HALF_UP
                            )
                        else:
                            precio_antes_descuento_decimal = precio_base
                            
                        descuento_aplicado_decimal = decimal.Decimal(str(descuento_aplicado)).quantize(
                            decimal.Decimal('0.01'), rounding=decimal.ROUND_HALF_UP
                        )
                        precio_total_decimal = decimal.Decimal(str(precio_total)).quantize(
                            decimal.Decimal('0.01'), rounding=decimal.ROUND_HALF_UP
                        )
                        
                        # Actualizar información del descuento y el precio final en la reserva
                        reserva.precio_antes_descuento = precio_antes_descuento_decimal
                        reserva.descuento_aplicado = descuento_aplicado_decimal
                        reserva.precio_total = precio_total_decimal
                        reserva.save()
                        
                        # Marcar el cupón como usado y asociarlo a la reserva
                        cupon.usado = True
                        cupon.reserva_uso = reserva
                        cupon.save()
                        
                        print(f"=== CUPÓN GUARDADO ===")
                        print(f"Precio antes descuento guardado: ${reserva.precio_antes_descuento}")
                        print(f"Descuento aplicado guardado: ${reserva.descuento_aplicado}")
                        print(f"Precio total guardado: ${reserva.precio_total}")
                        
                        logger.info(f"Cupón {cupon.codigo} aplicado a la reserva {reserva.id}")
                    except Exception as e:
                        logger.error(f"Error al finalizar la aplicación del cupón: {str(e)}")
                
                # Verificar disponibilidad
                try:
                    maquinaria_stock = maquinaria.stocks.get(sucursal_id=reserva_data['sucursal_retiro_id'])
                    stock_total = maquinaria_stock.stock_disponible
                    
                    # Obtener reservas superpuestas
                    reservas_superpuestas = Reserva.objects.filter(
                        maquinaria=maquinaria,
                        sucursal_retiro_id=reserva_data['sucursal_retiro_id'],
                        estado='CONFIRMADA',
                        fecha_inicio__lte=fecha_fin,
                        fecha_fin__gte=fecha_inicio
                    )
                    
                    stock_reservado = sum(reserva.cantidad_solicitada for reserva in reservas_superpuestas)
                    stock_disponible = stock_total - stock_reservado
                    
                    if stock_disponible < int(reserva_data['cantidad_solicitada']):
                        mensaje_error = f"Para las fechas seleccionadas solo hay {stock_disponible} unidad/es disponible/s. Por favor, seleccione una cantidad o fecha distinta."
                        messages.error(request, mensaje_error)
                        reserva.delete()
                        return redirect('home')
                        
                except Exception as e:
                    logger.error(f"Error al verificar disponibilidad: {str(e)}")
                    messages.error(request, "No se pudo verificar la disponibilidad. Por favor, intente nuevamente.")
                    reserva.delete()
                    return redirect('home')
                    
                # Limpiar datos de la sesión
                if 'reserva_data' in request.session:
                    del request.session['reserva_data']
                
                # Redirigir al proceso de pago con MercadoPago
                return redirect('reservas:procesar_pago', reserva_id=reserva.id)
            
            except Exception as e:
                logger.error(f"Error general: {str(e)}")
                messages.error(request, "Error al procesar la reserva.")
                return redirect('home')
                
        elif action == 'cancelar':
            # Limpiar datos de la sesión y redirigir
            if 'reserva_data' in request.session:
                del request.session['reserva_data']
            messages.info(request, "Proceso de reserva cancelado")
            return redirect('maquinaria_list_cliente')
    
    # Mostrar formulario de confirmación con datos de la reserva
    reserva_data = request.session.get('reserva_data')
    if not reserva_data:
        messages.error(request, "No hay datos de reserva para confirmar")
        return redirect('home')
    
    # Obtener objetos relacionados para mostrar en la confirmación
    cliente = request.user
    maquinaria = get_object_or_404(Maquinaria, id=reserva_data['maquinaria_id'])
    sucursal = get_object_or_404(Sucursal, id=reserva_data['sucursal_retiro_id'])
    
    # Calcular precio total con posible recargo
    fecha_inicio = datetime.strptime(reserva_data['fecha_inicio'], '%Y-%m-%d').date()
    fecha_fin = datetime.strptime(reserva_data['fecha_fin'], '%Y-%m-%d').date()
    dias = (fecha_fin - fecha_inicio).days + 1  # +1 para incluir el día de inicio
    precio_por_dia, porcentaje_recargo = maquinaria.get_precio_para_cliente(cliente)
    precio_base = precio_por_dia * dias * int(reserva_data['cantidad_solicitada'])
    
    # Convertir a Decimal para mantener consistencia con el resto del código
    precio_base = decimal.Decimal(str(precio_base)).quantize(decimal.Decimal('0.01'), rounding=decimal.ROUND_HALF_UP)
    precio_total = precio_base

    # Buscar cupones disponibles para el cliente
    cupones_disponibles = Cupon.objects.filter(
        cliente=cliente, 
        usado=False,
        fecha_vencimiento__gte=timezone.now().date()
    ).order_by('-fecha_creacion')

    # Inicializar variables para cupones
    cupon_aplicado = None
    descuento_aplicado = decimal.Decimal('0.00')
    
    # Verificar si se está aplicando un cupón
    if request.method == 'POST' and 'aplicar_cupon' in request.POST:
        # Crear formulario con los datos enviados
        form_cupon = AplicarCuponForm(request.POST, cliente=cliente, precio_reserva=precio_base)
        
        if form_cupon.is_valid():
            # Calcular descuento
            descuento_aplicado = form_cupon.get_descuento()
            precio_total = precio_base - descuento_aplicado
            
            # Obtener el cupón aplicado para mostrarlo
            codigo = form_cupon.cleaned_data.get('codigo_cupon')
            if codigo:
                try:
                    cupon_aplicado = Cupon.objects.get(codigo=codigo)
                except Cupon.DoesNotExist:
                    cupon_aplicado = None
            
            # Guardar el descuento en la sesión para cuando se confirme la reserva
            reserva_data['descuento_aplicado'] = str(descuento_aplicado)
            reserva_data['codigo_cupon'] = codigo
            reserva_data['precio_base'] = str(precio_base)  # También guardar el precio base
            request.session['reserva_data'] = reserva_data
            
            messages.success(request, f"¡Cupón aplicado correctamente! Descuento: ${descuento_aplicado}")
        else:
            # Mostrar errores del formulario si el cupón no es válido
            for field, errors in form_cupon.errors.items():
                for error in errors:
                    messages.error(request, f"Error en cupón: {error}")
    else:
        form_cupon = AplicarCuponForm(cliente=cliente, precio_reserva=precio_base)
    
    context = {
        'cliente': cliente,
        'maquinaria': maquinaria,
        'sucursal': sucursal,
        'fecha_inicio': reserva_data['fecha_inicio'],
        'fecha_fin': reserva_data['fecha_fin'],
        'cantidad_solicitada': reserva_data['cantidad_solicitada'],
        'precio_base': precio_base,
        'precio_total': precio_total,
        'titulo': 'Confirmar Reserva',
        'aplicar_recargo': porcentaje_recargo > 0,
        'porcentaje_recargo': porcentaje_recargo,
        'cupones_disponibles': cupones_disponibles,
        'form_cupon': form_cupon,
        'cupon_aplicado': cupon_aplicado,
        'descuento_aplicado': descuento_aplicado
    }
    
    return render(request, 'reservas/confirmar_reserva_cliente.html', context)

@login_required
@solo_empleado
def seleccionar_sucursal(request):
    """Vista para seleccionar la sucursal de retiro"""
    reserva_data = request.session.get('reserva_data')
    
    if not reserva_data:
        messages.error(request, 'No hay datos de reserva. Por favor, inicie el proceso nuevamente.')
        return redirect('maquinarias_cliente')
    
    # Reconstruir la información de sucursales disponibles
    sucursales_info = []
    for suc_data in reserva_data['sucursales_disponibles']:
        sucursal = get_object_or_404(Sucursal, id=suc_data['sucursal_id'])
        sucursales_info.append({
            'sucursal': sucursal,
            'stock_disponible': suc_data['stock_disponible']
        })
    
    # Determinar si el usuario es empleado o admin para mostrar stock
    es_empleado = request.user.is_authenticated and request.user.tipo in ['EMPLEADO', 'ADMIN']
    
    if request.method == 'POST':
        form = SeleccionSucursalForm(request.POST, sucursales_disponibles=sucursales_info, es_empleado=es_empleado)
        
        if form.is_valid():
            # Agregar la sucursal seleccionada a los datos de la sesión
            reserva_data['sucursal_retiro_id'] = form.cleaned_data['sucursal_retiro'].id
            request.session['reserva_data'] = reserva_data
            
            return redirect('confirmar_reserva')
    else:
        form = SeleccionSucursalForm(sucursales_disponibles=sucursales_info, es_empleado=es_empleado)
    
    maquinaria = get_object_or_404(Maquinaria, id=reserva_data['maquinaria_id'])
    
    context = {
        'form': form,
        'reserva_data': reserva_data,
        'maquinaria': maquinaria,
        'titulo': 'Seleccionar Sucursal de Retiro',
    }
    
    return render(request, 'reservas/seleccionar_sucursal.html', context)

@login_required
def confirmar_reserva(request, reserva_id):
    """Vista para confirmar los detalles de la reserva"""
    # Obtener la reserva y verificar permisos
    reserva = get_object_or_404(Reserva, id=reserva_id)
    
    # Verificar que el usuario tenga permiso para ver esta reserva
    if request.user.tipo == 'CLIENTE' and reserva.cliente != request.user:
        messages.error(request, "No tiene permiso para ver esta reserva.")
        return redirect('home')
    elif request.user.tipo == 'EMPLEADO' and reserva.empleado_procesador != request.user:
        messages.error(request, "No tiene permiso para ver esta reserva.")
        return redirect('home')
    
    if request.method == 'POST':
        if request.user.tipo == 'EMPLEADO':
            # Si es empleado, confirmar la reserva directamente
            reserva.estado = 'CONFIRMADA'
            reserva.fecha_confirmacion = timezone.now()
            reserva.save()
            messages.success(request, 'Reserva confirmada exitosamente')
            return redirect('reservas:detalle_reserva', reserva_id=reserva.id)
        else:
            preference = gen_preference_mp(request, reserva)
            return redirect('reservas:procesar_pago', reserva_id=reserva.id)
    
    return render(request, 'reservas/confirmar_reserva.html', {
        'reserva': reserva,
        'maquinaria': reserva.maquinaria,
        'sucursal': reserva.sucursal_retiro,
        'dias': (reserva.fecha_fin - reserva.fecha_inicio).days + 1,  # +1 para incluir el día de inicio
        'precio_por_dia': reserva.maquinaria.precio_por_dia,
        'precio_total': reserva.precio_total,
        'es_empleado': request.user.tipo == 'EMPLEADO'
    })


@login_required
def procesar_pago(request, reserva_id):
    """Vista para procesar el pago de una reserva usando Mercado Pago"""
    try:
        reserva = get_object_or_404(Reserva, id=reserva_id)
        
        # Verificar que el usuario puede acceder a esta reserva
        if request.user != reserva.cliente and not request.user.tipo in ['ADMIN', 'EMPLEADO']:
            return HttpResponseForbidden("No tiene permisos para acceder a esta reserva.")
        
        # Refrescar la reserva y ajustar precio si hay cupón aplicado
        reserva.refresh_from_db()
        
        # Log para debugging
        print(f"=== PROCESAR PAGO DEBUG ===")
        print(f"Reserva ID: {reserva.id}")
        print(f"Precio total actual: ${reserva.precio_total}")
        print(f"Precio antes descuento: ${reserva.precio_antes_descuento}")
        print(f"Descuento aplicado: ${reserva.descuento_aplicado}")
        
        if reserva.precio_antes_descuento and reserva.descuento_aplicado and reserva.descuento_aplicado > 0:
            precio_calculado = reserva.precio_antes_descuento - reserva.descuento_aplicado
            print(f"Precio calculado: ${precio_calculado}")
            if precio_calculado != reserva.precio_total:
                print(f"Actualizando precio de ${reserva.precio_total} a ${precio_calculado}")
                reserva.precio_total = precio_calculado
                reserva.save()
            else:
                print("El precio ya está correcto, no se actualiza")
        
        # Obtener información de recargo según calificación del cliente
        cliente = reserva.cliente
        maquinaria = reserva.maquinaria
        
        # Obtener el precio con posible recargo según calificación
        precio_por_dia, recargo_info = maquinaria.get_precio_para_cliente(cliente)
        
        # Generar preferencia de Mercado Pago
        try:
            preference = gen_preference_mp(request, reserva)
            preference_id = preference.get('id')
            
            if not preference_id:
                # Si no se puede obtener la preferencia, eliminar la reserva para evitar estados inválidos
                reserva.delete()
                logging.error("No se pudo obtener el ID de preferencia de Mercado Pago. Reserva eliminada.")
                messages.error(request, "Error al procesar el pago. Por favor, intente nuevamente desde el catálogo.")
                return redirect('maquinaria_list_cliente')
                
            context = {
                'reserva': reserva,
                'MP_PUBLIC_KEY': MP_PUBLIC_KEY,
                'preference_id': preference_id,
                'titulo': 'Procesar Pago',
                'recargo_info': recargo_info,  # Información sobre el recargo
                'precio_base': maquinaria.precio_por_dia,  # Precio base sin recargo
                'precio_con_recargo': precio_por_dia,  # Precio con recargo aplicado
            }

            return render(request, 'reservas/procesar_pago.html', context)
        
        except Exception as e:
            # En caso de error, eliminar la reserva para evitar registros incompletos
            if reserva and reserva.estado == 'PENDIENTE_PAGO':
                reserva.delete()
                logging.error(f"Error al generar preferencia de pago: {str(e)}. Reserva eliminada.")
            else:
                logging.error(f"Error al generar preferencia de pago: {str(e)}")
                
            messages.error(request, "Error al procesar el pago. Por favor, intente nuevamente desde el catálogo.")
            return redirect('maquinaria_list_cliente')
            
    except Exception as e:
        logging.error(f"Error en procesar_pago: {str(e)}")
        messages.error(request, "Error al procesar la solicitud. Por favor, intente nuevamente.")
        return redirect('home')


@login_required
def lista_reservas(request):
    """Vista para listar reservas según el tipo de usuario"""
    # Actualizar automáticamente las reservas vencidas
    reservas_actualizadas = Reserva.actualizar_reservas_vencidas()
    if reservas_actualizadas > 0 and (request.user.tipo == 'ADMIN' or request.user.tipo == 'EMPLEADO'):
        messages.info(request, f"Se actualizaron {reservas_actualizadas} reservas vencidas a estado 'No Devuelta'.")
    
    # Finalizar automáticamente las reservas confirmadas que nunca fueron retiradas y ya pasaron su fecha de fin
    reservas_finalizadas = Reserva.finalizar_reservas_no_retiradas()
    if reservas_finalizadas > 0 and (request.user.tipo == 'ADMIN' or request.user.tipo == 'EMPLEADO'):
        messages.info(request, f"Se finalizaron automáticamente {reservas_finalizadas} reservas que nunca fueron retiradas.")
        
    # Limpiar reservas abandonadas (PENDIENTE_PAGO por más de 30 minutos)
    reservas_eliminadas = Reserva.limpiar_reservas_abandonadas()
    if reservas_eliminadas > 0 and (request.user.tipo == 'ADMIN' or request.user.tipo == 'EMPLEADO'):
        messages.info(request, f"Se eliminaron {reservas_eliminadas} reservas abandonadas en estado pendiente de pago.")
    
    # Obtener parámetros de filtrado
    estado = request.GET.get('estado')
    fecha_desde = request.GET.get('fecha_desde')
    fecha_hasta = request.GET.get('fecha_hasta')
    cliente_dni = request.GET.get('cliente_dni', '').strip()
    empleado_dni = request.GET.get('empleado_dni', '').strip()
    sucursal_id = request.GET.get('sucursal')
      # Iniciar el queryset base según el tipo de usuario
    if request.user.tipo == 'ADMIN' or request.user.tipo == 'EMPLEADO':
        # Administradores y empleados ven todas las reservas excepto las pendientes de pago
        reservas = Reserva.objects.exclude(estado='PENDIENTE_PAGO')
        # Obtener lista de sucursales para el filtro
        sucursales = Sucursal.objects.filter(activa=True).order_by('nombre')
    else:
        # Clientes ven sus propias reservas excepto las pendientes de pago
        reservas = Reserva.objects.filter(cliente=request.user).exclude(estado='PENDIENTE_PAGO')
        sucursales = None
      # Aplicar filtros si existen
    if estado and estado != 'PENDIENTE_PAGO':
        reservas = reservas.filter(estado=estado)
        
    if fecha_desde:
        reservas = reservas.filter(fecha_inicio__gte=fecha_desde)
    
    if fecha_hasta:
        reservas = reservas.filter(fecha_fin__lte=fecha_hasta)
        
    if cliente_dni and (request.user.tipo in ['ADMIN', 'EMPLEADO']):
        # Filtrar por DNI de cliente (búsqueda parcial)
        cliente_ids = Usuario.objects.filter(
            tipo='CLIENTE', 
            dni__icontains=cliente_dni
        ).values_list('id', flat=True)
        reservas = reservas.filter(cliente_id__in=cliente_ids)
        
    if empleado_dni and (request.user.tipo in ['ADMIN', 'EMPLEADO']):
        # Filtrar por DNI de empleado (búsqueda parcial)
        empleado_ids = Usuario.objects.filter(
            tipo='EMPLEADO', 
            dni__icontains=empleado_dni
        ).values_list('id', flat=True)
        reservas = reservas.filter(empleado_procesador_id__in=empleado_ids)
        
    if sucursal_id and (request.user.tipo in ['ADMIN', 'EMPLEADO']):
        reservas = reservas.filter(sucursal_retiro_id=sucursal_id)
    
    # Obtener todas las maquinarias para el filtro
    from maquinarias.models import Maquinaria
    maquinaria_id = request.GET.get('maquinaria')
    maquinarias = Maquinaria.objects.all().order_by('nombre')
    
    # Aplicar filtro de maquinaria si existe
    if maquinaria_id:
        reservas = reservas.filter(maquinaria_id=maquinaria_id)
    
    # Ordenar por fecha de creación (más recientes primero)
    reservas = reservas.order_by('-fecha_creacion')
      
    # Paginación
    paginator = Paginator(reservas, 10)  # 10 reservas por página
    page = request.GET.get('page')
    reservas_paginadas = paginator.get_page(page)

    context = {
        'reservas': reservas_paginadas,
        'is_paginated': True if reservas.count() > 10 else False,
        'page_obj': reservas_paginadas,
        'titulo': 'Historial de Reservas',
        'sucursales': sucursales,  # Lista de sucursales para el filtro
        'maquinarias': maquinarias,  # Lista de maquinarias para el filtro
        'cliente_dni': cliente_dni,  # DNI del cliente para mantener el filtro
        'empleado_dni': empleado_dni,  # DNI del empleado para mantener el filtro
        'filtros_aplicados': any([estado, fecha_desde, fecha_hasta, cliente_dni, empleado_dni, sucursal_id, maquinaria_id])
    }
    
    return render(request, 'reservas/lista_reservas.html', context)


@login_required
def detalle_reserva(request, reserva_id):
    """Vista para ver los detalles de una reserva"""
    if request.user.is_staff:
        reserva = get_object_or_404(Reserva, id=reserva_id)
    else:
        reserva = get_object_or_404(Reserva, id=reserva_id, cliente=request.user)
    
    context = {
        'reserva': reserva
    }
    
    # Si la reserva está pendiente de pago, generar preferencia de Mercado Pago
    if reserva.estado == 'PENDIENTE_PAGO':
        try:
            # Verificar credenciales
            if not MP_ACCESS_TOKEN or not MP_PUBLIC_KEY:
                messages.error(request, "Error de configuración del sistema de pagos. Por favor, contacte a soporte.")
                logging.error("Mercado Pago credentials not configured")
            else:
                preference = gen_preference_mp(request, reserva)
                if preference and 'id' in preference:
                    context.update({
                        'MP_PUBLIC_KEY': MP_PUBLIC_KEY,
                        'preference_id': preference['id']
                    })
                else:
                    messages.error(request, "Error al generar el pago. Por favor, intente nuevamente más tarde.")
                    logging.error(f"Invalid preference response: {preference}")
        except Exception as e:
            logging.error(f"Error al generar preferencia de pago: {str(e)}")
            messages.error(request, "Error al cargar el pago. Por favor, intente nuevamente más tarde.")
    
    return render(request, 'reservas/detalle_reserva.html', context)


@login_required
def cancelar_reserva(request, reserva_id):
    """Vista para cancelar una reserva"""
    reserva = get_object_or_404(Reserva, id=reserva_id)
    
    # Verificar permisos
    if request.user.tipo == 'CLIENTE' and reserva.cliente != request.user:
        return HttpResponseForbidden("No puede cancelar esta reserva.")
    elif request.user.tipo not in ['CLIENTE', 'EMPLEADO', 'ADMIN']:
        return HttpResponseForbidden("No tiene permisos para cancelar reservas.")
        
    # Si es cliente y la reserva está activa (dentro del período de alquiler), no permitir cancelación
    if request.user.tipo == 'CLIENTE' and reserva.is_active():
        messages.error(request, "No se pueden cancelar reservas que están dentro de su período de alquiler activo. Por favor, contacte con un empleado si necesita asistencia.")
        return redirect('reservas:detalle_reserva', reserva_id=reserva_id)
    
    if request.method == 'POST':
        if reserva.estado is None:
            # Handle incomplete reservations (estado=None)
            reserva_id = reserva.id
            try:
                # Directly delete from database to avoid issues with signals or validations
                Reserva.objects.filter(id=reserva_id).delete()
                messages.success(request, f'Reserva incompleta #{reserva_id} eliminada correctamente.')
            except Exception as e:
                messages.error(request, f'Error al eliminar la reserva incompleta: {str(e)}')
                return redirect('reservas:lista_reservas')
        elif reserva.cancelar():
            messages.success(request, 'Reserva cancelada exitosamente.')
        else:
            messages.error(request, 'No se pudo cancelar la reserva.')
        
        # Redirigir según el tipo de usuario
        if request.user.tipo == 'CLIENTE':
            return redirect('usuarios:panel_cliente')
        else:
            return redirect('reservas:lista_reservas')
    
    context = {
        'reserva': reserva,
        'titulo': 'Cancelar Reserva',
    }
    
    return render(request, 'reservas/cancelar_reserva.html', context)


@login_required
def editar_reserva(request, reserva_id):
    """Vista para editar una reserva (solo admins y empleados)"""
    if request.user.tipo not in ['ADMIN', 'EMPLEADO']:
        return HttpResponseForbidden("No tiene permisos para editar reservas.")
    
    reserva = get_object_or_404(Reserva, id=reserva_id)
    
    if request.method == 'POST':
        form = EditarReservaForm(request.POST, instance=reserva, usuario=request.user)
        
        if form.is_valid():
            form.save()
            messages.success(request, 'Reserva actualizada exitosamente.')
            return redirect('detalle_reserva', reserva_id=reserva.id)
    else:
        form = EditarReservaForm(instance=reserva, usuario=request.user)
    
    context = {
        'form': form,
        'reserva': reserva,
        'titulo': f'Editar Reserva #{reserva.id}',
    }
    
    return render(request, 'reservas/editar_reserva.html', context)


@login_required
@solo_cliente
def reembolsar_reserva(request, reserva_id):
    """
    Vista para mostrar la página de confirmación de cancelación de una reserva.
    Calcula el monto de reembolso según la política establecida, pero no registra el reembolso.
    El reembolso solo se registrará cuando un empleado finalice la reserva cancelada.
    """
    reserva = get_object_or_404(Reserva, id=reserva_id)
    
    # Verificar que el usuario sea el dueño de la reserva
    if request.user != reserva.cliente:
        messages.error(request, "No tiene permisos para reembolsar esta reserva.")
        return redirect('reservas:lista_reservas')
    
    # Verificar que la reserva esté en estado CONFIRMADA
    if reserva.estado != 'CONFIRMADA':
        messages.error(request, "Solo se pueden reembolsar reservas confirmadas.")
        return redirect('reservas:lista_reservas')
    
    # Verificar si la reserva está activa (dentro del plazo de los días de la reserva)
    if reserva.is_active():
        messages.error(request, "No se pueden reembolsar reservas activas que están dentro de su periodo de alquiler. Por favor, contacte con un empleado si necesita asistencia.")
        return redirect('reservas:lista_reservas')
    
    # Obtener la fecha actual
    fecha_actual = timezone.now().date()
    dias_hasta_inicio = (reserva.fecha_inicio - fecha_actual).days
    
    # Calcular el monto de reembolso según la política
    monto_reembolso, porcentaje_reembolso = reserva.calcular_monto_reembolso(fecha_actual)
    
    # Si corresponde un reembolso del 0%, procesarlo directamente sin intervención del empleado
    if porcentaje_reembolso == 0:
        # Si es un GET, mostrar la confirmación
        if request.method == 'GET':
            context = {
                'reserva': reserva,
                'fecha_actual': fecha_actual,
                'dias_hasta_inicio': dias_hasta_inicio,
                'monto_reembolso': monto_reembolso,
                'porcentaje_reembolso': porcentaje_reembolso,
                'procesamiento_automatico': True
            }
            return render(request, 'reservas/confirmar_reembolso.html', context)
    
    # Si es un POST, procesar la confirmación del reembolso
    if request.method == 'POST':
        # Procesar la cancelación y restaurar stock
        if reserva.reembolsar_reserva():
            try:
                # Recalcular el monto de reembolso (por si acaso)
                monto_reembolso, porcentaje_reembolso = reserva.calcular_monto_reembolso(fecha_actual)
                
                # Si es un reembolso del 0%, finalizar la reserva y registrar el reembolso
                if porcentaje_reembolso == 0:
                    # Cambiar estado a FINALIZADA
                    if reserva.finalizar_reserva():
                        # Registrar el reembolso en la base de datos
                        from .models import Reembolso
                        reembolso = Reembolso.objects.create(
                            cliente=reserva.cliente,
                            reserva=reserva,
                            monto=0,
                            dni_cliente=reserva.cliente.dni
                        )
                        
                        # Enviar correo con confirmación
                        envio_exitoso = reserva.enviar_confirmacion_reembolso(0, 0)
                        if envio_exitoso:
                            messages.success(request, "Su reserva ha sido cancelada y finalizada automáticamente. Se ha enviado un correo electrónico con los detalles.")
                        else:
                            messages.warning(request, "Su reserva ha sido cancelada y finalizada, pero hubo un problema al enviar el correo electrónico de confirmación.")
                            
                        messages.info(request, "Como la cancelación se realizó muy cerca de la fecha de inicio, no corresponde reembolso monetario según la política de cancelación.")
                    else:
                        messages.error(request, "La reserva fue cancelada, pero no se pudo finalizar automáticamente. Un empleado la procesará pronto.")
                else:
                    # Para reembolsos con valor > 0%, procesar normalmente
                    # Enviar correo electrónico con detalles del reembolso
                    envio_exitoso = reserva.enviar_confirmacion_reembolso(monto_reembolso, porcentaje_reembolso)
                    if envio_exitoso:
                        messages.success(request, "Se ha enviado un correo electrónico con los detalles del reembolso.")
                    else:
                        messages.warning(request, "La reserva fue cancelada, pero hubo un problema al enviar el correo electrónico de confirmación.")
            except Exception as e:
                messages.warning(request, f"La reserva fue cancelada, pero ocurrió un error al procesar el reembolso: {str(e)}")
            
            # Redirigir a la página de confirmación con detalles del reembolso
            return redirect('reservas:reserva_cancelada', reserva_id=reserva.id)
        else:
            messages.error(request, "No se pudo procesar el reembolso. Por favor, intente nuevamente.")
            return redirect('reservas:lista_reservas')
    
    context = {
        'reserva': reserva,
        'fecha_actual': fecha_actual,
        'dias_hasta_inicio': dias_hasta_inicio,
        'monto_reembolso': monto_reembolso,
        'porcentaje_reembolso': porcentaje_reembolso,
    }
    
    return render(request, 'reservas/confirmar_reembolso.html', context)


@login_required
def reserva_cancelada(request, reserva_id):
    """
    Vista para mostrar la página de confirmación de reserva cancelada con instrucciones
    para el reembolso si corresponde.
    """
    reserva = get_object_or_404(Reserva, id=reserva_id)
    
    # Verificar que el usuario sea el dueño de la reserva o un empleado/admin
    if request.user != reserva.cliente and request.user.tipo not in ['EMPLEADO', 'ADMIN']:
        messages.error(request, "No tiene permisos para ver esta reserva.")
        return redirect('reservas:lista_reservas')
    
    # Verificar que la reserva esté en estado CANCELADA
    if reserva.estado != 'CANCELADA':
        messages.error(request, "Esta página solo aplica para reservas canceladas.")
        return redirect('reservas:lista_reservas')
    
    # Obtener la fecha actual
    fecha_actual = timezone.now().date()
    dias_hasta_inicio = (reserva.fecha_inicio - fecha_actual).days
    
    # Calcular el monto de reembolso según la política
    monto_reembolso, porcentaje_reembolso = reserva.calcular_monto_reembolso(fecha_actual)
    
    context = {
        'reserva': reserva,
        'fecha_actual': fecha_actual,
        'dias_hasta_inicio': dias_hasta_inicio,
        'monto_reembolso': monto_reembolso,
        'porcentaje_reembolso': porcentaje_reembolso,
        'titulo': 'Reserva Cancelada'
    }
    
    return render(request, 'reservas/reserva_cancelada.html', context)

# AJAX Views
@login_required
def buscar_cliente_ajax(request):
    """Vista AJAX para buscar clientes por DNI o nombre"""
    if request.user.tipo not in ['EMPLEADO', 'ADMIN']:
        return JsonResponse({'error': 'No autorizado'}, status=403)
    
    query = request.GET.get('q', '').strip()
    
    if len(query) < 2:
        return JsonResponse({'clientes': []})
    
    clientes = Usuario.objects.filter(
        tipo='CLIENTE'
    ).filter(
        Q(dni__icontains=query) |
        Q(first_name__icontains=query) |
        Q(last_name__icontains=query)
    )[:10]
    
    clientes_data = [{
        'id': cliente.id,
        'nombre': cliente.get_full_name(),
        'dni': cliente.dni,
        'email': cliente.email
    } for cliente in clientes]
    
    return JsonResponse({'clientes': clientes_data})


@login_required
def verificar_disponibilidad_ajax(request):
    """Vista AJAX para verificar disponibilidad de maquinarias"""
    maquinaria_id = request.GET.get('maquinaria_id')
    fecha_inicio = request.GET.get('fecha_inicio')
    fecha_fin = request.GET.get('fecha_fin')
    cantidad = request.GET.get('cantidad')
    
    if not all([maquinaria_id, fecha_inicio, fecha_fin, cantidad]):
        return JsonResponse({'error': 'Faltan parámetros'}, status=400)
    
    try:
        maquinaria = get_object_or_404(Maquinaria, id=maquinaria_id)
        fecha_inicio = datetime.strptime(fecha_inicio, '%Y-%m-%d').date()
        fecha_fin = datetime.strptime(fecha_fin, '%Y-%m-%d').date()
        cantidad = int(cantidad)
        
        disponibilidad = Reserva.verificar_disponibilidad(
            maquinaria=maquinaria,
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
            cantidad_solicitada=cantidad
        )
        
        return JsonResponse(disponibilidad)
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@login_required
def get_sucursales_disponibles(request):
    """
    Vista que devuelve las sucursales que tienen stock disponible para una maquinaria
    en un rango de fechas específico
    """
    try:
        # Obtener y validar parámetros
        maquinaria_id = request.GET.get('maquinaria_id')
        fecha_inicio = request.GET.get('fecha_inicio')
        fecha_fin = request.GET.get('fecha_fin')
        cantidad_solicitada = request.GET.get('cantidad_solicitada')

        # Validar que todos los parámetros necesarios estén presentes
        parametros_faltantes = []
        if not maquinaria_id:
            parametros_faltantes.append("maquinaria")
        if not fecha_inicio:
            parametros_faltantes.append("fecha de inicio")
        if not fecha_fin:
            parametros_faltantes.append("fecha de finalización")
        if not cantidad_solicitada:
            parametros_faltantes.append("cantidad solicitada")
            
        if parametros_faltantes:
            return JsonResponse({
                'error': f'Faltan datos: {", ".join(parametros_faltantes)}'
            }, status=400)

        # Convertir parámetros a sus tipos correctos
        try:
            maquinaria_id = int(maquinaria_id)
            cantidad_solicitada = int(cantidad_solicitada)
            fecha_inicio = datetime.strptime(fecha_inicio, '%Y-%m-%d').date()
            fecha_fin = datetime.strptime(fecha_fin, '%Y-%m-%d').date()
        except (ValueError, TypeError) as e:
            return JsonResponse({
                'error': 'Los datos ingresados no tienen el formato correcto. Por favor, verifique las fechas y la cantidad.'
            }, status=400)

        # Obtener la maquinaria
        try:
            maquinaria = Maquinaria.objects.get(id=maquinaria_id)
        except Maquinaria.DoesNotExist:
            return JsonResponse({
                'error': 'La máquina seleccionada no se encuentra disponible'
            }, status=404)

        # Validar fechas
        if fecha_inicio > fecha_fin:
            return JsonResponse({
                'error': 'La fecha de inicio debe ser anterior o igual a la fecha de finalización'
            }, status=400)

        if fecha_inicio < timezone.now().date():
            return JsonResponse({
                'error': 'La fecha de inicio debe ser igual o posterior a hoy'
            }, status=400)

        # Obtener las sucursales activas con stock disponible
        sucursales_disponibles = []
        
        # Agregar logging para debug
        print(f"Buscando sucursales para maquinaria {maquinaria_id}")
        print(f"Fechas: {fecha_inicio} - {fecha_fin}")
        print(f"Cantidad solicitada: {cantidad_solicitada}")
        
        # Solo buscar en sucursales activas
        for sucursal in Sucursal.objects.filter(activa=True):
            try:
                stock_disponible = sucursal.get_stock_disponible(
                    maquinaria, 
                    fecha_inicio, 
                    fecha_fin,
                    cantidad_solicitada
                )
                print(f"Sucursal {sucursal.nombre}: stock disponible = {stock_disponible}")
                
                if stock_disponible >= cantidad_solicitada:
                    sucursales_disponibles.append({
                        'id': sucursal.id,
                        'nombre': sucursal.nombre,
                        'direccion': sucursal.direccion,
                    })
            except Exception as e:
                print(f"Error al verificar stock en sucursal {sucursal.nombre}: {str(e)}")

        return JsonResponse({
            'sucursales': sucursales_disponibles
        })

    except Exception as e:
        print(f"Error general: {str(e)}")
        return JsonResponse({
            'error': str(e)
        }, status=400)


@login_required
@solo_empleado
def procesar_reservas(request):
    """
    Vista para que los empleados procesen reservas por código.
    Muestra un formulario para ingresar el código de 6 dígitos.
    """
    form = ReservaPorCodigoForm()
    
    context = {
        'form': form,
        'titulo': 'Procesar Reservas',
    }
    
    return render(request, 'reservas/procesar_reservas.html', context)


@login_required
@solo_empleado
def finalizar_reserva_por_codigo(request):
    """
    Vista para procesar la finalización de una reserva mediante su código.
    Comprueba que el código exista, que la reserva esté en estado ENTREGADA, CANCELADA o NO_DEVUELTA,
    y que la sucursal de la reserva coincida con la del empleado.
    
    Si la reserva está en estado CANCELADA, se registra el reembolso correspondiente cuando
    un empleado finaliza la reserva. Solo en este momento se considera efectuado el reembolso.
    """
    if request.method != 'POST':
        return redirect('reservas:procesar_reservas')
    
    form = ReservaPorCodigoForm(request.POST)
    
    if form.is_valid():
        codigo = form.cleaned_data['codigo_reserva']
        dni = form.cleaned_data['dni_cliente']
        action = request.POST.get('action', 'finalizar')
        
        # Debug información sobre la acción
        print(f"*** Acción solicitada: {action}")
        print(f"*** Código de reserva: {codigo}")
        print(f"*** DNI cliente: {dni}")
        
        # Buscar la reserva con ese código
        try:
            print(f"Buscando reserva con código: {codigo}")
            reserva = Reserva.objects.get(codigo_reserva=codigo)
            print(f"Reserva encontrada - Estado: {reserva.estado}, Cliente DNI: {reserva.cliente.dni}")
            
            # Verificar que el DNI coincida con el cliente de la reserva
            if reserva.cliente.dni != dni:
                messages.error(request, "El DNI ingresado no corresponde al cliente de la reserva.")
                return redirect('reservas:procesar_reservas')
        except Reserva.DoesNotExist:
            messages.error(request, f"No se encontró ninguna reserva con el código {codigo}.")
            return redirect('reservas:procesar_reservas')
        
        # Verificar que la sucursal de la reserva coincida con la del empleado
        if reserva.sucursal_retiro != request.user.sucursal:
            messages.error(
                request, 
                f"Esta reserva pertenece a la sucursal {reserva.sucursal_retiro.nombre}. "
                f"No se puede procesarla desde la sucursal {request.user.sucursal.nombre}."
            )
            return redirect('reservas:procesar_reservas')
            
        # Verificar si la reserva ha vencido (pasó su fecha de fin) y actualizarla si es necesario
        reserva.verificar_vencimiento()
        
        # Verificar inmediatamente si la reserva está en estado FINALIZADA
        print(f"*** Estado actual de la reserva: {reserva.estado}")
        if reserva.estado == 'FINALIZADA':
            print(f"*** ALERTA: La reserva ya está en estado FINALIZADA y no puede ser procesada.")
            messages.error(
                request,
                f"La reserva con código {codigo} ya está en estado FINALIZADA y no puede ser procesada nuevamente."
            )
            # Agregar información de depuración
            print(f"*** Redirigiendo a procesar_reservas debido a estado FINALIZADA")
            return redirect('reservas:procesar_reservas')
            
        # Si se presionó el botón de devolución, redirigir al formulario de devolución
        print(f"Action check: '{action}' == 'devolucion'? {action == 'devolucion'}")
        if action == 'devolucion':
            print(f"Entrando en caso de devolución")
            
            # Importar datetime para comparar fechas
            from datetime import date
            today = date.today()
                
            # Verificar el estado de la reserva y la fecha
            if reserva.estado == 'ENTREGADA':
                # Add debug message
                messages.info(request, f"Redirigiendo a formulario de devolución para la reserva")
                # Ensure using the correct URL name and parameter name
                return redirect('reservas:devolucion_reserva', reserva_id=reserva.id)
            elif reserva.estado == 'NO_DEVUELTA':
                # Las NO_DEVUELTA siempre pueden ser procesadas para devolución, independientemente de la fecha
                messages.info(request, f"Redirigiendo a formulario de devolución para la reserva")
                return redirect('reservas:devolucion_reserva', reserva_id=reserva.id)
            elif reserva.estado == 'CONFIRMADA':
                print(f"La reserva está en estado CONFIRMADA y no puede ser procesada para devolución. Debe estar en estado ENTREGADA.")
                messages.warning(
                    request,
                    f"No se puede procesar la devolución. La reserva está en estado CONFIRMADA y debe estar en estado ENTREGADA para poder procesar la devolución."
                )
                return redirect('reservas:procesar_reservas')
            elif reserva.estado == 'PENDIENTE_PAGO':
                print(f"La reserva está en estado PENDIENTE_PAGO y no puede ser procesada para devolución.")
                messages.error(
                    request,
                    f"La reserva está en estado PENDIENTE DE PAGO y no puede ser procesada para devolución."
                )
                return redirect('reservas:procesar_reservas')
            elif reserva.estado == 'CANCELADA':
                print(f"La reserva está en estado CANCELADA y no puede ser procesada para devolución.")
                messages.error(
                    request,
                    f"La reserva está en estado CANCELADA y no puede ser procesada para devolución."
                )
                return redirect('reservas:procesar_reservas')
            else:
                print(f"Reserva no está en estado ENTREGADA o NO_DEVUELTA: {reserva.estado}")
                messages.warning(
                    request,
                    f"Solo se pueden procesar devoluciones para reservas en estado ENTREGADA o NO DEVUELTA."
                )
                return redirect('reservas:procesar_reservas')
                
        # Si se presionó el botón de reembolso, verificar que la reserva esté en estado CANCELADA
        if action == 'reembolso':
            print(f"Entrando en caso de reembolso")
            
            if reserva.estado != 'CANCELADA':
                print(f"Reserva no está en estado CANCELADA: {reserva.estado}")
                messages.error(
                    request,
                    f"Solo se pueden procesar reembolsos para reservas en estado CANCELADA. "
                    f"Esta reserva está en estado {reserva.get_estado_display()}."
                )
                return redirect('reservas:procesar_reservas')
        
        # Procesar según el estado
        print(f"*** Preparando para procesar según el estado: {reserva.estado}")
        
        # Verificar nuevamente el estado FINALIZADA por seguridad
        if reserva.estado == 'FINALIZADA':
            print(f"*** ALERTA CRÍTICA: Intentando procesar una reserva FINALIZADA que no fue detectada anteriormente")
            messages.error(
                request,
                f"La reserva con código {codigo} ya está en estado FINALIZADA y no puede ser procesada nuevamente."
            )
            return redirect('reservas:procesar_reservas')
            
        if reserva.estado in ['ENTREGADA', 'NO_DEVUELTA']:
            # Finalizar la reserva
            print(f"*** Finalizando reserva en estado: {reserva.estado}")
            if reserva.finalizar_reserva():
                messages.success(
                    request, 
                    f"La reserva de {reserva.cliente.get_full_name()} ha sido finalizada correctamente."
                )
            else:
                messages.error(request, "No se pudo finalizar la reserva. Contacte al administrador.")
                
        elif reserva.estado == 'CANCELADA':
            # Solo proceder si la acción es explícitamente reembolso
            if action == 'reembolso':
                # Para reservas canceladas, calcular si aplica reembolso
                monto_reembolso, porcentaje = reserva.calcular_monto_reembolso()
                
                # Finalizar la reserva cancelada
                if reserva.finalizar_reserva():
                    # Registrar el reembolso en la base de datos cuando un empleado finaliza una reserva cancelada
                    from .models import Reembolso
                    
                    # Crear registro de reembolso
                    reembolso = Reembolso.objects.create(
                        cliente=reserva.cliente,
                        reserva=reserva,
                        monto=monto_reembolso,
                        dni_cliente=reserva.cliente.dni
                    )
                    
                    if porcentaje > 0:
                        messages.success(
                            request, 
                            f"✅ REEMBOLSO PROCESADO: La reserva cancelada de {reserva.maquinaria.nombre} para {reserva.cliente.get_full_name()} "
                            f"ha sido finalizada. Se ha registrado un reembolso de ${monto_reembolso:.2f} ({porcentaje}% del total). "
                            f"ID de reembolso: #{reembolso.id}. La reserva ahora está en estado FINALIZADA."
                        )
                    else:
                        messages.success(
                            request, 
                            f"✅ RESERVA CANCELADA PROCESADA: La reserva de {reserva.maquinaria.nombre} para {reserva.cliente.get_full_name()} "
                            f"ha sido finalizada sin reembolso ya que no correspondía según la política de cancelación. "
                            f"La reserva ahora está en estado FINALIZADA."
                        )
                else:
                    messages.error(request, "No se pudo finalizar la reserva cancelada. Contacte al administrador.")
            else:
                # Si la acción no es reembolso pero la reserva está cancelada
                messages.error(
                    request,
                    "Las reservas canceladas solo pueden procesarse con el botón 'Procesar Reembolso'."
                )
                
        elif reserva.estado == 'FINALIZADA':
            # Estado finalizada - mensaje específico
            print(f"*** Detectada reserva finalizada en el catch-all final")
            messages.error(
                request,
                f"La reserva con código {codigo} ya está en estado FINALIZADA y no puede ser procesada nuevamente."
            )
        else:
            # Otro estado no procesable
            print(f"*** Estado no procesable detectado: {reserva.estado}")
            messages.warning(
                request, 
                f"La reserva con código {codigo} tiene el estado {reserva.get_estado_display()}, "
                f"por lo que no se puede procesar."
            )
        
        return redirect('reservas:procesar_reservas')
    
    # Si el formulario no es válido
    context = {
        'form': form,
        'titulo': 'Procesar Reservas',
    }
    
    return render(request, 'reservas/procesar_reservas.html', context)

@login_required
@solo_empleado
def devolucion_reserva(request, reserva_id):
    """
    Vista para mostrar el formulario de devolución de una reserva.
    Permite marcar si la maquinaria necesita servicio y agregar observaciones.
    """
    # Log para debugging
    print(f"Entrando a devolucion_reserva con ID: {reserva_id}")
    
    # Obtener la reserva
    reserva = get_object_or_404(Reserva, id=reserva_id)
    
    # Log información de la reserva
    print(f"Reserva encontrada: {reserva.id}, Estado: {reserva.estado}")
    
    # Verificar si la reserva ha vencido y actualizarla si es necesario
    reserva.verificar_vencimiento()
    
    # Verificar que la reserva esté en estado ENTREGADA o NO_DEVUELTA
    if reserva.estado not in ['ENTREGADA', 'NO_DEVUELTA']:
        messages.error(request, "Solo se pueden procesar devoluciones para reservas en estado ENTREGADA o NO DEVUELTA.")
        return redirect('reservas:procesar_reservas')
    
    # Verificar que la sucursal de la reserva coincida con la del empleado
    if reserva.sucursal_retiro != request.user.sucursal:
        messages.error(
            request, 
            f"Esta reserva pertenece a la sucursal {reserva.sucursal_retiro.nombre}. "
            f"No se puede procesarla desde la sucursal {request.user.sucursal.nombre}."
        )
        return redirect('reservas:procesar_reservas')
    
    form = DevolucionForm()
    
    context = {
        'reserva': reserva,
        'form': form,
    }
    
    return render(request, 'reservas/devolucion_reserva.html', context)


@login_required
@solo_empleado
def confirmar_devolucion(request, reserva_id):
    """
    Vista para procesar la devolución de una reserva.
    Registra si la maquinaria necesita servicio y finaliza la reserva.
    """
    if request.method != 'POST':
        return redirect('reservas:procesar_reservas')
    
    # Obtener la reserva
    reserva = get_object_or_404(Reserva, id=reserva_id)
    
    # Verificar si la reserva ha vencido y actualizarla si es necesario
    reserva.verificar_vencimiento()
    
    # Verificar que la reserva esté en estado ENTREGADA o NO_DEVUELTA
    if reserva.estado not in ['ENTREGADA', 'NO_DEVUELTA']:
        messages.error(request, "Solo se pueden procesar devoluciones para reservas en estado ENTREGADA o NO DEVUELTA.")
        return redirect('reservas:procesar_reservas')
    
    # Verificar que la sucursal de la reserva coincida con la del empleado
    if reserva.sucursal_retiro != request.user.sucursal:
        messages.error(
            request, 
            f"Esta reserva pertenece a la sucursal {reserva.sucursal_retiro.nombre}. "
            f"No se puede procesarla desde la sucursal {request.user.sucursal.nombre}."
        )
        return redirect('reservas:procesar_reservas')
    form = DevolucionForm(request.POST)
    if form.is_valid():
        # Obtener la calificación del cliente y las observaciones
        calificacion_cliente = form.cleaned_data.get('calificacion_cliente', 5.0)
        observaciones = form.cleaned_data.get('observaciones', '')
        
        # Actualizar las observaciones de la reserva
        if observaciones:
            reserva.observaciones = (reserva.observaciones or "") + f"\n\nDEVOLUCIÓN: {observaciones}"
        
        # Guardar los cambios en la reserva
        reserva.save()
            
        # Registrar la calificación en el historial
        from usuarios.calificaciones import CalificacionCliente
        
        # Verificar si ya existe una calificación para esta reserva
        calificacion, creado = CalificacionCliente.objects.get_or_create(
            reserva=reserva,
            defaults={
                'cliente': reserva.cliente,
                'calificacion': calificacion_cliente,
                'observaciones': observaciones
            }
        )
        
        # Si la calificación ya existía, actualizarla
        if not creado:
            calificacion.calificacion = calificacion_cliente
            calificacion.observaciones = observaciones
            calificacion.save()
        
        # Actualizar el promedio de calificaciones del cliente
        # La calificación inicial de 5 estrellas SÍ se incluye en el cálculo del promedio.
        # El promedio se calcula como: (calificación_inicial + suma_calificaciones) / (1 + número_calificaciones)
        cliente = reserva.cliente
        cliente.actualizar_calificacion_promedio()
          # Finalizar la reserva
        if reserva.finalizar_reserva():
            
            messages.success(
                request, 
                f"✅ DEVOLUCIÓN PROCESADA: La maquinaria {reserva.maquinaria.nombre} ({reserva.cantidad_solicitada} unidad/es) "
                f"ha sido devuelta correctamente por {reserva.cliente.get_full_name()} "
                f"La reserva ahora está en estado FINALIZADA."
            )
            messages.info(
                request, 
                f"Se ha registrado una calificación de {calificacion_cliente} estrellas para el cliente. "
                f"Su calificación promedio actual es {reserva.cliente.calificacion} estrellas."
            )
        else:
            messages.error(request, "No se pudo finalizar la reserva. Contacte al administrador.")
    
    return redirect('reservas:procesar_reservas')
        
def gen_preference_mp(request, reserva):
    """Generate Mercado Pago preference for a reservation"""
    try:
        # Verificar que las credenciales estén configuradas
        if not MP_ACCESS_TOKEN or not MP_PUBLIC_KEY:   
            print("Antes de excepcion")
            raise Exception("Credenciales de Mercado Pago no configuradas")

        # URL base de ngrok
        base_url = NGROK_URL

        # Asegurar que tenemos el precio final correcto con cualquier descuento aplicado
        precio_final = float(reserva.precio_total)
        
        # Información de debug
        print(f"=== GEN PREFERENCE DEBUG ===")
        print(f"Preference - Generando preferencia para reserva #{reserva.id}")
        print(f"Preference - Precio total en BD: ${reserva.precio_total}")
        print(f"Preference - Precio final para MP: ${precio_final}")
        
        # Verificar si hay descuentos aplicados
        if hasattr(reserva, 'precio_antes_descuento') and reserva.precio_antes_descuento and hasattr(reserva, 'descuento_aplicado') and reserva.descuento_aplicado:
            print(f"Preference - Precio antes del descuento: ${reserva.precio_antes_descuento}")
            print(f"Preference - Descuento aplicado: ${reserva.descuento_aplicado}")
            
        preference_data = {
            "items": [{
                "title": f"Reserva de {reserva.maquinaria.nombre}",
                "quantity": 1,
                "unit_price": precio_final,
                "currency_id": "ARS",
                "description": f"Reserva desde {reserva.fecha_inicio} hasta {reserva.fecha_fin}"
            }],
            "back_urls": {
                "success": f"{base_url}/reservas/payment/success/{reserva.id}/",
                "failure": f"{base_url}/reservas/payment/failure/{reserva.id}/",
                "pending": f"{base_url}/reservas/payment/pending/{reserva.id}/"
            },
            "auto_return": "approved",
            "notification_url": f"{base_url}/reservas/payment/webhook/",
            "external_reference": str(reserva.id),  # Referencia externa para identificar la reserva
        }
        
        # Log the preference data
        print(f"Creating preference with data: {preference_data}")
        
        # Crear la preferencia
        preference_response = sdk.preference().create(preference_data)
        
        # Log the complete response
        print(f"Complete Mercado Pago response: {preference_response}")
        
        if not preference_response:
            raise Exception("No response from Mercado Pago")
            
        if 'response' not in preference_response:
            raise Exception(f"Invalid response format: {preference_response}")
            
        response_data = preference_response['response']
        
        if 'id' not in response_data:
            raise Exception(f"No preference ID in response: {response_data}")
            
        return response_data
        
    except Exception as e:
        print(f"Error generating payment: {str(e)}")
        raise

# Elimina el @login_required de estas tres funciones
def payment_success(request, reserva_id):
    """Handle successful payment"""
    try:
        reserva = get_object_or_404(Reserva, id=reserva_id)
        
        # Si no hay usuario autenticado, redirigir a la página de inicio o detalles públicos
        if not request.user.is_authenticated:
            reserva.confirmar_pago()
            messages.success(request, '¡Pago realizado con éxito!')
            return redirect('http://127.0.0.1:8000/reservas/historial/')  
        
        # Si hay usuario autenticado verificar permisos
        if request.user != reserva.cliente and not request.user.tipo in ['ADMIN', 'EMPLEADO']:
            return HttpResponseForbidden("No tiene permisos para acceder a esta reserva.")
        
        if reserva.confirmar_pago():
            try:
                reserva.enviar_codigo_reserva()
                messages.success(request, '¡Pago realizado con éxito! Se ha enviado el código de reserva a tu email.')
            except Exception as e:
                messages.warning(request, f'Pago confirmado pero hubo un error al enviar el código: {str(e)}')
        else:
            messages.error(request, 'Error al confirmar el pago. Por favor, contacta a soporte.')
            
    except Reserva.DoesNotExist:
        messages.error(request, 'Reserva no encontrada.')
    except Exception as e:
        logging.error(f"Error en payment_success: {str(e)}")
        messages.error(request, 'Error al procesar el pago. Por favor, contacta a soporte.')
    
    return redirect('reservas:detalle_reserva', reserva_id=reserva_id)

def payment_failure(request, reserva_id):
    """Handle failed payment"""
    try:
        reserva = get_object_or_404(Reserva, id=reserva_id)
        
        # Eliminar la reserva si el pago falló
        if reserva.estado == 'PENDIENTE_PAGO':
            # Guardar datos temporales para mensajes
            cliente = reserva.cliente
            maquinaria_nombre = reserva.maquinaria.nombre
            
            # Eliminar la reserva fallida
            reserva.delete()
            
            logging.info(f"Reserva {reserva_id} eliminada debido a pago fallido")
            
            if not request.user.is_authenticated:
                messages.error(request, 'El pago no pudo ser procesado. La reserva ha sido cancelada.')
                return redirect('http://127.0.0.1:8000/reservas/historial/')
                
            # Verificar que el usuario puede acceder a esta reserva
            if request.user != cliente and not request.user.tipo in ['ADMIN', 'EMPLEADO']:
                return HttpResponseForbidden("No tiene permisos para acceder a esta reserva.")
                
            messages.error(request, f'El pago para {maquinaria_nombre} no pudo ser procesado. La reserva ha sido cancelada. Puede intentar nuevamente desde el catálogo.')
            return redirect('maquinaria_list_cliente')
        else:
            # Si la reserva no está en estado pendiente, simplemente notificar
            if not request.user.is_authenticated:
                messages.error(request, 'El pago no pudo ser procesado.')
                return redirect('http://127.0.0.1:8000/reservas/historial/')
                
            # Verificar que el usuario puede acceder a esta reserva
            if request.user != reserva.cliente and not request.user.tipo in ['ADMIN', 'EMPLEADO']:
                return HttpResponseForbidden("No tiene permisos para acceder a esta reserva.")
                
            messages.error(request, 'El pago no pudo ser procesado. Por favor, intenta nuevamente.')
            return redirect('reservas:detalle_reserva', reserva_id=reserva_id)
            
    except Reserva.DoesNotExist:
        logging.error(f"Reserva {reserva_id} no encontrada al procesar pago fallido")
        messages.error(request, 'No se encontró la reserva asociada al pago.')
        return redirect('maquinaria_list_cliente')
    except Exception as e:
        logging.error(f"Error en payment_failure: {str(e)}")
        messages.error(request, 'Error al procesar la respuesta del pago.')
        return redirect('home')
    

def payment_pending(request, reserva_id):
    """Handle pending payment"""
    try:
        reserva = get_object_or_404(Reserva, id=reserva_id)
        
        # Actualizar el estado de la reserva a PENDIENTE_CONFIRMACION
        if reserva.estado == 'PENDIENTE_PAGO':
            reserva.estado = 'PENDIENTE_CONFIRMACION'
            reserva.save()
            logging.info(f"Reserva {reserva_id} actualizada a estado PENDIENTE_CONFIRMACION")
        
        if not request.user.is_authenticated:
            messages.warning(request, 'Tu pago está pendiente de confirmación. Te notificaremos cuando se complete.')
            return redirect('http://127.0.0.1:8000/reservas/historial/')  
        
        # Verificar que el usuario puede acceder a esta reserva
        if request.user != reserva.cliente and not request.user.tipo in ['ADMIN', 'EMPLEADO']:
            return HttpResponseForbidden("No tiene permisos para acceder a esta reserva.")
            
        messages.warning(request, 'Tu pago está pendiente de confirmación. Te notificaremos cuando se complete.')
    except Reserva.DoesNotExist:
        logging.error(f"Reserva {reserva_id} no encontrada al procesar pago pendiente")
        messages.error(request, 'No se encontró la reserva asociada al pago.')
        return redirect('home')
    except Exception as e:
        logging.error(f"Error en payment_pending: {str(e)}")
        messages.error(request, 'Error al procesar la respuesta del pago.')
    
    return redirect('reservas:detalle_reserva', reserva_id=reserva_id)

@csrf_exempt
def payment_webhook(request):
    """Handle Mercado Pago webhook notifications"""
    # Registrar cada solicitud recibida
    print("Webhook recibido:", request.method)
    
    if request.method == 'POST':
        try:
            # Guardar el contenido completo de la solicitud
            body = request.body.decode('utf-8')
            print(f"Cuerpo del webhook: {body}")
            
            # Intentar parsear los datos
            try:
                data = json.loads(body)
                print(f"Datos parseados: {data}")
            except json.JSONDecodeError:
                print("Error al decodificar JSON")
                data = {}
            
            # Extraer información del tipo de evento
            topic = data.get('topic', '')
            resource = data.get('resource', '')
            
            print(f"Topic: {topic}, Resource: {resource}")
            
            # Procesar notificaciones de merchant_order
            if topic == 'merchant_order' and resource:
                try:
                    # Obtener ID del merchant_order desde la URL del recurso
                    merchant_order_id = resource.split('/')[-1]
                    print(f"Merchant Order ID: {merchant_order_id}")
                    
                    # Obtener información del merchant_order
                    merchant_info = sdk.merchant_order().get(merchant_order_id)
                    print(f"Merchant order info: {merchant_info}")
                    
                    if merchant_info.get('status') == 200:
                        merchant_data = merchant_info.get('response', {})
                        external_reference = merchant_data.get('external_reference')
                        print(f"External reference: {external_reference}")
                        
                        if external_reference:
                            try:
                                reserva = Reserva.objects.get(id=external_reference)
                                print(f"Reserva encontrada: {reserva.id}")
                                
                                # Verificar si hay pagos aprobados
                                payments = merchant_data.get('payments', [])
                                approved_payment = any(p.get('status') == 'approved' for p in payments)
                                
                                if approved_payment:
                                    print("Pago aprobado encontrado, confirmando...")
                                    if reserva.confirmar_pago():
                                        print("Pago confirmado")
                                        try:
                                            reserva.enviar_codigo_reserva()
                                            print("Código de reserva enviado")
                                        except Exception as e:
                                            print(f"Error al enviar código: {str(e)}")
                                
                            except Reserva.DoesNotExist:
                                print(f"Reserva no encontrada para: {external_reference}")
                            except Exception as e:
                                print(f"Error procesando reserva: {str(e)}")
                except Exception as e:
                    print(f"Error procesando merchant_order: {str(e)}")
                    
            # Seguir procesando notificaciones de payment para mantener compatibilidad
            if data.get('type') == 'payment':
                payment_id = data.get('data', {}).get('id')
                print(f"ID de pago recibido: {payment_id}")
                
                if payment_id:
                    payment_info = sdk.payment().get(payment_id)
                    print(f"Información de pago: {payment_info}")
                    
                    if payment_info.get('status') == 200:
                        payment_data = payment_info.get('response', {})
                        external_reference = payment_data.get('external_reference')
                        print(f"Referencia externa: {external_reference}")
                        
                        if external_reference:
                            try:
                                reserva = Reserva.objects.get(id=external_reference)
                                print(f"Reserva encontrada: {reserva.id}")
                                
                                status = payment_data.get('status')
                                print(f"Estado del pago: {status}")
                                
                                if status == 'approved':
                                    print("Intentando confirmar pago...")
                                    if reserva.confirmar_pago():
                                        print("Pago confirmado")
                                        try:
                                            reserva.enviar_codigo_reserva()
                                            print("Código de reserva enviado")
                                        except Exception as e:
                                            print(f"Error al enviar código: {str(e)}")
                                    else:
                                        print("No se pudo confirmar el pago")
                                elif status in ['rejected', 'cancelled']:
                                    # Eliminar la reserva si el pago es rechazado o cancelado
                                    if reserva.estado == 'PENDIENTE_PAGO' or reserva.estado == 'PENDIENTE_CONFIRMACION':
                                        print(f"Eliminando reserva {reserva.id} por pago rechazado/cancelado")
                                        reserva.delete()
                                        logging.info(f"Reserva {reserva.id} eliminada por webhook debido a pago {status}")
                                        
                            except Reserva.DoesNotExist:
                                print(f"Reserva no encontrada para: {external_reference}")
                            except Exception as e:
                                print(f"Error procesando reserva: {str(e)}")
        except Exception as e:
            print(f"Error general en webhook: {str(e)}")
    
    # Siempre devolver 200 OK para que Mercado Pago sepa que recibimos la notificación
    return JsonResponse({'status': 'ok'})

###### QR
import requests

def generar_qr_orden_mp(reserva):
    try:
        import requests
        import json
        from datetime import datetime, timedelta
            
        # Fecha de expiración (15 minutos desde ahora)
        expiration_time = (datetime.utcnow() + timedelta(minutes=15)).isoformat() + "Z"

        # Obtener el access token para extraer el user_id
        access_token = MP_ACCESS_TOKEN
        
        # Asegurar que tenemos el precio final correcto con cualquier descuento aplicado
        precio_final = float(reserva.precio_total)
        
        # Información de debug
        print(f"QR - Generando orden de pago para reserva #{reserva.id}")
        print(f"QR - Precio total: ${precio_final}")
        
        # Verificar si hay descuentos aplicados
        if hasattr(reserva, 'precio_antes_descuento') and reserva.precio_antes_descuento and hasattr(reserva, 'descuento_aplicado') and reserva.descuento_aplicado:
            print(f"QR - Precio antes del descuento: ${reserva.precio_antes_descuento}")
            print(f"QR - Descuento aplicado: ${reserva.descuento_aplicado}")
        
        # Datos básicos para la orden
        order_data = {
            "external_reference": str(reserva.id),
            "title": f"Reserva de {reserva.maquinaria.nombre}",
            "description": f"Reserva desde {reserva.fecha_inicio} hasta {reserva.fecha_fin}",
            "notification_url": f"{NGROK_URL}/reservas/payment/webhook/",
            "total_amount": precio_final,
            "items": [{
                "sku_number": str(reserva.maquinaria.id),
                "category": "alquiler",
                "title": reserva.maquinaria.nombre,
                "description": f"{reserva.cantidad_solicitada} unidad/es del {reserva.fecha_inicio} al {reserva.fecha_fin}",
                "unit_price": precio_final,
                "quantity": 1,
                "unit_measure": "unit",
                "total_amount": precio_final
            }],
            "expiration_date": expiration_time
        }

        # Imprimir el payload para depuración
        print(f"QR order payload: {json.dumps(order_data)}")

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }

        # Primero hacemos una consulta para obtener información del usuario
        user_me_url = "https://api.mercadopago.com/users/me"
        user_response = requests.get(user_me_url, headers=headers)
        
        if user_response.status_code != 200:
            print(f"Error al obtener información del usuario: {user_response.status_code} - {user_response.text}")
            return None
            
        user_info = user_response.json()
        user_id = user_info.get('id')
        
        if not user_id:
            print("No se pudo obtener el ID del usuario de Mercado Pago")
            return None
            
        print(f"ID de usuario de Mercado Pago: {user_id}")
        
        # URL correcta para la API de QR de Mercado Pago usando el ID obtenido
        url = f"https://api.mercadopago.com/instore/orders/qr/seller/collectors/{user_id}/pos/ALQUILAR01/qrs"

        response = requests.post(
            url,
            headers=headers,
            json=order_data
        )

        # Imprimir respuesta para depuración
        print(f"QR API Response status: {response.status_code}")
        print(f"QR API Response body: {response.text}")

        # Revisá status
        if response.status_code not in [200, 201]:
            print(f"Error al generar QR: {response.status_code} - {response.text}")
            
            # Como alternativa, generamos un QR con la URL de pago normal
            try:
                # Creamos una preferencia estándar
                preference = gen_preference_mp(None, reserva)
                if preference and 'init_point' in preference:
                    print("Usando URL de preferencia estándar para el QR")
                    return preference['init_point']
            except Exception as e:
                print(f"Error al generar preferencia alternativa: {str(e)}")
            
            return None

        response_json = response.json()
        
        # El valor correcto para mostrar el QR
        qr_data = response_json.get('qr_data')
        if not qr_data:
            print("No se encontró qr_data en la respuesta")
            return None
            
        return qr_data

    except Exception as e:
        print(f"Error al generar QR dinámico: {str(e)}")
        
        # Como alternativa, intentamos generar un QR con la URL de pago normal
        try:
            # Creamos una preferencia estándar
            preference = gen_preference_mp(None, reserva)
            if preference and 'init_point' in preference:
                print("Usando URL de preferencia estándar para el QR después de una excepción")
                return preference['init_point']
        except Exception as e2:
            print(f"Error al generar preferencia alternativa: {str(e2)}")
            
        return None

@login_required
@solo_empleado
def mostrar_qr_pago(request, reserva_id):
    reserva = get_object_or_404(Reserva, id=reserva_id)

    if reserva.estado != 'PENDIENTE_PAGO' or reserva.tipo_pago != 'PRESENCIAL':
        messages.error(request, "Esta reserva no requiere pago presencial o ya fue pagada.")
        return redirect('reservas:detalle_reserva', reserva_id=reserva.id)
        
    # Refrescar la reserva para asegurar que tenemos los datos más actualizados
    # especialmente si hubo cambios en el precio debido a cupones aplicados
    reserva.refresh_from_db()
    # Ajustar y guardar precio_total según cupón aplicado si no se reflejó en la BD
    if reserva.precio_antes_descuento and reserva.descuento_aplicado and reserva.descuento_aplicado > 0:
        precio_calculado = reserva.precio_antes_descuento - reserva.descuento_aplicado
        reserva.precio_total = precio_calculado
        reserva.save()
    
    # Log para depuración
    print(f"Generando QR para reserva #{reserva.id}")
    print(f"Precio total: ${reserva.precio_total}")
    if hasattr(reserva, 'descuento_aplicado') and reserva.descuento_aplicado:
        print(f"Descuento aplicado: ${reserva.descuento_aplicado}")
    
    qr_data = generar_qr_orden_mp(reserva)

    if not qr_data:
        messages.error(request, "No se pudo generar el QR de pago.")
        return redirect('reservas:detalle_reserva', reserva_id=reserva.id)

    context = {
        'reserva': reserva,
        'qr_data': qr_data
    }
    return render(request, 'reservas/mostrar_qr_pago.html', context)

@login_required
@solo_empleado
def check_payment_status(request, reserva_id):
    """
    Vista AJAX para verificar si una reserva ha sido pagada.
    Retorna JSON con estado de la reserva.
    """
    reserva = get_object_or_404(Reserva, id=reserva_id)
    
    # Verificar que el usuario puede acceder a esta reserva
    if reserva.sucursal_retiro != request.user.sucursal:
        return JsonResponse({
            'success': False,
            'error': 'No tiene permisos para acceder a esta reserva'
        }, status=403)
    
    # Verificar si la reserva ya está confirmada o si sigue pendiente
    estado_anterior = request.GET.get('estado_anterior')
    
    # Si el estado cambió desde la última consulta, considerar que hubo un cambio
    estado_cambio = estado_anterior != reserva.estado if estado_anterior else False
    
    # Si la reserva ya está confirmada, retornar éxito
    if reserva.estado == 'CONFIRMADA':
        return JsonResponse({
            'success': True,
            'status': 'confirmed',
            'message': '¡Pago realizado con éxito!',
            'estado_cambio': estado_cambio
        })
    elif reserva.estado == 'PENDIENTE_PAGO':
        return JsonResponse({
            'success': True,
            'status': 'pending',
            'message': 'Esperando pago...',
            'estado_cambio': estado_cambio
        })
    else:
        return JsonResponse({
            'success': True,
            'status': reserva.estado.lower(),
            'message': f'Estado de la reserva: {reserva.get_estado_display()}',
            'estado_cambio': estado_cambio
        })

@login_required
@solo_empleado
def entregar_reserva_por_codigo(request):
    """
    Vista para procesar la entrega de una reserva mediante su código.
    Comprueba que el código exista, que la reserva esté en estado CONFIRMADA,
    que la fecha de inicio sea hoy o anterior, y que la sucursal de la reserva
    coincida con la del empleado.
    """
    if request.method != 'POST':
        return redirect('reservas:procesar_reservas')
    
    form = ReservaPorCodigoForm(request.POST)
    
    if form.is_valid():
        codigo = form.cleaned_data['codigo_reserva']
        dni = form.cleaned_data['dni_cliente']
        
        # Debug información
        print(f"*** Procesando entrega de reserva - Código: {codigo}, DNI: {dni}")
        
        # Buscar la reserva con ese código
        try:
            reserva = Reserva.objects.get(codigo_reserva=codigo)
            print(f"*** Reserva encontrada - Estado: {reserva.estado}, Cliente DNI: {reserva.cliente.dni}")
            
            # Verificar que el DNI coincida con el cliente de la reserva
            if reserva.cliente.dni != dni:
                messages.error(request, "El DNI ingresado no corresponde al cliente de la reserva.")
                return redirect('reservas:procesar_reservas')
        except Reserva.DoesNotExist:
            messages.error(request, f"No se encontró ninguna reserva con el código {codigo}.")
            return redirect('reservas:procesar_reservas')
        
        # Verificar que la sucursal de la reserva coincida con la del empleado
        if reserva.sucursal_retiro != request.user.sucursal:
            messages.error(
                request, 
                f"Esta reserva pertenece a la sucursal {reserva.sucursal_retiro.nombre}. "
                f"No se puede procesarla desde la sucursal {request.user.sucursal.nombre}."
            )
            return redirect('reservas:procesar_reservas')
            
        # Verificar si la reserva está en estado FINALIZADA
        if reserva.estado == 'FINALIZADA':
            messages.error(
                request,
                f"La reserva con código {codigo} ya está en estado FINALIZADA y no puede ser procesada nuevamente."
            )
            return redirect('reservas:procesar_reservas')
            
        # Verificar si la reserva ya está entregada
        if reserva.estado == 'ENTREGADA':
            messages.error(
                request,
                f"La reserva con código {codigo} ya está en estado ENTREGADA y no puede ser entregada nuevamente."
            )
            return redirect('reservas:procesar_reservas')
            
        # Verificar si la reserva está cancelada
        if reserva.estado == 'CANCELADA':
            messages.error(
                request,
                f"La reserva con código {codigo} está CANCELADA y no puede ser entregada."
            )
            return redirect('reservas:procesar_reservas')
            
        # Verificar si la reserva está en estado NO_DEVUELTA
        if reserva.estado == 'NO_DEVUELTA':
            messages.error(
                request,
                f"La reserva con código {codigo} está en estado NO_DEVUELTA y no puede ser entregada."
            )
            return redirect('reservas:procesar_reservas')
            
        # Verificar si la reserva está en estado PENDIENTE_PAGO
        if reserva.estado == 'PENDIENTE_PAGO':
            messages.error(
                request,
                f"La reserva con código {codigo} está en estado PENDIENTE DE PAGO y no puede ser entregada."
            )
            return redirect('reservas:procesar_reservas')
        
        # Verificar explícitamente que la reserva esté en estado CONFIRMADA
        if reserva.estado != 'CONFIRMADA':
            messages.error(
                request,
                f"La reserva con código {codigo} está en estado {reserva.get_estado_display()} y no puede ser entregada. Solo se pueden entregar reservas en estado CONFIRMADA."
            )
            return redirect('reservas:procesar_reservas')
        
        # Verificar la fecha de inicio
        from datetime import date
        today = date.today()
        
        if reserva.fecha_inicio > today:
            messages.warning(
                request,
                f"No se puede entregar la reserva. La fecha de inicio ({reserva.fecha_inicio}) es posterior a la fecha actual."
            )
            return redirect('reservas:procesar_reservas')
        
        # Marcar la reserva como entregada
        if reserva.marcar_entregada():
            messages.success(
                request, 
                f"✅ ENTREGA PROCESADA: La maquinaria {reserva.maquinaria.nombre} ({reserva.cantidad_solicitada} unidad/es) "
                f"ha sido entregada correctamente a {reserva.cliente.get_full_name()}. "
                f"Período de alquiler: {reserva.fecha_inicio.strftime('%d/%m/%Y')} - {reserva.fecha_fin.strftime('%d/%m/%Y')}. "
                f"La reserva ahora está en estado ENTREGADA."
            )
        else:
            messages.error(
                request, 
                "No se pudo marcar la reserva como entregada. Contacte al administrador."
            )
            
        return redirect('reservas:procesar_reservas')
    
    # Si el formulario no es válido
    messages.error(request, "Por favor, complete correctamente el formulario.")
    return redirect('reservas:procesar_reservas')


@login_required
def aplicar_cupon_view(request, reserva_id):
    """
    Vista para aplicar un cupón de descuento a una reserva.
    """
    reserva = get_object_or_404(Reserva, id=reserva_id)
    
    # Verificar que el usuario puede acceder a esta reserva
    if request.user != reserva.cliente and not request.user.tipo in ['ADMIN', 'EMPLEADO']:
        return HttpResponseForbidden("No tiene permisos para acceder a esta reserva.")
    
    # Verificar que la reserva esté en un estado válido para aplicar cupones
    if reserva.estado != 'PENDIENTE_PAGO':
        messages.error(request, "Solo se pueden aplicar cupones a reservas pendientes de pago.")
        return redirect('reservas:procesar_pago', reserva_id=reserva.id)
    
    # Verificar que no se haya aplicado un cupón previamente
    if reserva.descuento_aplicado > 0:
        messages.error(request, "Ya se ha aplicado un cupón a esta reserva.")
        return redirect('reservas:procesar_pago', reserva_id=reserva.id)
    
    # Crear el formulario para aplicar cupones
    if request.method == 'POST':
        form = AplicarCuponForm(
            request.POST,
            cliente=request.user if request.user.tipo == 'CLIENTE' else reserva.cliente,
            precio_reserva=reserva.precio_total
        )
        
        if form.is_valid():
            # Aplicar el cupón a la reserva
            aplicado = form.aplicar_cupon(reserva)
            
            if aplicado:
                messages.success(request, "¡Cupón aplicado correctamente!")
            else:
                messages.warning(request, "No se pudo aplicar el cupón.")
                
            return redirect('reservas:procesar_pago', reserva_id=reserva.id)
    else:
        form = AplicarCuponForm(
            cliente=request.user if request.user.tipo == 'CLIENTE' else reserva.cliente,
            precio_reserva=reserva.precio_total
        )
    
    return render(request, 'reservas/aplicar_cupon.html', {
        'form': form,
        'reserva': reserva
    })