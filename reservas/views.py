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
import logging
import os
import mercadopago
from django.urls import reverse
from dotenv import load_dotenv

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
                return redirect('reservas:procesar_pago', reserva_id=reserva.id)
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
                    precio_total=precio_total
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
            preference = gen_preference_mp(request, reserva)
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
    """Vista para procesar el pago de una reserva usando Mercado Pago"""
    try:
        reserva = get_object_or_404(Reserva, id=reserva_id)
        
        # Verificar que el usuario puede acceder a esta reserva
        if request.user != reserva.cliente and not request.user.tipo in ['ADMIN', 'EMPLEADO']:
            return HttpResponseForbidden("No tiene permisos para acceder a esta reserva.")
        
        # Generar preferencia de Mercado Pago
        try:
            preference = gen_preference_mp(request, reserva)
            preference_id = preference.get('id')
            
            if not preference_id:
                raise Exception("No se pudo obtener el ID de preferencia de Mercado Pago")
                
            context = {
                'reserva': reserva,
                'MP_PUBLIC_KEY': MP_PUBLIC_KEY,
                'preference_id': preference_id,
                'titulo': 'Procesar Pago',
            }
            
            return render(request, 'reservas/procesar_pago.html', context)
            
        except Exception as e:
            logging.error(f"Error al generar preferencia de pago: {str(e)}")
            messages.error(request, "Error al procesar el pago. Por favor, intente nuevamente más tarde.")
            return redirect('reservas:detalle_reserva', reserva_id=reserva.id)
            
    except Exception as e:
        logging.error(f"Error en procesar_pago: {str(e)}")
        messages.error(request, "Error al procesar la solicitud. Por favor, intente nuevamente.")
        return redirect('home')


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
        
def gen_preference_mp(request, reserva):
    """Generate Mercado Pago preference for a reservation"""
    try:
        # Verificar que las credenciales estén configuradas
        if not MP_ACCESS_TOKEN or not MP_PUBLIC_KEY:
            raise Exception("Credenciales de Mercado Pago no configuradas")

        # URL base de ngrok
        base_url = NGROK_URL

        preference_data = {
            "items": [{
                "title": f"Reserva de {reserva.maquinaria.nombre}",
                "quantity": 1,
                "unit_price": float(reserva.precio_total),
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
        logging.info(f"Creating preference with data: {preference_data}")
        
        # Crear la preferencia
        preference_response = sdk.preference().create(preference_data)
        
        # Log the complete response
        logging.info(f"Complete Mercado Pago response: {preference_response}")
        
        if not preference_response:
            raise Exception("No response from Mercado Pago")
            
        if 'response' not in preference_response:
            raise Exception(f"Invalid response format: {preference_response}")
            
        response_data = preference_response['response']
        
        if 'id' not in response_data:
            raise Exception(f"No preference ID in response: {response_data}")
            
        return response_data
        
    except Exception as e:
        logging.error(f"Error generating payment: {str(e)}")
        raise

@login_required
def payment_success(request, reserva_id):
    """Handle successful payment"""
    try:
        reserva = get_object_or_404(Reserva, id=reserva_id)
        
        # Verificar que el usuario puede acceder a esta reserva
        if request.user != reserva.cliente and not request.user.tipo in ['ADMIN', 'EMPLEADO']:
            return HttpResponseForbidden("No tiene permisos para acceder a esta reserva.")
        
        payment_id = request.GET.get('payment_id')
        external_reference = request.GET.get('external_reference')
        
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

@login_required
def payment_failure(request, reserva_id):
    """Handle failed payment"""
    try:
        reserva = get_object_or_404(Reserva, id=reserva_id)
        
        # Verificar que el usuario puede acceder a esta reserva
        if request.user != reserva.cliente and not request.user.tipo in ['ADMIN', 'EMPLEADO']:
            return HttpResponseForbidden("No tiene permisos para acceder a esta reserva.")
            
        messages.error(request, 'El pago no pudo ser procesado. Por favor, intenta nuevamente.')
    except Exception as e:
        logging.error(f"Error en payment_failure: {str(e)}")
        messages.error(request, 'Error al procesar la respuesta del pago.')
    
    return redirect('reservas:detalle_reserva', reserva_id=reserva_id)

@login_required
def payment_pending(request, reserva_id):
    """Handle pending payment"""
    try:
        reserva = get_object_or_404(Reserva, id=reserva_id)
        
        # Verificar que el usuario puede acceder a esta reserva
        if request.user != reserva.cliente and not request.user.tipo in ['ADMIN', 'EMPLEADO']:
            return HttpResponseForbidden("No tiene permisos para acceder a esta reserva.")
            
        messages.warning(request, 'Tu pago está pendiente de confirmación.')
    except Exception as e:
        logging.error(f"Error en payment_pending: {str(e)}")
        messages.error(request, 'Error al procesar la respuesta del pago.')
    
    return redirect('reservas:detalle_reserva', reserva_id=reserva_id)

@login_required
def payment_webhook(request):
    """Handle Mercado Pago webhook notifications"""
    if request.method == 'POST':
        try:
            data = request.POST
            if data.get('type') == 'payment':
                payment_id = data.get('data', {}).get('id')
                payment_info = sdk.payment().get(payment_id)
                
                if payment_info['status'] == 200:
                    payment_data = payment_info['response']
                    external_reference = payment_data.get('external_reference')
                    
                    if external_reference:
                        try:
                            reserva = Reserva.objects.get(id=external_reference)
                            if payment_data.get('status') == 'approved':
                                if reserva.confirmar_pago():
                                    reserva.enviar_codigo_reserva()
                                    logging.info(f"Pago confirmado y código enviado para reserva {reserva.id}")
                        except Reserva.DoesNotExist:
                            logging.error(f"Reserva no encontrada para external_reference: {external_reference}")
                        except Exception as e:
                            logging.error(f"Error procesando webhook para reserva {external_reference}: {str(e)}")
                
        except Exception as e:
            logging.error(f"Error processing webhook: {str(e)}")
    
    return JsonResponse({'status': 'ok'})