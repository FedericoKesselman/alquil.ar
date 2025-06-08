# reservas/urls.py
from django.urls import path
from . import views

app_name = 'reservas'

urlpatterns = [
    # URLs para clientes
    path('crear/<int:maquinaria_id>/', views.crear_reserva_cliente, name='crear_reserva_cliente'),
    path('confirmar/<int:reserva_id>/', views.confirmar_reserva, name='confirmar_reserva'),
    path('get-sucursales-disponibles/', views.get_sucursales_disponibles, name='get_sucursales_disponibles'),
    
    # URLs para empleados
    path('empleado/crear/', views.crear_reserva_empleado, name='crear_reserva_empleado'),
    path('empleado/lista/', views.lista_reservas_empleado, name='lista_reservas_empleado'),
    
    # URLs compartidas
    path('lista/', views.lista_reservas, name='lista_reservas'),
    path('detalle/<int:reserva_id>/', views.detalle_reserva, name='detalle_reserva'),
    path('cancelar/<int:reserva_id>/', views.cancelar_reserva, name='cancelar_reserva'),
    
    # URLs para verificación AJAX
    path('verificar-disponibilidad/', views.verificar_disponibilidad_ajax, name='verificar_disponibilidad_ajax'),
]