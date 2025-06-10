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
    BusquedaReservasForm, EditarReservaForm, ReservaEmpleadoForm
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
        form = ReservaForm(request.POST, maquinaria=maquinaria, usuario=request.user)
        if form.is_valid():
            # Si es cliente, verificar que no tenga una reserva activa
            if request.user.tipo == 'CLIENTE':
                reserva_activa = Reserva.objects.filter(
                    cliente=request.user,
                    estado='CONFIRMADA'
                ).exists()
                
                if reserva_activa:
                    messages.error(request, "Ya tienes una reserva activa. No puedes tener más de una reserva confirmada a la vez.")
                    return redirect('home')
            # Si es empleado, verificar que el cliente seleccionado no tenga una reserva activa
            elif request.user.tipo == 'EMPLEADO':
                cliente = form.cleaned_data['cliente']
                reserva_activa = Reserva.objects.filter(
                    cliente=cliente,
                    estado='CONFIRMADA'
                ).exists()
                
                if reserva_activa:
                    messages.error(request, "El cliente seleccionado ya tiene una reserva activa. No puede tener más de una reserva confirmada a la vez.")
                    return redirect('home')
            
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
            
            # Calcular precio total
            dias = (reserva.fecha_fin - reserva.fecha_inicio).days
            reserva.precio_total = maquinaria.precio_por_dia * dias * reserva.cantidad_solicitada
            
            if request.user.tipo == 'EMPLEADO':
                # Para empleados, redirigir a la página de confirmación
                request.session['reserva_data'] = {
                    'cliente_id': form.cleaned_data['cliente'].id,
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
                # Para clientes, guardar como pendiente y redirigir al pago
                reserva.cliente = request.user
                reserva.estado = 'PENDIENTE_PAGO'
                reserva.tipo_pago = 'ONLINE'
                reserva.save()
                # TODO: Redirigir a la página de pago cuando esté implementada
                messages.info(request, "Página de pago en construcción")
                return redirect('home')
        else:
            messages.error(request, "Por favor, corrija los errores en el formulario.")
    else:
        initial_data = {
            'maquinaria': maquinaria.id
        }
        if request.user.tipo == 'CLIENTE':
            initial_data['cliente'] = request.user.id
        form = ReservaForm(initial=initial_data, maquinaria=maquinaria, usuario=request.user)
    
    return render(request, 'reservas/crear_reserva.html', {
        'form': form,
        'maquinaria': maquinaria,
        'titulo': 'Crear Reserva'
    })


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
                
                # Verificar si el cliente ya tiene una reserva confirmada
                cliente = Usuario.objects.get(id=reserva_data['cliente_id'])
                reserva_activa = Reserva.objects.filter(
                    cliente=cliente,
                    estado='CONFIRMADA'
                ).exists()
                
                if reserva_activa:
                    messages.error(request, "El cliente ya tiene una reserva activa. No puede tener más de una reserva confirmada a la vez.")
                    return redirect('home')
                
                # Obtener la maquinaria para calcular el precio total
                maquinaria = Maquinaria.objects.get(id=reserva_data['maquinaria_id'])
                fecha_inicio = datetime.strptime(reserva_data['fecha_inicio'], '%Y-%m-%d').date()
                fecha_fin = datetime.strptime(reserva_data['fecha_fin'], '%Y-%m-%d').date()
                dias = (fecha_fin - fecha_inicio).days + 1
                precio_total = maquinaria.precio_por_dia * dias * reserva_data['cantidad_solicitada']
                
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
    precio_total = maquinaria.precio_por_dia * dias * reserva_data['cantidad_solicitada']
    
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
    # Obtener parámetros de filtrado
    estado = request.GET.get('estado')
    fecha_desde = request.GET.get('fecha_desde')
    fecha_hasta = request.GET.get('fecha_hasta')
    
    # Iniciar el queryset base según el tipo de usuario
    if request.user.tipo == 'ADMIN':
        # Administradores ven todas las reservas
        reservas = Reserva.objects.all()
    elif request.user.tipo == 'EMPLEADO':
        # Empleados ven las reservas que han procesado
        reservas = Reserva.objects.filter(empleado_procesador=request.user)
    else:
        # Clientes ven sus propias reservas
        reservas = Reserva.objects.filter(cliente=request.user)
    
    # Aplicar filtros si existen
    if estado:
        reservas = reservas.filter(estado=estado)
    
    if fecha_desde:
        reservas = reservas.filter(fecha_inicio__gte=fecha_desde)
    
    if fecha_hasta:
        reservas = reservas.filter(fecha_fin__lte=fecha_hasta)
    
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
        'titulo': 'Historial de Reservas'
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