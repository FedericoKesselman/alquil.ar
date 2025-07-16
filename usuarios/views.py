# usuarios/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth import get_user_model
from .models import Usuario
from .forms import (
    LoginForm, 
    EmpleadoForm, 
    ClienteForm, 
    TokenVerificationForm,
    RecuperarPasswordForm,
    RestablecerPasswordForm,
    CambiarPasswordPerfilForm,
    EditarClienteForm
)
from usuarios.decorators import solo_admin, solo_cliente, solo_empleado
from django.core.paginator import Paginator
import json
from django.http import JsonResponse
from .models import Sucursal
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.db.models import Q
from django.utils import timezone
from datetime import timedelta
import django.db.models.deletion  # Añadimos esta importación para ProtectedError

User = get_user_model()  # Agregamos esta línea

def login_view(request):
    if request.user.is_authenticated:
        return redirect('redireccionar_por_rol')

    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            user = form.cleaned_data['user']
            
            # Si es admin, redirigir a verificación
            if user.tipo == 'ADMIN' and form.cleaned_data.get('needs_2fa'):
                request.session['admin_user_id'] = user.id
                return redirect('verificar_token')
                
            # Para otros usuarios, login directo
            login(request, user)
            return redirect('redireccionar_por_rol')
        else:
            messages.error(request, 'Credenciales incorrectas. Por favor, verifica tu email y contraseña.')
    else:
        form = LoginForm()

    return render(request, 'usuarios/login.html', {'form': form})

def verificar_token_view(request):
    user_id = request.session.get('admin_user_id')
    if not user_id:
        return redirect('login')
        
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return redirect('login')

    if request.method == 'POST':
        form = TokenVerificationForm(user, request.POST)
        if form.is_valid():
            # Limpiar token (Regla 2: se invalida al usarlo)
            user.token_2fa = None
            user.token_2fa_timestamp = None
            user.save()
            
            # Login exitoso
            login(request, user)
            del request.session['admin_user_id']
            return redirect('redireccionar_por_rol')
    else:
        form = TokenVerificationForm(user)

    return render(request, 'usuarios/verificar_token.html', {'form': form})

@login_required
def logout_view(request):
    logout(request)
    messages.success(request, 'Has cerrado sesión correctamente.')
    return redirect('home')

@login_required
def redireccionar_por_rol(request):
    if request.user.tipo == 'ADMIN':
        return redirect('panel_admin')  # Admin va a su panel
    else:
        return redirect('home')  

@login_required
@solo_admin
def admin_panel_view(request):
    """Vista del panel de administrador"""
    context = {}
    
    # Aquí solo incluimos el contexto necesario sin procesar estadísticas
    # La lógica de estadísticas está en usuarios/estadisticas/views.py
    
    return render(request, 'usuarios/admin_panel.html', context)

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
    if request.method == 'POST':
        form = EmpleadoForm(request.POST)
        if form.is_valid():
            try:
                user = form.save()
                messages.success(request, f"Empleado {user.nombre} registrado exitosamente.")
                return redirect('crear_empleado')
            except Exception as e:
                messages.error(request, f"Error al crear el empleado: {str(e)}")
        else:
            # Mostrar errores del formulario correctamente
            for field, errors in form.errors.items():
                for error in errors:
                    if field == '__all__':
                        messages.error(request, error)
                    else:
                        field_label = form.fields.get(field, {}).label or field.title()
                        messages.error(request, f"{field_label}: {error}")
    else:
        form = EmpleadoForm()
    
    # Usar el template genérico que ya existe
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
                return redirect('listar_clientes')  # PONER LISTADO DE CLIENTES
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

@solo_admin
def admin_sucursales(request):
    return render(request, 'usuarios/admin_sucursales.html')

def sucursales_json_publico(request):
    data = list(Sucursal.objects.filter(activa=True).values('id', 'nombre', 'direccion', 'telefono', 'latitud', 'longitud', 'activa'))
    return JsonResponse(data, safe=False)

def todas_sucursales_json(request):
    """API para obtener todas las sucursales (para el admin)"""
    data = list(Sucursal.objects.all().values('id', 'nombre', 'direccion', 'telefono', 'latitud', 'longitud', 'activa'))
    return JsonResponse(data, safe=False)

