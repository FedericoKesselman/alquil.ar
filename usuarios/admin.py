from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import Usuario, Sucursal
from .calificaciones import CalificacionCliente

# Registra los modelos
admin.site.register(Usuario)
admin.site.register(Sucursal)
admin.site.register(CalificacionCliente)