# usuarios/views.py
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import Usuario
from .forms import LoginForm, EmpleadoForm, ClienteForm
from usuarios.decorators import solo_admin,solo_cliente,solo_empleado
from django.core.paginator import Paginator

def login_view(request):
    if request.user.is_authenticated: 
        return redirect('redireccionar_por_rol')

    if request.method == 'POST': #Si el usuario hace submit del fomrulario
        form = LoginForm(request.POST) # Sacamos los datos
        if form.is_valid():
            user = form.cleaned_data.get('user')  
            if user:  # Verificamos que el usuario exista
                login(request, user) # Lo logeamos
                return redirect('redireccionar_por_rol')
        # Si el formulario no es válido, muestra los errores
        for field, errors in form.errors.items():
            for error in errors:
                messages.error(request, f"{field}: {error}")
    
    else: # Se muestra fomrulario vacio (con la peticion GET)
        form = LoginForm()

    return render(request, 'usuarios/login.html', {'form': form})

@login_required
def logout_view(request):
    logout(request)
    messages.success(request, 'Has cerrado sesión correctamente.')
    return redirect('home')

@login_required
def redireccionar_por_rol(request):
    # Chequea el tipo de usuario, y lo redirecciona a sus paneles
    if request.user.tipo == 'ADMIN':
        return redirect('panel_admin')
    elif request.user.tipo == 'EMPLEADO':
        return redirect('panel_empleado')
    else:
        return redirect('panel_cliente')

@login_required
@solo_admin
def admin_panel_view(request):
    return render(request, 'usuarios/admin_panel.html')

@login_required
@solo_empleado
def empleado_panel_view(request):
    return render(request, 'usuarios/empleado_panel.html')

@login_required
@solo_cliente
def cliente_panel_view(request):
    return render(request, 'usuarios/cliente_panel.html')

@login_required
@solo_admin
def crear_empleado_view(request):
    if request.method == 'POST': # Cuando se aprieta el boton de submit
        form = EmpleadoForm(request.POST) # Extrae los datos llenados por el usuario
        if form.is_valid():
            try:
                empleado = form.save() # Ejecuta la funcion save del form definido en forms.py (Guarda empleado)
                messages.success(request, f'Empleado {empleado.nombre} registrado exitosamente!')
                return redirect('crear_empleado')  # ACA IRIA EL LISTADO DE EMPLEADOS
            except Exception as e:
                messages.error(request, f'Ocurrió un error al registrar el empleado: {str(e)}')
        else:
            # Mostrar todos los errores del formulario
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{form.fields[field].label}: {error}")
    else: 
        form = EmpleadoForm() # Se muestra el formulario

    context = {
        'form': form,
        'titulo': 'Registrar Nuevo Empleado'
    }
    return render(request, 'usuarios/form_generico.html', context)

@login_required
@solo_empleado
def crear_cliente_view(request):
    if request.method == 'POST': # Cuando se aprieta el boton de submit dle formulario
        form = ClienteForm(request.POST) # Extraemos los datos que puso el usuario
        if form.is_valid():
            try:
                cliente = form.save() # Lo guardamos en la base de datos
                messages.success(request, f'Cliente {cliente.nombre} registrado exitosamente!')
                return redirect('crear_cliente')  # PONER LISTADO DE CLIENTES
            except Exception as e:
                messages.error(request, f'Ocurrió un error al registrar el cliente: {str(e)}')
        else:
            # Mostrar todos los errores del formulario
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{form.fields[field].label}: {error}")
    else:
        form = ClienteForm() # Se muestra el formulario

    context = {
        'form': form,
        'titulo': 'Registrar Nuevo Cliente'
    }
    return render(request, 'usuarios/form_generico.html', context)

@login_required
@solo_admin
def listar_empleados_view(request):
    empleados = Usuario.objects.filter(tipo="EMPLEADO").order_by('nombre') #Extraigo los empleados de la base de datos

    paginator = Paginator(empleados, 10) # 10 item por pagina
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'empleados': page_obj,
        'total_empleados': empleados.count(),
        'titulo': 'Listado de Empleados'
    }

    return render(request, 'usuarios/listar_empleados.html', context) # Context tiene la info que voy a utilizar en el html

@login_required
@solo_empleado
def listar_clientes_view(request):
    clientes = Usuario.objects.filter(tipo="CLIENTE").order_by('nombre') #Extraigo los clientes de la base de datos

    paginator = Paginator(clientes, 10) # 10 item por pagina
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'clientes': page_obj,
        'total_clientes': clientes.count(),
        'titulo': 'Listado de Clientes'
    }

    return render(request, 'usuarios/listar_clientes.html', context) # Context tiene la info que voy a utilizar en el html