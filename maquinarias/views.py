import django
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.views.generic import ListView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.forms import formset_factory
from django import forms
from django.http import JsonResponse, HttpResponseRedirect
from django.urls import reverse
from .models import Maquinaria, TipoMaquinaria, MaquinariaStock, MaquinariaFavorita
from .forms import (MaquinariaForm, MaquinariaUpdateForm, TipoMaquinariaForm, 
                   MaquinariaStockFormSet, MaquinariaStockForm)
from usuarios.decorators import solo_admin, solo_empleado, solo_cliente
from usuarios.models import Sucursal

# Vistas para Tipos de Maquinaria
@login_required
@solo_admin
def tipo_maquinaria_list(request):
    tipos = TipoMaquinaria.objects.all().order_by('nombre')
    return render(request, 'maquinarias/tipo_maquinaria_list.html', {'tipos': tipos})

@login_required
@solo_admin
def tipo_maquinaria_create(request):
    if request.method == 'POST':
        form = TipoMaquinariaForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Tipo de maquinaria creado exitosamente.')
            return redirect('tipo_maquinaria_list')
    else:
        form = TipoMaquinariaForm()
    return render(request, 'maquinarias/tipo_maquinaria_form.html', {'form': form, 'action': 'Crear'})

@login_required
@solo_admin
def tipo_maquinaria_update(request, pk):
    tipo = get_object_or_404(TipoMaquinaria, pk=pk)
    if request.method == 'POST':
        form = TipoMaquinariaForm(request.POST, instance=tipo)
        if form.is_valid():
            form.save()
            messages.success(request, 'Tipo de maquinaria actualizado exitosamente.')
            return redirect('tipo_maquinaria_list')
    else:
        form = TipoMaquinariaForm(instance=tipo)
    return render(request, 'maquinarias/tipo_maquinaria_form.html', {'form': form, 'action': 'Editar'})

@login_required
@solo_admin
def tipo_maquinaria_delete(request, pk):
    tipo = get_object_or_404(TipoMaquinaria, pk=pk)
    try:
        tipo.delete()
        messages.success(request, 'Tipo de maquinaria eliminado exitosamente.')
    except Exception as e:
        messages.error(request, 'No se puede eliminar este tipo de maquinaria porque está siendo utilizado.')
    return redirect('tipo_maquinaria_list')

# Vistas para Maquinarias
@login_required
@solo_admin
def maquinaria_list(request):
    maquinarias = Maquinaria.objects.all().order_by('nombre')
    paginator = Paginator(maquinarias, 10)
    page = request.GET.get('page')
    maquinarias = paginator.get_page(page)
    return render(request, 'maquinarias/maquinaria_list.html', {'maquinarias': maquinarias})

