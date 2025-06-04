from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.views.generic import ListView
from django.contrib.auth.mixins import LoginRequiredMixin
from .models import Maquinaria, TipoMaquinaria
from .forms import MaquinariaForm, MaquinariaUpdateForm, TipoMaquinariaForm
from usuarios.decorators import solo_admin, solo_empleado

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
def maquinaria_list(request):
    if request.user.tipo not in ['ADMIN', 'EMPLEADO']:
        messages.error(request, 'No tienes permiso para acceder a esta página.')
        return redirect('home')
    
    maquinarias = Maquinaria.objects.all().order_by('nombre')
    paginator = Paginator(maquinarias, 10)
    page = request.GET.get('page')
    maquinarias = paginator.get_page(page)
    return render(request, 'maquinarias/maquinaria_list.html', {'maquinarias': maquinarias})

@login_required
def maquinaria_list_cliente(request):
    if request.user.tipo != 'CLIENTE':
        messages.error(request, 'No tienes permiso para acceder a esta página.')
        return redirect('home')
    
    maquinarias = Maquinaria.objects.filter(stock_disponible__gt=0).order_by('nombre')
    paginator = Paginator(maquinarias, 12)  # 12 items por página para la vista en cuadrícula
    page = request.GET.get('page')
    maquinarias = paginator.get_page(page)
    return render(request, 'maquinarias/maquinaria_list_cliente.html', {'maquinarias': maquinarias})

@login_required
def maquinaria_create(request):
    if request.user.tipo not in ['ADMIN', 'EMPLEADO']:
        messages.error(request, 'No tienes permiso para acceder a esta página.')
        return redirect('home')
    
    if request.method == 'POST':
        form = MaquinariaForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, 'Maquinaria creada exitosamente.')
            return redirect('maquinaria_list')
    else:
        form = MaquinariaForm()
    return render(request, 'maquinarias/maquinaria_form.html', {'form': form, 'action': 'Crear'})

@login_required
def maquinaria_update(request, pk):
    if request.user.tipo not in ['ADMIN', 'EMPLEADO']:
        messages.error(request, 'No tienes permiso para acceder a esta página.')
        return redirect('home')
    
    maquinaria = get_object_or_404(Maquinaria, pk=pk)
    if request.method == 'POST':
        form = MaquinariaUpdateForm(request.POST, request.FILES, instance=maquinaria)
        if form.is_valid():
            form.save()
            messages.success(request, 'Maquinaria actualizada exitosamente.')
            return redirect('maquinaria_list')
    else:
        form = MaquinariaUpdateForm(instance=maquinaria)
    return render(request, 'maquinarias/maquinaria_form.html', {'form': form, 'action': 'Editar'})

@login_required
def maquinaria_delete(request, pk):
    if request.user.tipo not in ['ADMIN', 'EMPLEADO']:
        messages.error(request, 'No tienes permiso para acceder a esta página.')
        return redirect('home')
    
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
    return render(request, 'maquinarias/maquinaria_detail.html', {'maquinaria': maquinaria})

class MaquinariaListCliente(LoginRequiredMixin, ListView):
    model = Maquinaria
    template_name = 'maquinarias/maquinaria_list_cliente.html'
    context_object_name = 'maquinarias'
    paginate_by = 9

    def get_queryset(self):
        return Maquinaria.objects.filter(stock_disponible__gt=0).order_by('nombre')