@csrf_exempt
@require_http_methods(["POST"])
@solo_admin
def crear_sucursal(request):
    try:
        data = json.loads(request.body)
        nombre = data.get('nombre', '').strip()
        direccion = data.get('direccion', '').strip()
        telefono = data.get('telefono', '').strip()
        latitud = data.get('latitud')
        longitud = data.get('longitud')
        
        # Validaciones
        if not nombre:
            return JsonResponse({'error': 'El nombre es obligatorio'}, status=400)
        
        if not direccion:
            return JsonResponse({'error': 'La dirección es obligatoria'}, status=400)
        
        if not telefono:
            return JsonResponse({'error': 'El teléfono es obligatorio'}, status=400)
        
        if latitud is None or longitud is None:
            return JsonResponse({'error': 'Coordenadas inválidas'}, status=400)
        
        # Verificar duplicados
        if Sucursal.objects.filter(nombre__iexact=nombre).exists():
            return JsonResponse({'error': 'Ya existe una sucursal con este nombre'}, status=400)
        
        if Sucursal.objects.filter(direccion__iexact=direccion).exists():
            return JsonResponse({'error': 'Ya existe una sucursal en esta dirección'}, status=400)
        
        if Sucursal.objects.filter(telefono=telefono).exists():
            return JsonResponse({'error': 'Ya existe una sucursal con este teléfono'}, status=400)
        
        sucursal = Sucursal.objects.create(
            nombre=nombre,
            direccion=direccion,
            telefono=telefono,
            latitud=latitud,
            longitud=longitud
        )
        
        return JsonResponse({
            'status': 'ok', 
            'id': sucursal.id,
            'mensaje': 'Sucursal creada exitosamente'
        })
    
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Datos JSON inválidos'}, status=400)
    except Exception as e:
        return JsonResponse({'error': f'Error interno: {str(e)}'}, status=500)

@csrf_exempt
@require_http_methods(["PUT"])
@solo_admin
def editar_sucursal(request, id):
    try:
        data = json.loads(request.body)
        sucursal = Sucursal.objects.get(id=id)
        
        nombre = data.get('nombre', '').strip()
        direccion = data.get('direccion', '').strip()
        telefono = data.get('telefono', '').strip()
        
        # Validaciones
        if not nombre:
            return JsonResponse({'error': 'El nombre es obligatorio'}, status=400)
        
        if not direccion:
            return JsonResponse({'error': 'La dirección es obligatoria'}, status=400)
        
        if not telefono:
            return JsonResponse({'error': 'El teléfono es obligatorio'}, status=400)
        
        # Verificar duplicados (excluyendo la sucursal actual)
        if Sucursal.objects.filter(nombre__iexact=nombre).exclude(id=id).exists():
            return JsonResponse({'error': 'Ya existe otra sucursal con este nombre'}, status=400)
        
        if Sucursal.objects.filter(direccion__iexact=direccion).exclude(id=id).exists():
            return JsonResponse({'error': 'Ya existe otra sucursal en esta dirección'}, status=400)
        
        if Sucursal.objects.filter(telefono=telefono).exclude(id=id).exists():
            return JsonResponse({'error': 'Ya existe otra sucursal con este teléfono'}, status=400)
        
        sucursal.nombre = nombre
        sucursal.direccion = direccion
        sucursal.telefono = telefono
        sucursal.save()
        
        return JsonResponse({
            'status': 'ok',
            'mensaje': 'Sucursal actualizada exitosamente'
        })
        
    except Sucursal.DoesNotExist:
        return JsonResponse({'error': 'Sucursal no encontrada'}, status=404)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Datos JSON inválidos'}, status=400)
    except Exception as e:
        return JsonResponse({'error': f'Error interno: {str(e)}'}, status=500)
    
@csrf_exempt
@require_http_methods(["PUT"])
@solo_admin
def cambiar_estado_sucursal(request, id):
    try:
        sucursal = Sucursal.objects.get(id=id)
        sucursal.activa = not sucursal.activa
        sucursal.save()
        return JsonResponse({
            'status': 'ok', 
            'activa': sucursal.activa,
            'mensaje': f'Sucursal {("activada" if sucursal.activa else "desactivada")} exitosamente'
        })
    except Sucursal.DoesNotExist:
        return JsonResponse({'error': 'Sucursal no encontrada'}, status=404)
    except Exception as e:
        return JsonResponse({'error': f'Error interno: {str(e)}'}, status=500)
    