def maquinaria_list_cliente(request):
    # Verificar si el usuario está autenticado y es cliente o empleado
    if not request.user.is_authenticated or (request.user.tipo not in ['CLIENTE', 'EMPLEADO']):
        # Query base sin filtros para usuarios no autenticados - mostrar maquinarias con stock en al menos una sucursal activa
        maquinarias = Maquinaria.objects.filter(
            stocks__stock__gt=0,
            stocks__sucursal__activa=True
        ).distinct().order_by('nombre')
        
        # Paginación
        paginator = Paginator(maquinarias, 12)
        page = request.GET.get('page')
        maquinarias = paginator.get_page(page)
        
        return render(request, 'maquinarias/maquinaria_list_cliente.html', {'maquinarias': maquinarias})

    # Obtener los parámetros de filtrado
    search_query = request.GET.get('search', '').strip()
    tipo_id = request.GET.get('tipo')
    precio_min = request.GET.get('precio_min')
    precio_max = request.GET.get('precio_max')
    sucursal_id = request.GET.get('sucursal')
    
    # Query base inicial - maquinarias que tienen stock en al menos una sucursal activa
    base_queryset = Maquinaria.objects.filter(
        stocks__stock__gt=0,
        stocks__sucursal__activa=True
    ).distinct()

    # Aplicar filtros y obtener queryset filtrado
    filtered_queryset = base_queryset

    # Aplicar búsqueda por nombre si existe
    if search_query:
        filtered_queryset = filtered_queryset.filter(nombre__icontains=search_query)

    # Aplicar filtro de tipo si existe
    if tipo_id:
        filtered_queryset = filtered_queryset.filter(tipo_id=tipo_id)
    
    # Aplicar filtro de sucursal si existe
    if sucursal_id:
        filtered_queryset = filtered_queryset.filter(
            stocks__sucursal_id=sucursal_id,
            stocks__sucursal__activa=True,
            stocks__stock__gt=0
        )
    
    # Aplicar filtros de precio
    if precio_min:
        try:
            filtered_queryset = filtered_queryset.filter(precio_por_dia__gte=float(precio_min))
        except ValueError:
            pass
    
    if precio_max:
        try:
            filtered_queryset = filtered_queryset.filter(precio_por_dia__lte=float(precio_max))
        except ValueError:
            pass
    
    # Obtener tipos de maquinaria disponibles según los filtros actuales
    # Un tipo está disponible si al menos una de sus maquinarias tiene stock en una sucursal activa
    base_tipos_query = TipoMaquinaria.objects.filter(
        maquinarias__stocks__stock__gt=0,
        maquinarias__stocks__sucursal__activa=True
    ).distinct()

    if search_query:
        base_tipos_query = base_tipos_query.filter(maquinarias__nombre__icontains=search_query)

    if sucursal_id:
        # Si hay filtro de sucursal, mostrar tipos que tienen maquinarias en esa sucursal activa
        tipos_disponibles = base_tipos_query.filter(
            maquinarias__stocks__sucursal_id=sucursal_id,
            maquinarias__stocks__sucursal__activa=True,
            maquinarias__stocks__stock__gt=0
        ).distinct()
    else:
        tipos_disponibles = base_tipos_query

    # Obtener sucursales activas disponibles según los filtros actuales
    base_sucursales_query = Sucursal.objects.filter(
        activa=True,
        stocks__stock__gt=0
    )

    if search_query:
        base_sucursales_query = base_sucursales_query.filter(
            stocks__maquinaria__nombre__icontains=search_query
        )

    if tipo_id:
        # Si hay filtro de tipo, mostrar solo sucursales activas que tienen ese tipo
        sucursales_disponibles = base_sucursales_query.filter(
            stocks__maquinaria__tipo_id=tipo_id,
            stocks__stock__gt=0
        ).distinct()
    else:
        # Si no hay filtro de tipo, mostrar sucursales activas que tienen cualquier maquinaria con stock
        sucursales_disponibles = base_sucursales_query.distinct()
    
    # Ordenar resultados
    filtered_queryset = filtered_queryset.order_by('nombre')
    
    # Paginación
    paginator = Paginator(filtered_queryset, 12)
    page = request.GET.get('page')
    maquinarias = paginator.get_page(page)
    
    context = {
        'maquinarias': maquinarias,
        'tipos': tipos_disponibles.order_by('nombre'),
        'sucursales': sucursales_disponibles.order_by('nombre'),
        'filtros': {
            'search': search_query,
            'tipo': tipo_id,
            'sucursal': sucursal_id,
            'precio_min': precio_min,
            'precio_max': precio_max
        },
        'is_cliente': request.user.tipo == 'CLIENTE',
        'is_empleado': request.user.tipo == 'EMPLEADO',
        'cliente': request.user if request.user.is_authenticated and request.user.tipo == 'CLIENTE' else None
    }
    
    # Agregar información sobre recargos si es cliente
    if request.user.is_authenticated and request.user.tipo == 'CLIENTE':
        if request.user.calificacion <= 1.0:
            context['aplicar_recargo'] = True
            context['porcentaje_recargo'] = 30
        elif request.user.calificacion <= 2.0:
            context['aplicar_recargo'] = True
            context['porcentaje_recargo'] = 20
            
        # Obtener los IDs de maquinarias favoritas del cliente
        favoritos_ids = MaquinariaFavorita.objects.filter(
            usuario=request.user
        ).values_list('maquinaria_id', flat=True)
        
        context['favoritos_ids'] = set(favoritos_ids)
    
    return render(request, 'maquinarias/maquinaria_list_cliente.html', context)

