# reservas/urls.py
from django.urls import path
from . import views

urlpatterns = [
    # URLs para clientes
    path('crear/<int:maquinaria_id>/', views.crear_reserva_cliente, name='crear_reserva_cliente'),
    path('seleccionar-sucursal/', views.seleccionar_sucursal, name='seleccionar_sucursal'),
    path('confirmar/', views.confirmar_reserva, name='confirmar_reserva'),
    path('pago/<int:reserva_id>/', views.procesar_pago, name='procesar_pago'),
    path('mis-reservas/', views.mis_reservas, name='mis_reservas'),
    
    # URLs para empleados
    path('empleado/crear/<int:maquinaria_id>/', views.crear_reserva_empleado, name='crear_reserva_empleado'),
    path('empleado/confirmar-pago/<int:reserva_id>/', views.confirmar_pago_empleado, name='confirmar_pago_empleado'),
    path('empleado/listar/', views.listar_reservas_empleado, name='listar_reservas_empleado'),
    
    # URLs generales
    path('detalle/<int:reserva_id>/', views.detalle_reserva, name='detalle_reserva'),
    path('cancelar/<int:reserva_id>/', views.cancelar_reserva, name='cancelar_reserva'),
    path('editar/<int:reserva_id>/', views.editar_reserva, name='editar_reserva'),
    
    # URLs AJAX
    path('ajax/buscar-cliente/', views.buscar_cliente_ajax, name='buscar_cliente_ajax'),
    path('ajax/verificar-disponibilidad/', views.verificar_disponibilidad_ajax, name='verificar_disponibilidad_ajax'),
]