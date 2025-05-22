# usuarios/views.py
from django.shortcuts import render, redirect
from django.contrib.auth.views import LoginView
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from .forms import LoginForm
from usuarios.decorators import solo_admin

class CustomLoginView(LoginView):
    def get_success_url(self):
        user = self.request.user
        if user.role == 'ADMIN':
            return 'panel_admin'  # Cambia por la URL real de tu dashboard
        elif user.role == 'EMPLEADO':
            return 'panel_empleado'    # Cambia por la URL real del empleado
        else:
            return 'panel_cliente'     # Cambia por la URL real del cliente
        

def is_admin(user):
    return user.role == 'admin'

@login_required
@user_passes_test(is_admin)
def dashboard_admin(request):
    ...

def login_view(request):
    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            # Procesar los datos
            pass
    else:
        form = LoginForm()
    return render(request, 'usuarios/login.html', {'form': form})