@login_required
@solo_admin
def maquinaria_create(request):
    # Verificar si existen sucursales activas y tipos de maquinaria
    if not Sucursal.objects.filter(activa=True).exists():
        messages.error(request, 'Para registrar una maquinaria, primero deben haber sucursales y tipos de maquinaria registrados.')
        return redirect('home')
    
    if not TipoMaquinaria.objects.exists():
        messages.error(request, 'Para registrar una maquinaria, primero deben haber sucursales y tipos de maquinaria registrados.')
        return redirect('home')

    if request.method == 'POST':
        form = MaquinariaForm(request.POST, request.FILES)
        stock_formset = MaquinariaStockFormSet(request.POST, prefix='stocks')
        
        formset_is_valid = True
        if stock_formset.is_valid():
            # Procesar datos del formset
            stocks_data = []
            for stock_form in stock_formset:
                if stock_form.cleaned_data and not stock_form.cleaned_data.get('DELETE', False):
                    try:
                        stock_form.clean()
                        stocks_data.append(stock_form.cleaned_data)
                    except forms.ValidationError as e:
                        messages.error(request, f"Error en el stock de sucursal: {e.messages[0]}")
                        formset_is_valid = False
                        break
            
            # Validar que se haya asignado al menos una sucursal con stock válido
            if not stocks_data and formset_is_valid:
                messages.error(request, 'Debe asignar la maquinaria a al menos una sucursal con stock mayor a 0.')
                formset_is_valid = False
        else:
            formset_is_valid = False
            for form_errors in stock_formset.errors:
                for field, errors in form_errors.items():
                    for error in errors:
                        messages.error(request, f"Error en el stock de sucursal: {error}")
        
        if form.is_valid() and formset_is_valid:
            maquinaria = form.save(stocks_data=stocks_data)
            messages.success(request, 'Maquinaria creada exitosamente.')
            return redirect('maquinaria_list')
    else:
        form = MaquinariaForm()
        stock_formset = MaquinariaStockFormSet(prefix='stocks')
    
    context = {
        'form': form,
        'stock_formset': stock_formset,
        'action': 'Crear',
        'sucursales': Sucursal.objects.filter(activa=True)
    }
    return render(request, 'maquinarias/maquinaria_form.html', context)

@login_required
@solo_admin
def maquinaria_update(request, pk):
    maquinaria = get_object_or_404(Maquinaria, pk=pk)
    
    if request.method == 'POST':
        form = MaquinariaUpdateForm(request.POST, request.FILES, instance=maquinaria)
        stock_formset = MaquinariaStockFormSet(request.POST, prefix='stocks')
        
        formset_is_valid = True
        if stock_formset.is_valid():
            # Procesar datos del formset
            stocks_data = []
            for stock_form in stock_formset:
                if stock_form.cleaned_data:
                    try:
                        stock_form.clean()
                        stocks_data.append(stock_form.cleaned_data)
                    except forms.ValidationError as e:
                        messages.error(request, f"Error en el stock de sucursal: {e.messages[0]}")
                        formset_is_valid = False
                        break
            
            # Validar que se haya asignado al menos una sucursal con stock válido
            if not stocks_data and formset_is_valid:
                messages.error(request, 'Debe asignar la maquinaria a al menos una sucursal con stock mayor a 0.')
                formset_is_valid = False
        else:
            formset_is_valid = False
            for form_errors in stock_formset.errors:
                for field, errors in form_errors.items():
                    for error in errors:
                        messages.error(request, f"Error en el stock de sucursal: {error}")
        
        if form.is_valid() and formset_is_valid:
            maquinaria = form.save(stocks_data=stocks_data)
            messages.success(request, 'Maquinaria actualizada exitosamente.')
            return redirect('maquinaria_list')
    else:
        form = MaquinariaUpdateForm(instance=maquinaria)
        
        # Inicializar formset con datos existentes
        initial_data = []
        for stock in maquinaria.stocks.all():
            initial_data.append({
                'sucursal': stock.sucursal,
                'stock': stock.stock
            })
        
        stock_formset = MaquinariaStockFormSet(
            initial=initial_data,
            prefix='stocks'
        )
    
    context = {
        'form': form,
        'stock_formset': stock_formset,
        'action': 'Editar',
        'maquinaria': maquinaria,
        'sucursales': Sucursal.objects.filter(activa=True)
    }
    return render(request, 'maquinarias/maquinaria_form.html', context)

@login_required
@solo_admin
def maquinaria_delete(request, pk):
    maquinaria = get_object_or_404(Maquinaria, pk=pk)
    try:
        # Intentar eliminar la maquinaria
        nombre_maquinaria = maquinaria.nombre
        maquinaria.delete()
        messages.success(request, f'Maquinaria "{nombre_maquinaria}" eliminada exitosamente.')
    except django.db.models.deletion.ProtectedError as e:
        # Mostrar el mensaje de error personalizado
        messages.error(request, "No se puede eliminar la maquinaria porque tiene reservas que no están finalizadas.")
    except Exception as e:
        # Para otros tipos de errores
        messages.error(request, f'Error al eliminar la maquinaria: {str(e)}')
        
        # Registrar el error para debug
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error inesperado al eliminar maquinaria {maquinaria.id}: {str(e)}")
        
    return redirect('maquinaria_list')

