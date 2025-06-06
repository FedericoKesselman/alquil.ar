# reservas/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseForbidden
from django.core.paginator import Paginator
from django.db.models import Q
from django.utils import timezone
from datetime import datetime, timedelta
from usuarios.decorators import solo_cliente, solo_empleado, solo_admin
from usuarios.models import Usuario, Sucursal
from maquinarias.models import Maquinaria
from .models import Reserva
from .forms import (
    ReservaForm, SeleccionSucursalForm, ConfirmacionPagoForm,
    BusquedaReservasForm, EditarReservaForm
)


@login_required
@solo_cliente
def crear_reserva_cliente(request, maquinaria_id):
    """Vista para que los clientes creen reservas"""
    maquinaria = get_object_or_404(Maquinaria, id=maquinaria_id)
    
    if request.method == 'POST':
        form = ReservaForm(request.POST, maquinaria=maquinaria, usuario=request.user)
        
        if form.is_valid():
            # Guardar los datos de la reserva en la sesión
            request.session['reserva_data'] = {
                'maquinaria_id': maquinaria.id,
                'fecha_inicio': form.cleaned_data['fecha_inicio'].strftime('%Y-%m-%d'),
                'fecha_fin': form.cleaned_data['fecha_fin'].strftime('%Y-%m-%d'),
                'cantidad_solicitada': form.cleaned_data['cantidad_solicitada'],
                'precio_total': float(form.calcular_precio_total()),
                'sucursales_disponibles': [
                    {
                        'sucursal_id': info['sucursal'].id,
                        'sucursal_nombre': info['sucursal'].nombre,
                        'sucursal_direccion': info['sucursal'].direccion,
                        'stock_disponible': info['stock_disponible']
                    }
                    for info in form.sucursales_disponibles
                ]
            }
            
            return redirect('seleccionar_sucursal')
    else:
        form = ReservaForm(maquinaria=maquinaria, usuario=request.user)
    
    context = {
        'form': form,
        'maquinaria': maquinaria,
        'titulo': f'Reservar {maquinaria.nombre}',
    }
    
    return render(request, 'reservas/crear_reserva.html', context)


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
@solo_cliente
def confirmar_reserva(request):
    """Vista para confirmar la reserva antes del pago"""
    reserva_data = request.session.get('reserva_data')
    
    if not reserva_data or 'sucursal_retiro_id' not in reserva_data:
        messages.error(request, 'Datos de reserva incompletos. Por favor, inicie el proceso nuevamente.')
        return redirect('maquinarias_cliente')
    
    maquinaria = get_object_or_404(Maquinaria, id=reserva_data['maquinaria_id'])
    sucursal = get_object_or_404(Sucursal, id=reserva_data['sucursal_retiro_id'])
    
    if request.method == 'POST':
        # Crear la reserva
        try:
            reserva = Reserva.objects.create(
                cliente=request.user,
                maquinaria=maquinaria,
                sucursal_retiro=sucursal,
                fecha_inicio=datetime.strptime(reserva_data['fecha_inicio'], '%Y-%m-%d').date(),
                fecha_fin=datetime.strptime(reserva_data['fecha_fin'], '%Y-%m-%d').date(),
                cantidad_solicitada=reserva_data['cantidad_solicitada'],
                precio_total=reserva_data['precio_total'],
                tipo_pago='ONLINE',
                estado='PENDIENTE_PAGO'
            )
            
            # Limpiar la sesión
            if 'reserva_data' in request.session:
                del request.session['reserva_data']
            
            messages.success(request, f'Reserva creada exitosamente. ID: {reserva.id}')
            
            # Redirigir al pago (por ahora, simularemos)
            return redirect('procesar_pago', reserva_id=reserva.id)
            
        except Exception as e:
            messages.error(request, f'Error al crear la reserva: {str(e)}')
    
    context = {
        'reserva_data': reserva_data,
        'maquinaria': maquinaria,
        'sucursal': sucursal,
        'titulo': 'Confirmar Reserva',
    }
    
    return render(request, 'reservas/confirmar_reserva.html', context)


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
            messages.success(request, 'Pago confirmado. Su reserva ha sido procesada exitosamente.')
            return redirect('detalle_reserva', reserva_id=reserva.id)
    
    context = {
        'reserva': reserva,
        'titulo': 'Procesar Pago',
    }
    
    return render(request, 'reservas/procesar_pago.html', context)


