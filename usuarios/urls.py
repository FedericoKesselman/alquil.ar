from django.urls import path
from .views import login_view, logout_view, redireccionar_por_rol

urlpatterns = [
    path('login/', login_view, name='login'),
    path('logout/', logout_view, name='logout'),
    path('redirigir/', redireccionar_por_rol, name='redireccionar_por_rol'),
]
