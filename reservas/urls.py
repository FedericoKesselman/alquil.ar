# reservas/urls.py
from django.urls import path
from . import views

app_name = 'reservas'

urlpatterns = [
    # URLs para reservas (unificada para clientes y empleados)
    path('crear/<int:maquinaria_id>/', views.crear_reserva, name='crear_reserva'),
    path('confirmar-reservas/', views.confirmar_reservas, name='confirmar_reservas'),
    path('get-sucursales-disponibles/', views.get_sucursales_disponibles, name='get_sucursales_disponibles'),
    
    # URL para historial de reservas (unificada para todos los usuarios)
    path('historial/', views.lista_reservas, name='lista_reservas'),
    
    # URLs compartidas
    path('detalle/<int:reserva_id>/', views.detalle_reserva, name='detalle_reserva'),
    path('cancelar/<int:reserva_id>/', views.cancelar_reserva, name='cancelar_reserva'),
    
    # URLs para verificación AJAX
    path('verificar-disponibilidad/', views.verificar_disponibilidad_ajax, name='verificar_disponibilidad_ajax'),
]