@login_required
@solo_empleado
def crear_reserva_empleado(request, maquinaria_id):
    """Vista para que empleados creen reservas para clientes"""
    maquinaria = get_object_or_404(Maquinaria, id=maquinaria_id)
    
    # Buscar cliente por DNI si se proporciona
    cliente = None
    if request.GET.get('cliente_dni'):
        try:
            cliente = Usuario.objects.get(dni=request.GET['cliente_dni'], tipo='CLIENTE')
        except Usuario.DoesNotExist:
            messages.error(request, 'Cliente no encontrado con ese DNI.')
    
    if request.method == 'POST':
        # Verificar que se ha seleccionado un cliente
        cliente_id = request.POST.get('cliente_id')
        if not cliente_id:
            messages.error(request, 'Debe seleccionar un cliente.')
            return redirect(request.path)
        
        cliente = get_object_or_404(Usuario, id=cliente_id, tipo='CLIENTE')
        form = ReservaForm(request.POST, maquinaria=maquinaria, usuario=cliente)
        
        if form.is_valid():
            # Crear la reserva directamente (pago presencial)
            try:
                reserva = Reserva(
                    cliente=cliente,
                    maquinaria=maquinaria,
                    fecha_inicio=form.cleaned_data['fecha_inicio'],
                    fecha_fin=form.cleaned_data['fecha_fin'],
                    cantidad_solicitada=form.cleaned_data['cantidad_solicitada'],
                    tipo_pago='PRESENCIAL',
                    estado='PENDIENTE_PAGO',
                    empleado_procesador=request.user
                )
                
                # Calcular precio
                dias = (reserva.fecha_fin - reserva.fecha_inicio).days
                reserva.precio_total = maquinaria.precio_por_dia * dias * reserva.cantidad_solicitada
                
                # Seleccionar sucursal (por defecto la del empleado, o la primera disponible)
                sucursales_disponibles = form.sucursales_disponibles
                if request.user.sucursal and any(s['sucursal'] == request.user.sucursal for s in sucursales_disponibles):
                    reserva.sucursal_retiro = request.user.sucursal
                else:
                    reserva.sucursal_retiro = sucursales_disponibles[0]['sucursal']
                
                reserva.save()
                
                messages.success(request, f'Reserva creada exitosamente. ID: {reserva.id}')
                return redirect('confirmar_pago_empleado', reserva_id=reserva.id)
                
            except Exception as e:
                messages.error(request, f'Error al crear la reserva: {str(e)}')
    else:
        form = ReservaForm(maquinaria=maquinaria, usuario=cliente)
    
    # Buscar clientes para el autocomplete
    clientes = Usuario.objects.filter(tipo='CLIENTE')[:10] if not cliente else [cliente]
    
    context = {
        'form': form,
        'maquinaria': maquinaria,
        'cliente': cliente,
        'clientes': clientes,
        'titulo': f'Crear Reserva - {maquinaria.nombre}',
    }
    
    return render(request, 'reservas/crear_reserva_empleado.html', context)


@login_required
@solo_empleado
def confirmar_pago_empleado(request, reserva_id):
    """Vista para que empleados confirmen pagos presenciales"""
    reserva = get_object_or_404(Reserva, id=reserva_id)
    
    # Verificar que el empleado puede confirmar este pago
    if reserva.tipo_pago != 'PRESENCIAL' or reserva.estado != 'PENDIENTE_PAGO':
        messages.error(request, 'Esta reserva no requiere confirmación de pago presencial.')
        return redirect('listar_reservas_empleado')
    
    if request.method == 'POST':
        form = ConfirmacionPagoForm(request.POST)
        
        if form.is_valid():
            # Confirmar el pago
            reserva.observaciones = form.cleaned_data.get('observaciones', '')
            if reserva.confirmar_pago(empleado=request.user):
                messages.success(request, 'Pago confirmado exitosamente.')
                return redirect('detalle_reserva', reserva_id=reserva.id)
    else:
        form = ConfirmacionPagoForm()
    
    context = {
        'form': form,
        'reserva': reserva,
        'titulo': 'Confirmar Pago Presencial',
    }
    
    return render(request, 'reservas/confirmar_pago_empleado.html', context)


@login_required
def detalle_reserva(request, reserva_id):
    """Vista para ver el detalle de una reserva"""
    reserva = get_object_or_404(Reserva, id=reserva_id)
    
    # Verificar permisos
    if (request.user.tipo == 'CLIENTE' and reserva.cliente != request.user) and \
       request.user.tipo not in ['ADMIN', 'EMPLEADO']:
        return HttpResponseForbidden("No tiene permisos para acceder a esta reserva.")
    
    context = {
        'reserva': reserva,
        'titulo': f'Reserva #{reserva.id}',
    }
    
    return render(request, 'reservas/detalle_reserva.html', context)


@login_required
@solo_cliente
def mis_reservas(request):
    """Vista para que los clientes vean sus reservas"""
    reservas = Reserva.objects.filter(cliente=request.user).order_by('-fecha_creacion')
    
    # Paginación
    paginator = Paginator(reservas, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'titulo': 'Mis Reservas',
    }
    
    return render(request, 'reservas/mis_reservas.html', context)


@login_required
def listar_reservas_empleado(request):
    """Vista para que empleados y admins vean todas las reservas"""
    if request.user.tipo not in ['EMPLEADO', 'ADMIN']:
        return HttpResponseForbidden("No tiene permisos para acceder a esta sección.")
    
    # Filtros
    form = BusquedaReservasForm(request.GET)
    reservas = Reserva.objects.all().select_related('cliente', 'maquinaria', 'sucursal_retiro')
    
    if form.is_valid():
        # Filtrar por cliente
        if form.cleaned_data.get('cliente'):
            cliente_query = form.cleaned_data['cliente']
            reservas = reservas.filter(
                Q(cliente__first_name__icontains=cliente_query) |
                Q(cliente__last_name__icontains=cliente_query) |
                Q(cliente__dni__icontains=cliente_query)
            )
        
        # Filtrar por estado
        if form.cleaned_data.get('estado'):
            reservas = reservas.filter(estado=form.cleaned_data['estado'])
        
        # Filtrar por fechas
        if form.cleaned_data.get('fecha_desde'):
            reservas = reservas.filter(fecha_inicio__gte=form.cleaned_data['fecha_desde'])
        
        if form.cleaned_data.get('fecha_hasta'):
            reservas = reservas.filter(fecha_fin__lte=form.cleaned_data['fecha_hasta'])
        
        # Filtrar por maquinaria
        if form.cleaned_data.get('maquinaria'):
            reservas = reservas.filter(maquinaria__nombre__icontains=form.cleaned_data['maquinaria'])
    
    # Ordenar por fecha de creación (más recientes primero)
    reservas = reservas.order_by('-fecha_creacion')
    
    # Paginación
    paginator = Paginator(reservas, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'form': form,
        'page_obj': page_obj,
        'titulo': 'Gestión de Reservas',
    }
    
    return render(request, 'reservas/listar_reservas_empleado.html', context)


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
            return redirect('listar_reservas_empleado')
    
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