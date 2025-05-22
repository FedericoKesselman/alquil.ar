# usuarios/urls.py
from django.urls import path
from .views import login_view, logout_view, redireccionar_por_rol,admin_panel_view,crear_empleado_view,empleado_panel_view,cliente_panel_view,crear_cliente_view

# Cuando se accede al path, se ejecuta la view indicada.
urlpatterns = [
    path('login/', login_view, name='login'),
    path('logout/', logout_view, name='logout'),
    path('redirigir/', redireccionar_por_rol, name='redireccionar_por_rol'),
    path('admin/panel/', admin_panel_view, name="panel_admin"),
    path('empleado/panel/', empleado_panel_view, name="panel_empleado"),
    path('cliente/panel/', cliente_panel_view, name="panel_cliente"),
    path('registrar-empleado/', crear_empleado_view, name="crear_empleado"),
    path('registrar-cliente/', crear_cliente_view, name="crear_cliente"),
]