@csrf_exempt
@require_http_methods(["PUT"])
@solo_admin
def actualizar_ubicacion_sucursal(request, id):
    try:
        sucursal = Sucursal.objects.get(id=id)
        data = json.loads(request.body)
        
        latitud = data.get('latitud')
        longitud = data.get('longitud')
        
        if latitud is None or longitud is None:
            return JsonResponse({'error': 'Coordenadas inválidas'}, status=400)
        
        sucursal.latitud = latitud
        sucursal.longitud = longitud
        sucursal.save()
        
        return JsonResponse({
            'status': 'ok',
            'mensaje': 'Ubicación actualizada exitosamente'
        })
        
    except Sucursal.DoesNotExist:
        return JsonResponse({'error': 'Sucursal no encontrada'}, status=404)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Datos JSON inválidos'}, status=400)
    except Exception as e:
        return JsonResponse({'error': f'Error interno: {str(e)}'}, status=500)

@csrf_exempt
@require_http_methods(["DELETE"])
@solo_admin
def eliminar_sucursal(request, id):
    try:
        sucursal = Sucursal.objects.get(id=id)
        nombre_sucursal = sucursal.nombre
        sucursal.delete()
        return JsonResponse({
            'status': 'ok',
            'mensaje': f'Sucursal "{nombre_sucursal}" eliminada exitosamente'
        })
    except Sucursal.DoesNotExist:
        return JsonResponse({'error': 'Sucursal no encontrada'}, status=404)
    except django.db.models.deletion.ProtectedError as e:
        # Capturar específicamente el error de protección y mostrar un mensaje amigable
        mensaje_error = str(e.args[0]) if e.args and len(e.args) > 0 else "No se puede eliminar la sucursal porque tiene elementos asociados"
        return JsonResponse({'error': mensaje_error}, status=400)
    except Exception as e:
        # Para otros errores, registrar el error completo pero mostrar un mensaje genérico
        print(f"Error al eliminar sucursal: {str(e)}")
        return JsonResponse({'error': 'No se pudo eliminar la sucursal. Verifique que no tenga maquinarias asociadas.'}, status=500)

def recuperar_password_view(request):
    if request.method == 'POST':
        form = RecuperarPasswordForm(request.POST)
        if form.is_valid():
            form.save()  # Este método ahora siempre retorna True
            # Mensaje genérico que no revela si el email existe
            messages.success(request, 'Si el correo electrónico pertenece a una cuenta registrada, recibirás un enlace de recuperación en tu bandeja de entrada.')
            return redirect('login')
    else:
        form = RecuperarPasswordForm()
    
    return render(request, 'usuarios/recuperar_password.html', {'form': form})

def enlace_expirado_view(request):
    """Vista para mostrar que el enlace de recuperación ha expirado"""
    return render(request, 'usuarios/enlace_expirado.html')

