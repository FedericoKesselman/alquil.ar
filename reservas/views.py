# reservas/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse, HttpResponseForbidden
from django.core.paginator import Paginator
from django.db.models import Q
from django.utils import timezone
from datetime import datetime, timedelta
from usuarios.decorators import solo_cliente, solo_empleado, solo_admin
from usuarios.models import Usuario, Sucursal
from maquinarias.models import Maquinaria, MaquinariaStock
from .models import Reserva
from .forms import (
    ReservaForm, SeleccionSucursalForm, ConfirmacionPagoForm,
    BusquedaReservasForm, EditarReservaForm, ReservaEmpleadoForm,
    ReservaPorCodigoForm, DevolucionForm
)
import decimal
import logging


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
            dias = (reserva.fecha_fin - reserva.fecha_inicio).days
            precio_por_dia = maquinaria.get_precio_para_cliente(reserva.cliente)
            reserva.precio_total = precio_por_dia * dias * reserva.cantidad_solicitada
            
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
                    'precio_total': str(reserva.precio_total),
                    'empleado_id': request.user.id
                }
                messages.info(request, "Por favor, confirme los detalles de la reserva.")
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
                    'precio_total': str(reserva.precio_total)
                }
                messages.info(request, "Por favor, confirme los detalles de la reserva.")
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
                
                # Obtener la maquinaria y cliente para calcular el precio total
                maquinaria = Maquinaria.objects.get(id=reserva_data['maquinaria_id'])
                cliente = Usuario.objects.get(id=reserva_data['cliente_id'])
                fecha_inicio = datetime.strptime(reserva_data['fecha_inicio'], '%Y-%m-%d').date()
                fecha_fin = datetime.strptime(reserva_data['fecha_fin'], '%Y-%m-%d').date()
                dias = (fecha_fin - fecha_inicio).days + 1
                
                # Aplicar recargo según calificación del cliente
                precio_por_dia, _ = maquinaria.get_precio_para_cliente(cliente)
                precio_total = precio_por_dia * dias * reserva_data['cantidad_solicitada']
                
                # Crear la reserva
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
                    empleado_procesador=request.user  # Guardar el empleado que procesa la reserva
                )
                
                # Intentar confirmar la reserva
                try:
                    if reserva.confirmar_reserva():
                        messages.success(request, "Reserva confirmada exitosamente")
                    else:
                        # Obtener información del stock disponible
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
                            
                            mensaje_error = f"Para las fechas seleccionadas solo hay {stock_disponible} unidad/es disponible/s. Por favor, seleccione una cantidad o fecha distinta."
                        except Exception as e:
                            mensaje_error = "No se pudo confirmar la reserva. Por favor, intente nuevamente."
                            
                        messages.error(request, mensaje_error)
                        reserva.delete()
                except ValueError as e:
                    messages.error(request, str(e))
                    reserva.delete()
                except Exception as e:
                    logger.error(f"Error al confirmar reserva: {str(e)}")
                    messages.error(request, "Error al confirmar la reserva")
                    reserva.delete()
                
                # Limpiar datos de la sesión
                del request.session['reserva_data']
                
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
    
    # GET request - mostrar página de confirmación
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
    precio_total = precio_por_dia * dias * reserva_data['cantidad_solicitada']
    
    context = {
        'cliente': cliente,
        'maquinaria': maquinaria,
        'sucursal': sucursal,
        'fecha_inicio': reserva_data['fecha_inicio'],
        'fecha_fin': reserva_data['fecha_fin'],
        'cantidad_solicitada': reserva_data['cantidad_solicitada'],
        'precio_total': precio_total,
        'titulo': 'Confirmar Reserva'
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
                
                # Obtener la maquinaria para calcular el precio total
                maquinaria = Maquinaria.objects.get(id=reserva_data['maquinaria_id'])
                fecha_inicio = datetime.strptime(reserva_data['fecha_inicio'], '%Y-%m-%d').date()
                fecha_fin = datetime.strptime(reserva_data['fecha_fin'], '%Y-%m-%d').date()
                dias = (fecha_fin - fecha_inicio).days
                
                # Aplicar recargo según calificación del cliente
                precio_por_dia, _ = maquinaria.get_precio_para_cliente(cliente)
                precio_total = precio_por_dia * dias * int(reserva_data['cantidad_solicitada'])
                
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
                
                # TODO: Proceso de pago online
                # Por ahora, simplemente marcaremos la reserva como confirmada
                try:
                    if reserva.confirmar_reserva():
                        messages.success(request, "¡Reserva confirmada exitosamente! Se ha enviado un correo con los detalles.")
                    else:
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
                            
                            mensaje_error = f"Para las fechas seleccionadas solo hay {stock_disponible} unidad/es disponible/s. Por favor, seleccione una cantidad o fecha distinta."
                        except Exception as e:
                            mensaje_error = "No se pudo confirmar la reserva. Por favor, intente nuevamente."
                            
                        messages.error(request, mensaje_error)
                        reserva.delete()
                except Exception as e:
                    logger.error(f"Error al confirmar reserva: {str(e)}")
                    messages.error(request, "Error al confirmar la reserva")
                    reserva.delete()
                
                # Limpiar datos de la sesión
                if 'reserva_data' in request.session:
                    del request.session['reserva_data']
                
                return redirect('home')
            
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
    dias = (fecha_fin - fecha_inicio).days
    precio_por_dia, porcentaje_recargo = maquinaria.get_precio_para_cliente(cliente)
    precio_total = precio_por_dia * dias * int(reserva_data['cantidad_solicitada'])
    
    context = {
        'cliente': cliente,
        'maquinaria': maquinaria,
        'sucursal': sucursal,
        'fecha_inicio': reserva_data['fecha_inicio'],
        'fecha_fin': reserva_data['fecha_fin'],
        'cantidad_solicitada': reserva_data['cantidad_solicitada'],
        'precio_total': precio_total,
        'titulo': 'Confirmar Reserva',
        'aplicar_recargo': porcentaje_recargo > 0,
        'porcentaje_recargo': porcentaje_recargo
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
    
    if request.method == 'POST':
        form = SeleccionSucursalForm(request.POST, sucursales_disponibles=sucursales_info)
        
        if form.is_valid():
            # Agregar la sucursal seleccionada a los datos de la sesión
            reserva_data['sucursal_retiro_id'] = form.cleaned_data['sucursal_retiro'].id
            request.session['reserva_data'] = reserva_data
            
            return redirect('confirmar_reserva')
    else:
        form = SeleccionSucursalForm(sucursales_disponibles=sucursales_info)
    
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
            # Si es cliente, redirigir al proceso de pago online
            return redirect('reservas:procesar_pago', reserva_id=reserva.id)
    
    return render(request, 'reservas/confirmar_reserva.html', {
        'reserva': reserva,
        'maquinaria': reserva.maquinaria,
        'sucursal': reserva.sucursal_retiro,
        'dias': (reserva.fecha_fin - reserva.fecha_inicio).days,
        'precio_por_dia': reserva.maquinaria.precio_por_dia,
        'precio_total': reserva.precio_total,
        'es_empleado': request.user.tipo == 'EMPLEADO'
    })


@login_required
def procesar_pago(request, reserva_id):
    """Vista temporal para simular el pago (aquí se integrará Mercado Pago)"""
    reserva = get_object_or_404(Reserva, id=reserva_id)
    
    # Verificar que el usuario puede acceder a esta reserva
    if request.user != reserva.cliente and not request.user.tipo in ['ADMIN', 'EMPLEADO']:
        return HttpResponseForbidden("No tiene permisos para acceder a esta reserva.")
    
    if request.method == 'POST':
        # Simular confirmación de pago
        if reserva.confirmar_pago():
            try:
                # Generar y enviar código de reserva
                reserva.enviar_codigo_reserva()
                messages.success(request, 'Pago confirmado y código de reserva enviado. Su reserva ha sido procesada exitosamente.')
            except Exception as e:
                messages.warning(request, f'Pago confirmado pero hubo un error al enviar el código: {str(e)}')
            return redirect('detalle_reserva', reserva_id=reserva.id)
    
    context = {
        'reserva': reserva,
        'titulo': 'Procesar Pago',
    }
    
    return render(request, 'reservas/procesar_pago.html', context)


@login_required
def lista_reservas(request):
    """Vista para listar reservas según el tipo de usuario"""
    # Actualizar automáticamente las reservas vencidas
    reservas_actualizadas = Reserva.actualizar_reservas_vencidas()
    if reservas_actualizadas > 0 and (request.user.tipo == 'ADMIN' or request.user.tipo == 'EMPLEADO'):
        messages.info(request, f"Se actualizaron {reservas_actualizadas} reservas vencidas a estado 'No Devuelta'.")
    
    # Obtener parámetros de filtrado
    estado = request.GET.get('estado')
    fecha_desde = request.GET.get('fecha_desde')
    fecha_hasta = request.GET.get('fecha_hasta')
    cliente_dni = request.GET.get('cliente_dni', '').strip()
    empleado_dni = request.GET.get('empleado_dni', '').strip()
    sucursal_id = request.GET.get('sucursal')
      # Iniciar el queryset base según el tipo de usuario
    if request.user.tipo == 'ADMIN' or request.user.tipo == 'EMPLEADO':
        # Administradores y empleados ven todas las reservas
        reservas = Reserva.objects.all()
        # Obtener lista de sucursales para el filtro
        sucursales = Sucursal.objects.filter(activa=True).order_by('nombre')
    else:
        # Clientes ven sus propias reservas
        reservas = Reserva.objects.filter(cliente=request.user)
        sucursales = None
      # Aplicar filtros si existen
    if estado:
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
        'cliente_dni': cliente_dni,  # DNI del cliente para mantener el filtro
        'empleado_dni': empleado_dni,  # DNI del empleado para mantener el filtro
    }
    
    return render(request, 'reservas/lista_reservas.html', context)


@login_required
def detalle_reserva(request, reserva_id):
    """Vista para ver los detalles de una reserva"""
    if request.user.is_staff:
        reserva = get_object_or_404(Reserva, id=reserva_id)
    else:
        reserva = get_object_or_404(Reserva, id=reserva_id, cliente=request.user)
    
    return render(request, 'reservas/detalle_reserva.html', {
        'reserva': reserva
    })


@login_required
def cancelar_reserva(request, reserva_id):
    """Vista para cancelar una reserva"""
    reserva = get_object_or_404(Reserva, id=reserva_id)
    
    # Verificar permisos
    if request.user.tipo == 'CLIENTE' and reserva.cliente != request.user:
        return HttpResponseForbidden("No puede cancelar esta reserva.")
    elif request.user.tipo not in ['CLIENTE', 'EMPLEADO', 'ADMIN']:
        return HttpResponseForbidden("No tiene permisos para cancelar reservas.")
    
    if request.method == 'POST':
        if reserva.cancelar():
            messages.success(request, 'Reserva cancelada exitosamente.')
        else:
            messages.error(request, 'No se pudo cancelar la reserva.')
        
        # Redirigir según el tipo de usuario
        if request.user.tipo == 'CLIENTE':
            return redirect('mis_reservas')
        else:
            return redirect('listar_reservas')
    
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
    Vista para mostrar la página de confirmación de reembolso de una reserva.
    Calcula el monto de reembolso según la política establecida.
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
    
    # Obtener la fecha actual
    fecha_actual = timezone.now().date()
    dias_hasta_inicio = (reserva.fecha_inicio - fecha_actual).days
    
    # Calcular el monto de reembolso según la política
    monto_reembolso, porcentaje_reembolso = reserva.calcular_monto_reembolso(fecha_actual)
    
    # Si es un POST, procesar la confirmación del reembolso
    if request.method == 'POST':
        # Procesar el reembolso y restaurar stock
        if reserva.reembolsar_reserva():
            # Obtener el nombre de la sucursal
            nombre_sucursal = reserva.sucursal_retiro.nombre
            
            # Mostrar mensaje según el tipo de reembolso
            if porcentaje_reembolso > 0:  # Reembolso total o parcial
                messages.success(
                    request, 
                    f"Acércate a la sucursal {nombre_sucursal} para que te reintegremos el monto de ${monto_reembolso:.2f}"
                )
            else:  # Reembolso nulo
                messages.success(
                    request, 
                    f"Reembolso efectuado, acércate a {nombre_sucursal} para devolvernos la maquinaria"
                )
        else:
            messages.error(request, "No se pudo procesar el reembolso. Por favor, intente nuevamente.")
        
        return redirect('home')
    
    context = {
        'reserva': reserva,
        'fecha_actual': fecha_actual,
        'dias_hasta_inicio': dias_hasta_inicio,
        'monto_reembolso': monto_reembolso,
        'porcentaje_reembolso': porcentaje_reembolso,
    }
    
    return render(request, 'reservas/confirmar_reembolso.html', context)


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
        if not all([maquinaria_id, fecha_inicio, fecha_fin, cantidad_solicitada]):
            return JsonResponse({
                'error': 'Faltan parámetros requeridos'
            }, status=400)

        # Convertir parámetros a sus tipos correctos
        try:
            maquinaria_id = int(maquinaria_id)
            cantidad_solicitada = int(cantidad_solicitada)
            fecha_inicio = datetime.strptime(fecha_inicio, '%Y-%m-%d').date()
            fecha_fin = datetime.strptime(fecha_fin, '%Y-%m-%d').date()
        except (ValueError, TypeError) as e:
            return JsonResponse({
                'error': f'Formato de parámetros inválido: {str(e)}'
            }, status=400)

        # Obtener la maquinaria
        try:
            maquinaria = Maquinaria.objects.get(id=maquinaria_id)
        except Maquinaria.DoesNotExist:
            return JsonResponse({
                'error': 'Maquinaria no encontrada'
            }, status=404)

        # Validar fechas
        if fecha_inicio > fecha_fin:
            return JsonResponse({
                'error': 'La fecha de inicio debe ser anterior a la fecha de fin'
            }, status=400)

        if fecha_inicio < timezone.now().date():
            return JsonResponse({
                'error': 'La fecha de inicio debe ser posterior a hoy'
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
    Comprueba que el código exista, que la reserva esté en estado CONFIRMADA o CANCELADA,
    y que la sucursal de la reserva coincida con la del empleado.
    """
    if request.method != 'POST':
        return redirect('reservas:procesar_reservas')
    
    form = ReservaPorCodigoForm(request.POST)
    
    if form.is_valid():
        codigo = form.cleaned_data['codigo_reserva']
        dni = form.cleaned_data['dni_cliente']
        action = request.POST.get('action', 'finalizar')
        
        # Debug información sobre la acción
        print(f"Acción solicitada: {action}")
        
        # Buscar la reserva con ese código
        try:
            reserva = Reserva.objects.get(codigo_reserva=codigo)
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
                f"No puedes procesarla desde {request.user.sucursal.nombre}."
            )
            return redirect('reservas:procesar_reservas')
            
        # Verificar si la reserva ha vencido (pasó su fecha de fin) y actualizarla si es necesario
        reserva.verificar_vencimiento()
        
        # Si se presionó el botón de devolución, redirigir al formulario de devolución
        print(f"Action check: '{action}' == 'devolucion'? {action == 'devolucion'}")
        if action == 'devolucion':
            print(f"Entrando en caso de devolución")
            if reserva.estado in ['CONFIRMADA', 'NO_DEVUELTA']:
                # Add debug message
                messages.info(request, f"Redirigiendo a formulario de devolución para la reserva")
                # Ensure using the correct URL name and parameter name
                return redirect('reservas:devolucion_reserva', reserva_id=reserva.id)
            else:
                print(f"Reserva no está en estado CONFIRMADA o NO_DEVUELTA: {reserva.estado}")
                messages.warning(
                    request,
                    f"Solo se pueden procesar devoluciones para reservas en estado CONFIRMADA o NO DEVUELTA."
                )
                return redirect('reservas:procesar_reservas')
        
        # Procesar según el estado
        if reserva.estado in ['CONFIRMADA', 'NO_DEVUELTA']:
            # Finalizar la reserva
            if reserva.finalizar_reserva():
                messages.success(
                    request, 
                    f"La reserva de {reserva.cliente.get_full_name()} ha sido finalizada correctamente."
                )
            else:
                messages.error(request, "No se pudo finalizar la reserva. Contacte al administrador.")
                
        elif reserva.estado == 'CANCELADA':
            # Para reservas canceladas, calcular si aplica reembolso
            monto_reembolso, porcentaje = reserva.calcular_monto_reembolso()
            
            # Finalizar la reserva cancelada
            if reserva.finalizar_reserva():
                if porcentaje > 0:
                    messages.success(
                        request, 
                        f"La reserva cancelada de {reserva.cliente.get_full_name()} ha sido finalizada. "
                        f"Debes reembolsar ${monto_reembolso:.2f} ({porcentaje}% del total)."
                    )
                else:
                    messages.success(
                        request, 
                        f"La reserva cancelada de {reserva.cliente.get_full_name()} ha sido finalizada sin reembolso."
                    )
            else:
                messages.error(request, "No se pudo finalizar la reserva cancelada. Contacte al administrador.")
                
        else:
            # Estado no procesable
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
    
    # Verificar que la reserva esté en estado CONFIRMADA o NO_DEVUELTA
    if reserva.estado not in ['CONFIRMADA', 'NO_DEVUELTA']:
        messages.error(request, "Solo se pueden procesar devoluciones para reservas en estado CONFIRMADA o NO DEVUELTA.")
        return redirect('reservas:procesar_reservas')
    
    # Verificar que la sucursal de la reserva coincida con la del empleado
    if reserva.sucursal_retiro != request.user.sucursal:
        messages.error(
            request, 
            f"Esta reserva pertenece a la sucursal {reserva.sucursal_retiro.nombre}. "
            f"No puedes procesarla desde {request.user.sucursal.nombre}."
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
    
    # Verificar que la reserva esté en estado CONFIRMADA o NO_DEVUELTA
    if reserva.estado not in ['CONFIRMADA', 'NO_DEVUELTA']:
        messages.error(request, "Solo se pueden procesar devoluciones para reservas en estado CONFIRMADA o NO DEVUELTA.")
        return redirect('reservas:procesar_reservas')
    
    # Verificar que la sucursal de la reserva coincida con la del empleado
    if reserva.sucursal_retiro != request.user.sucursal:
        messages.error(
            request, 
            f"Esta reserva pertenece a la sucursal {reserva.sucursal_retiro.nombre}. "
            f"No puedes procesarla desde {request.user.sucursal.nombre}."
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
        cliente = reserva.cliente
        cliente.actualizar_calificacion_promedio()
          # Finalizar la reserva
        if reserva.finalizar_reserva():
            messages.success(
                request, 
                f"La devolución de {reserva.cliente.get_full_name()} ha sido procesada correctamente."
            )
            messages.info(
                request, 
                f"Se ha registrado una calificación de {calificacion_cliente} estrellas para el cliente. "
                f"Su calificación promedio actual es {reserva.cliente.calificacion} estrellas."
            )
        else:
            messages.error(request, "No se pudo finalizar la reserva. Contacte al administrador.")
    
    return redirect('reservas:procesar_reservas')