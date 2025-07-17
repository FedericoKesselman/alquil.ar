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
    
    # URLs para Maquinarias Favoritas
    path('favoritos/', views.maquinarias_favoritas, name='maquinarias_favoritas'),
    path('favoritos/agregar/<int:pk>/', views.agregar_favorito, name='agregar_favorito'),
    path('favoritos/eliminar/<int:pk>/', views.eliminar_favorito, name='eliminar_favorito'),
    path('admin/tipos/', views.tipo_maquinaria_list, name='tipo_maquinaria_list'),
    path('admin/tipos/crear/', views.tipo_maquinaria_create, name='tipo_maquinaria_create'),
    path('admin/tipos/<int:pk>/editar/', views.tipo_maquinaria_update, name='tipo_maquinaria_update'),
    path('admin/tipos/<int:pk>/eliminar/', views.tipo_maquinaria_delete, name='tipo_maquinaria_delete'),
]