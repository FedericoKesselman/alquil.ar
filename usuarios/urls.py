# usuarios/urls.py
from django.urls import path
from . import views
from .views import cambiar_password_perfil_view
from .estadisticas import views as estadisticas_views  # Asegúrate de que esta línea esté presente

# Cuando se accede al path, se ejecuta la view indicada.
urlpatterns = [
    # path('', views.home_view, name='home'),  # ESTA FALTA - referenciada en decorators.py
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('redirigir/', views.redireccionar_por_rol, name='redireccionar_por_rol'),
    path('admin/panel/', views.admin_panel_view, name='panel_admin'),
    path('admin/estadisticas/procesar/', estadisticas_views.procesar_estadisticas, name='procesar_estadisticas'),
    path('empleado/panel/', views.empleado_panel_view, name="panel_empleado"),
    path('cliente/panel/', views.cliente_panel_view, name="panel_cliente"),
    path('registrar-empleado/', views.crear_empleado_view, name="crear_empleado"),
    path('registrar-cliente/', views.crear_cliente_view, name="crear_cliente"),
    path('ver-empleados/', views.listar_empleados_view, name="listar_empleados"),
    path('ver-clientes/', views.listar_clientes_view, name="listar_clientes"),
    path('eliminar-cliente/<int:cliente_id>/', views.eliminar_cliente_view, name="eliminar_cliente"),
    path('editar-cliente/<int:cliente_id>/', views.editar_cliente_view, name="editar_cliente"),
    path('editar-empleado/<int:empleado_id>/', views.editar_empleado_view, name="editar_empleado"),
    path('eliminar-empleado/<int:empleado_id>/', views.eliminar_empleado_view, name="eliminar_empleado"),
    path('verificar-token/', views.verificar_token_view, name='verificar_token'),
    path('admin/sucursales/', views.admin_sucursales, name='admin_sucursales'),
    path('api/sucursales/', views.sucursales_json_publico, name='sucursales_json'),
    path('api/sucursales/todas/', views.todas_sucursales_json, name='todas_sucursales_json'),
    path('api/sucursales/crear/', views.crear_sucursal, name='crear_sucursal'),
    path('api/sucursales/editar/<int:id>/', views.editar_sucursal, name='editar_sucursal'),
    path('api/sucursales/estado/<int:id>/', views.cambiar_estado_sucursal, name='cambiar_estado_sucursal'),
    path('api/sucursales/actualizar_ubicacion/<int:id>/', views.actualizar_ubicacion_sucursal, name='actualizar_ubicacion'),
    path('api/sucursales/eliminar/<int:id>/', views.eliminar_sucursal, name='eliminar_sucursal'),
    
    # URLs para recuperar contraseña
    path('recuperar-password/', views.recuperar_password_view, name='recuperar_password'),
    path('restablecer-password/<str:token>/', views.restablecer_password_view, name='restablecer_password'),
    path('cambiar-password/', cambiar_password_perfil_view, name='cambiar_password_perfil'),
    path('enlace-expirado/', views.enlace_expirado_view, name='enlace_expirado'),
    
    # URLs para gestión de cupones
    path('admin/crear-cupon/<int:cliente_id>/', views.crear_cupon_view, name='crear_cupon'),
    path('admin/cupones/', views.listar_cupones_view, name='listar_cupones'),
    path('api/cupones/validar/<str:codigo>/', views.validar_cupon_view, name='validar_cupon'),
]
