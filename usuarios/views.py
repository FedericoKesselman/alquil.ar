# usuarios/views.py
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .forms import LoginForm
from usuarios.decorators import solo_admin

def login_view(request):
    if request.user.is_authenticated:
        return redirect('redireccionar_por_rol')

    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            user = form.cleaned_data['user']
            login(request, user)
            messages.success(request, f'Bienvenido {user.get_full_name()}!')
            return redirect('redireccionar_por_rol')
        else:
            for error in form.errors.values():
                messages.error(request, error)
    else:
        form = LoginForm()

    return render(request, 'usuarios/login.html', {'form': form})

@login_required
def logout_view(request):
    logout(request)
    messages.success(request, 'Has cerrado sesión correctamente.')
    return redirect('home')

@login_required
def redireccionar_por_rol(request):
    if request.user.tipo == 'ADMIN':
        return redirect('panel_admin')
    elif request.user.tipo == 'EMPLEADO':
        return redirect('panel_empleado')
    else:
        return redirect('panel_cliente')

@login_required
@solo_admin
def admin_panel_view(request):
    render(request, 'usuarios/admin_panel.html')