from django.urls import path
from . import views

urlpatterns = [
    # URLs para Tipos de Maquinaria
    path('tipos/', views.tipo_maquinaria_list, name='tipo_maquinaria_list'),
    path('tipos/crear/', views.tipo_maquinaria_create, name='tipo_maquinaria_create'),
    path('tipos/<int:pk>/editar/', views.tipo_maquinaria_update, name='tipo_maquinaria_update'),
    path('tipos/<int:pk>/eliminar/', views.tipo_maquinaria_delete, name='tipo_maquinaria_delete'),
    
    # URLs para Maquinarias
    path('', views.maquinaria_list, name='maquinaria_list'),
    path('catalogo/', views.maquinaria_list_cliente, name='maquinaria_list_cliente'),
    path('crear/', views.maquinaria_create, name='maquinaria_create'),
    path('editar/<int:pk>/', views.maquinaria_update, name='maquinaria_update'),
    path('eliminar/<int:pk>/', views.maquinaria_delete, name='maquinaria_delete'),
    path('detalle/<int:pk>/', views.maquinaria_detail, name='maquinaria_detail'),
    path('admin/tipos/', views.tipo_maquinaria_list, name='tipo_maquinaria_list'),
    path('admin/tipos/crear/', views.tipo_maquinaria_create, name='tipo_maquinaria_create'),
    path('admin/tipos/<int:pk>/editar/', views.tipo_maquinaria_update, name='tipo_maquinaria_update'),
    path('admin/tipos/<int:pk>/eliminar/', views.tipo_maquinaria_delete, name='tipo_maquinaria_delete'),
]