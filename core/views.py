from django.shortcuts import render
from django.shortcuts import render, redirect
# Create your views here.
def home(request):
    # Si el usuario está autenticado y es admin, redirigir a su panel
    if request.user.is_authenticated and request.user.tipo == 'ADMIN':
        return redirect('panel_admin')
    
    # Para usuarios no autenticados, empleados y clientes, mostrar el home normal
    return render(request, 'core/home.html')