def restablecer_password_view(request, token):
    try:
        user = User.objects.get(reset_token=token, reset_token_used=False)

        # Verificar si el token expiró (15 minutos)
        tiempo_actual = timezone.now()
        if tiempo_actual > (user.reset_token_timestamp + timedelta(minutes=15)):
            return redirect('enlace_expirado')

    except User.DoesNotExist:
        return redirect('enlace_expirado')

    if request.method == 'POST':
        form = RestablecerPasswordForm(user, request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Tu contraseña fue restablecida con éxito.')
            return redirect('login')
        else:
            messages.error(request, 'Hubo errores en el formulario. Por favor, verifica los campos.')
    else:
        form = RestablecerPasswordForm(user)

    return render(request, 'usuarios/restablecer_password.html', {'form': form})

@login_required
def cambiar_password_perfil_view(request):
    if request.method == 'POST':
        form = CambiarPasswordPerfilForm(request.user, request.POST)
        if form.is_valid():
            form.save()  # Cambia la contraseña sin afectar la sesión
            messages.success(request, 'Tu contraseña fue actualizada con éxito.')
            return redirect('home')  # Redirige al home manteniendo la sesión activa
    else:
        form = CambiarPasswordPerfilForm(request.user)
    return render(request, 'usuarios/cambiar_password_perfil.html', {'form': form})

@login_required
@solo_empleado
def eliminar_cliente_view(request, cliente_id):
    """
    Vista para eliminar un cliente
    Solo se permite si todas sus reservas están finalizadas o si no tiene reservas
    """
    try:
        cliente = Usuario.objects.get(id=cliente_id, tipo="CLIENTE")
        
        # Verificar si tiene reservas que no están en estado FINALIZADA
        reservas_activas = cliente.reservas.exclude(estado='FINALIZADA').exists()
        
        if reservas_activas:
            messages.error(request, 'No se puede eliminar el cliente porque tiene reservas activas.')
            return redirect('listar_clientes')
        
        if request.method == 'POST':
            # La confirmación ya se recibió, proceder con la transferencia y eliminación
            nombre_cliente = cliente.nombre
            
            # Obtener o crear usuario placeholder para preservar datos históricos
            usuario_eliminado = get_or_create_deleted_user_placeholder()
            
            # Transferir todas las reservas y sus relaciones al usuario placeholder
            reservas = cliente.reservas.all()
            if reservas.exists():
                reservas.update(cliente=usuario_eliminado)
                
            # Verificar si hay reembolsos asociados y transferirlos
            from django.db.models import Q
            try:
                # Intenta importar el modelo Reembolso si existe
                from reservas.models import Reembolso
                # Transferir reembolsos si existen
                reembolsos = Reembolso.objects.filter(Q(reserva__cliente=cliente) | Q(cliente=cliente))
                if reembolsos.exists():
                    reembolsos.update(cliente=usuario_eliminado)
            except ImportError:
                # Si no existe el modelo, simplemente continuamos
                pass
                
            # Ahora eliminar el cliente (ya no tiene reservas asociadas)
            cliente.delete()
            messages.success(request, f'Cliente {nombre_cliente} eliminado correctamente.')
            return redirect('listar_clientes')
        
        # Obtener el número de reservas para el mensaje de confirmación
        num_reservas = cliente.reservas.count()
        
        return render(request, 'usuarios/confirmar_eliminar_cliente.html', {
            'cliente': cliente,
            'num_reservas': num_reservas
        })
        
    except Usuario.DoesNotExist:
        messages.error(request, 'Cliente no encontrado.')
        return redirect('listar_clientes')

@login_required
@solo_empleado
def editar_cliente_view(request, cliente_id):
    """
    Vista para editar un cliente
    Solo permite editar nombre, teléfono y fecha de nacimiento
    """
    cliente = get_object_or_404(Usuario, id=cliente_id, tipo="CLIENTE")
    
    if request.method == 'POST':
        form = EditarClienteForm(request.POST, instance=cliente)
        if form.is_valid():
            form.save()
            messages.success(request, f'Cliente {cliente.nombre} actualizado correctamente.')
            return redirect('listar_clientes')
        else:
            messages.error(request, 'Por favor, corrige los errores en el formulario.')
    else:
        form = EditarClienteForm(instance=cliente)
    
    context = {
        'form': form,
        'cliente': cliente,
        'titulo': 'Editar Cliente'
    }
    
    return render(request, 'usuarios/editar_cliente.html', context)

def get_or_create_deleted_user_placeholder():
    """
    Retorna un usuario placeholder para mantener asociadas las reservas y reembolsos
    de clientes eliminados, para fines estadísticos y de auditoría.
    """
    email = "cliente_eliminado@alquil.ar"
    try:
        # Intentar recuperar el usuario placeholder existente
        return Usuario.objects.get(email=email)
    except Usuario.DoesNotExist:
        # Crear el usuario placeholder si no existe
        import string
        import random
        from datetime import date
        
        # Generar una contraseña aleatoria segura que no se usará
        password = ''.join(random.choice(string.ascii_letters + string.digits + string.punctuation) for _ in range(32))
        
        # Crear el usuario placeholder
        deleted_user = Usuario.objects.create_user(
            username=email,
            email=email,
            password=password,
            nombre="Cliente Eliminado",
            dni="00000000",
            telefono="0000000000",
            fecha_nacimiento=date(2000, 1, 1),  # Fecha arbitraria
            tipo='CLIENTE'
        )
        return deleted_user

