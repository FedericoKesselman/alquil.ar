# usuarios/urls.py
from django.urls import path

from . import views

# Cuando se accede al path, se ejecuta la view indicada.
urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('redirigir/', views.redireccionar_por_rol, name='redireccionar_por_rol'),
    path('admin/panel/', views.admin_panel_view, name="panel_admin"),
    path('empleado/panel/', views.empleado_panel_view, name="panel_empleado"),
    path('cliente/panel/', views.cliente_panel_view, name="panel_cliente"),
    path('registrar-empleado/', views.crear_empleado_view, name="crear_empleado"),
    path('registrar-cliente/', views.crear_cliente_view, name="crear_cliente"),
    path('ver-empleados/', views.listar_empleados_view, name="listar_empleados"),
    path('ver-clientes/', views.listar_clientes_view, name="listar_clientes"),
    path('admin/sucursales/', views.admin_sucursales, name='admin_sucursales'),
    path('api/sucursales/', views.sucursales_json_publico, name='sucursales_json'),
    path('api/sucursales/todas/', views.todas_sucursales_json, name='todas_sucursales_json'),
    path('api/sucursales/crear/', views.crear_sucursal, name='crear_sucursal'),
    path('api/sucursales/editar/<int:id>/', views.editar_sucursal, name='editar_sucursal'),
    path('api/sucursales/estado/<int:id>/', views.cambiar_estado_sucursal, name='cambiar_estado_sucursal'),
    path('api/sucursales/actualizar_ubicacion/<int:id>/', views.actualizar_ubicacion_sucursal, name='actualizar_ubicacion'),
    path('api/sucursales/eliminar/<int:id>/', views.eliminar_sucursal, name='eliminar_sucursal'),
]