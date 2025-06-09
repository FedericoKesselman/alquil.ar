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
from maquinarias.models import Maquinaria
from .models import Reserva
from .forms import (
    ReservaForm, SeleccionSucursalForm, ConfirmacionPagoForm,
    BusquedaReservasForm, EditarReservaForm, ReservaEmpleadoForm
)
import decimal


@login_required
def crear_reserva(request, maquinaria_id):
    """Vista unificada para crear reservas (clientes y empleados)"""
    if request.user.tipo not in ['CLIENTE', 'EMPLEADO']:
        messages.error(request, "No tiene permisos para crear reservas.")
        return redirect('home')

    maquinaria = get_object_or_404(Maquinaria, id=maquinaria_id)
    
    if request.method == 'POST':
        form = ReservaForm(request.POST, maquinaria=maquinaria, usuario=request.user)
        if form.is_valid():
            reserva = form.save(commit=False)
            reserva.maquinaria = maquinaria
            
            # Calcular precio total
            dias = (reserva.fecha_fin - reserva.fecha_inicio).days
            reserva.precio_total = maquinaria.precio_por_dia * dias * reserva.cantidad_solicitada
            
            if request.user.tipo == 'EMPLEADO':
                # Para empleados, redirigir a la página de confirmación
                # No guardamos la reserva aún, la guardamos en la vista de confirmación
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
            'maquinaria': maquinaria.id,
            'sucursal_retiro': request.user.sucursal.id if request.user.tipo == 'EMPLEADO' else None
        }
        if request.user.tipo == 'CLIENTE':
            initial_data['cliente'] = request.user.id
        form = ReservaForm(maquinaria=maquinaria, usuario=request.user, initial=initial_data)
    
    return render(request, 'reservas/crear_reserva.html', {
        'form': form,
        'maquinaria': maquinaria,
        'titulo': 'Crear Reserva'
    })


@login_required
@solo_empleado
def confirmar_reservas(request):
    """Vista para confirmar reservas por parte de empleados"""
    if request.method == 'POST':
        if 'confirmar' in request.POST:
            # Obtener los datos de la sesión
            reserva_data = request.session.get('reserva_data')
            if not reserva_data:
                messages.error(request, "No hay datos de reserva para confirmar.")
                return redirect('home')
            
            # Crear la reserva
            reserva = Reserva(
                cliente_id=reserva_data['cliente_id'],
                maquinaria_id=reserva_data['maquinaria_id'],
                fecha_inicio=datetime.fromisoformat(reserva_data['fecha_inicio']),
                fecha_fin=datetime.fromisoformat(reserva_data['fecha_fin']),
                cantidad_solicitada=reserva_data['cantidad_solicitada'],
                sucursal_retiro_id=reserva_data['sucursal_retiro_id'],
                precio_total=decimal.Decimal(reserva_data['precio_total']),
                empleado_procesador_id=reserva_data['empleado_id'],
                estado='CONFIRMADA',
                tipo_pago='PRESENCIAL'
            )
            reserva.save()
            
            # Limpiar los datos de la sesión
            del request.session['reserva_data']
            
            messages.success(request, "Reserva confirmada exitosamente.")
            return redirect('reservas:detalle_reserva', reserva_id=reserva.id)
        else:
            # Si se cancela, simplemente limpiar la sesión y redirigir
            if 'reserva_data' in request.session:
                del request.session['reserva_data']
            messages.info(request, "Reserva cancelada.")
            return redirect('home')
    
    # Obtener los datos de la reserva de la sesión
    reserva_data = request.session.get('reserva_data')
    if not reserva_data:
        messages.error(request, "No hay datos de reserva para confirmar.")
        return redirect('home')
    
    # Obtener los objetos relacionados
    cliente = get_object_or_404(Usuario, id=reserva_data['cliente_id'])
    maquinaria = get_object_or_404(Maquinaria, id=reserva_data['maquinaria_id'])
    sucursal = get_object_or_404(Sucursal, id=reserva_data['sucursal_retiro_id'])
    
    context = {
        'cliente': cliente,
        'maquinaria': maquinaria,
        'sucursal': sucursal,
        'fecha_inicio': datetime.fromisoformat(reserva_data['fecha_inicio']),
        'fecha_fin': datetime.fromisoformat(reserva_data['fecha_fin']),
        'cantidad_solicitada': reserva_data['cantidad_solicitada'],
        'precio_total': reserva_data['precio_total'],
        'titulo': 'Confirmar Reserva',
        'reserva_data': {
            'fecha_inicio': datetime.fromisoformat(reserva_data['fecha_inicio']),
            'fecha_fin': datetime.fromisoformat(reserva_data['fecha_fin']),
            'cantidad_solicitada': reserva_data['cantidad_solicitada']
        }
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
            messages.success(request, 'Pago confirmado. Su reserva ha sido procesada exitosamente.')
            return redirect('detalle_reserva', reserva_id=reserva.id)
    
    context = {
        'reserva': reserva,
        'titulo': 'Procesar Pago',
    }
    
    return render(request, 'reservas/procesar_pago.html', context)


@login_required
@solo_empleado
def lista_reservas_empleado(request):
    """Vista para que los empleados vean todas las reservas"""
    reservas = Reserva.objects.all().order_by('-fecha_creacion')
    return render(request, 'reservas/lista_reservas_empleado.html', {
        'reservas': reservas
    })


@login_required
def lista_reservas(request):
    """Vista para que los clientes vean sus reservas"""
    reservas = Reserva.objects.filter(cliente=request.user).order_by('-fecha_creacion')
    return render(request, 'reservas/lista_reservas.html', {
        'reservas': reservas
    })


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

        # Obtener las sucursales con stock disponible
        sucursales_disponibles = []
        
        # Agregar logging para debug
        print(f"Buscando sucursales para maquinaria {maquinaria_id}")
        print(f"Fechas: {fecha_inicio} - {fecha_fin}")
        print(f"Cantidad solicitada: {cantidad_solicitada}")
        
        for sucursal in Sucursal.objects.all():
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