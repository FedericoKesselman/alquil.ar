from django.contrib import admin
from .models import Reserva, Reembolso

# Register your models here.
@admin.register(Reserva)
class ReservaAdmin(admin.ModelAdmin):
    list_display = ('id', 'cliente', 'maquinaria', 'fecha_inicio', 'fecha_fin', 'estado', 'precio_total')
    list_filter = ('estado', 'fecha_inicio', 'fecha_fin')
    search_fields = ('cliente__nombre', 'cliente__email', 'maquinaria__nombre')
    date_hierarchy = 'fecha_creacion'

@admin.register(Reembolso)
class ReembolsoAdmin(admin.ModelAdmin):
    list_display = ('id', 'cliente', 'reserva', 'monto', 'dni_cliente', 'fecha_reembolso')
    list_filter = ('fecha_reembolso',)
    search_fields = ('cliente__nombre', 'cliente__email', 'dni_cliente', 'reserva__id')
    date_hierarchy = 'fecha_reembolso'