@login_required
def maquinaria_detail(request, pk):
    maquinaria = get_object_or_404(Maquinaria, pk=pk)
    context = {
        'maquinaria': maquinaria,
    }
    
    # Si es empleado, mostrar el stock de su sucursal
    if request.user.tipo == 'EMPLEADO' and hasattr(request.user, 'sucursal') and request.user.sucursal:
        try:
            stock_sucursal = MaquinariaStock.objects.get(
                maquinaria=maquinaria,
                sucursal=request.user.sucursal
            )
            context['stock_sucursal'] = stock_sucursal
        except MaquinariaStock.DoesNotExist:
            context['stock_sucursal'] = None
    
    # Si es cliente, verificar si tiene 2 estrellas o menos para aplicar recargo
    if request.user.is_authenticated and request.user.tipo == 'CLIENTE':
        context['cliente'] = request.user
        precio_ajustado, porcentaje_recargo = maquinaria.get_precio_para_cliente(request.user)
        context['aplicar_recargo'] = porcentaje_recargo > 0
        context['porcentaje_recargo'] = porcentaje_recargo
        context['precio_con_recargo'] = precio_ajustado
        
        # Verificar si la maquinaria está en favoritos
        is_favorito = MaquinariaFavorita.objects.filter(
            usuario=request.user, 
            maquinaria=maquinaria
        ).exists()
        
        context['is_favorito'] = is_favorito
    
    return render(request, 'maquinarias/maquinaria_detail.html', context)


class MaquinariaListCliente(LoginRequiredMixin, ListView):
    model = Maquinaria
    template_name = 'maquinarias/maquinaria_list_cliente.html'
    context_object_name = 'maquinarias'
    paginate_by = 9

    def get_queryset(self):
        # Mostrar maquinarias que tienen stock en al menos una sucursal activa
        return Maquinaria.objects.filter(
            stocks__stock_disponible__gt=0,
            stocks__sucursal__activa=True
        ).distinct().order_by('nombre')

@login_required
@solo_cliente
def maquinarias_favoritas(request):
    """Vista para mostrar las maquinarias favoritas del cliente"""
    favoritos = MaquinariaFavorita.objects.filter(usuario=request.user).select_related('maquinaria')
    
    # Paginar los resultados
    paginator = Paginator(favoritos, 12)
    page = request.GET.get('page')
    favoritos = paginator.get_page(page)
    
    context = {
        'favoritos': favoritos,
        'is_cliente': True,
    }
    
    return render(request, 'maquinarias/maquinarias_favoritas.html', context)

@login_required
@solo_cliente
def agregar_favorito(request, pk):
    """Vista para agregar una maquinaria a favoritos"""
    maquinaria = get_object_or_404(Maquinaria, pk=pk)
    
    # Verificar si ya existe como favorito
    favorito_existente = MaquinariaFavorita.objects.filter(usuario=request.user, maquinaria=maquinaria).exists()
    
    if not favorito_existente:
        # Crear el nuevo favorito
        MaquinariaFavorita.objects.create(usuario=request.user, maquinaria=maquinaria)
        messages.success(request, f"¡{maquinaria.nombre} añadida a tus favoritos!")
    else:
        messages.info(request, "Esta maquinaria ya está en tus favoritos")
    
    # Redirigir a la página anterior
    referer = request.META.get('HTTP_REFERER')
    if referer:
        return HttpResponseRedirect(referer)
    else:
        return redirect('maquinaria_list_cliente')

@login_required
@solo_cliente
def eliminar_favorito(request, pk):
    """Vista para eliminar una maquinaria de favoritos"""
    favorito = get_object_or_404(MaquinariaFavorita, maquinaria_id=pk, usuario=request.user)
    nombre_maquinaria = favorito.maquinaria.nombre
    favorito.delete()
    messages.success(request, f"{nombre_maquinaria} ha sido eliminada de tus favoritos")
    
    # Redirigir a la página anterior o a favoritos
    referer = request.META.get('HTTP_REFERER')
    if referer and 'favoritos' in referer:
        return HttpResponseRedirect(referer)
    else:
        return redirect('maquinaria_list_cliente')