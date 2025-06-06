#usuarios/decorators.py
from django.shortcuts import redirect
from django.contrib import messages

def solo_admin(view_func): #Verifica que el usuario logeado sea admin
    def wrapper(request, *args, **kwargs):
        if request.user.is_authenticated and request.user.tipo == 'ADMIN':
            return view_func(request, *args, **kwargs)
        messages.error(request, "No tenés permiso para acceder a esta sección.")
        return redirect('home')  # o redirigí a otra página
    return wrapper

def solo_empleado(view_func): #Verifica que el usuario logeado sea empleado
    def wrapper(request, *args, **kwargs):
        if request.user.is_authenticated and request.user.tipo == 'EMPLEADO':
            return view_func(request, *args, **kwargs)
        messages.error(request, "No tenés permiso para acceder a esta sección.")
        return redirect('home')
    return wrapper

def solo_cliente(view_func): #Verifica que el usuario logeado sea cliente
    def wrapper(request, *args, **kwargs):
        if request.user.is_authenticated and request.user.tipo == 'CLIENTE':
            return view_func(request, *args, **kwargs)
        messages.error(request, "No tenés permiso para acceder a esta sección.")
        return redirect('home')
    return wrapper
