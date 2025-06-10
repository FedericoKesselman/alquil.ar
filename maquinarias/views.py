from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.views.generic import ListView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.forms import formset_factory
from .models import Maquinaria, TipoMaquinaria, MaquinariaStock
from .forms import (MaquinariaForm, MaquinariaUpdateForm, TipoMaquinariaForm, 
                   MaquinariaStockFormSet, MaquinariaStockForm)
from usuarios.decorators import solo_admin, solo_empleado
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
        # Query base sin filtros para usuarios no autenticados
        maquinarias = Maquinaria.objects.filter(
            stocks__stock_disponible__gt=0
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
    
    # Query base: maquinarias con stock disponible
    base_queryset = Maquinaria.objects.filter(
        stocks__stock_disponible__gt=0
    ).distinct()

    # Si es empleado, filtrar solo por su sucursal
    if request.user.tipo == 'EMPLEADO' and hasattr(request.user, 'sucursal'):
        base_queryset = base_queryset.filter(stocks__sucursal=request.user.sucursal)
    
    # Aplicar filtros y obtener queryset filtrado
    filtered_queryset = base_queryset

    # Aplicar búsqueda por nombre si existe
    if search_query:
        filtered_queryset = filtered_queryset.filter(nombre__icontains=search_query)

    # Aplicar filtro de tipo si existe
    if tipo_id:
        filtered_queryset = filtered_queryset.filter(tipo_id=tipo_id)
    
    # Para clientes, aplicar filtro de sucursal si existe
    sucursal_id = None
    if request.user.tipo == 'CLIENTE':
        sucursal_id = request.GET.get('sucursal')
        if sucursal_id:
            filtered_queryset = filtered_queryset.filter(stocks__sucursal_id=sucursal_id, stocks__stock_disponible__gt=0)
    
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
    base_tipos_query = TipoMaquinaria.objects.filter(
        maquinarias__stocks__stock_disponible__gt=0
    ).distinct()

    if search_query:
        base_tipos_query = base_tipos_query.filter(maquinarias__nombre__icontains=search_query)

    if sucursal_id:
        # Si hay filtro de sucursal, mostrar solo tipos disponibles en esa sucursal
        tipos_disponibles = base_tipos_query.filter(
            maquinarias__stocks__sucursal_id=sucursal_id
        ).distinct()
    else:
        # Si no hay filtro de sucursal, mostrar tipos que tienen stock en cualquier sucursal
        tipos_disponibles = base_tipos_query

    # Obtener sucursales disponibles según los filtros actuales (solo para clientes)
    sucursales_disponibles = None
    if request.user.tipo == 'CLIENTE':
        base_sucursales_query = Sucursal.objects.filter(
            activa=True,
            stocks__stock_disponible__gt=0
        )

        if search_query:
            base_sucursales_query = base_sucursales_query.filter(
                stocks__maquinaria__nombre__icontains=search_query
            )

        if tipo_id:
            # Si hay filtro de tipo, mostrar solo sucursales que tienen ese tipo
            sucursales_disponibles = base_sucursales_query.filter(
                stocks__maquinaria__tipo_id=tipo_id
            ).distinct()
        else:
            # Si no hay filtro de tipo, mostrar sucursales que tienen cualquier maquinaria con stock
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
        'sucursales': sucursales_disponibles.order_by('nombre') if sucursales_disponibles else None,
        'filtros': {
            'search': search_query,
            'tipo': tipo_id,
            'sucursal': sucursal_id,
            'precio_min': precio_min,
            'precio_max': precio_max
        },
        'is_cliente': request.user.tipo == 'CLIENTE',
        'is_empleado': request.user.tipo == 'EMPLEADO'
    }
    
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
        
        if form.is_valid() and stock_formset.is_valid():
            # Procesar datos del formset
            stocks_data = []
            for stock_form in stock_formset:
                if stock_form.cleaned_data and not stock_form.cleaned_data.get('DELETE', False):
                    stocks_data.append(stock_form.cleaned_data)
            
            # Validar que se haya asignado al menos una sucursal
            if not stocks_data:
                messages.error(request, 'Debe asignar la maquinaria a al menos una sucursal.')
            else:
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
        
        if form.is_valid() and stock_formset.is_valid():
            # Procesar datos del formset
            stocks_data = []
            for stock_form in stock_formset:
                if stock_form.cleaned_data:
                    stocks_data.append(stock_form.cleaned_data)
            
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
        maquinaria.delete()
        messages.success(request, 'Maquinaria eliminada exitosamente.')
    except Exception as e:
        messages.error(request, 'No se puede eliminar esta maquinaria porque está siendo utilizada.')
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
    
    return render(request, 'maquinarias/maquinaria_detail.html', context)


class MaquinariaListCliente(LoginRequiredMixin, ListView):
    model = Maquinaria
    template_name = 'maquinarias/maquinaria_list_cliente.html'
    context_object_name = 'maquinarias'
    paginate_by = 9

    def get_queryset(self):
        return Maquinaria.objects.filter(
            stocks__stock_disponible__gt=0
        ).distinct().order_by('nombre')