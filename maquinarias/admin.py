from django.contrib import admin
from .models import Maquinaria, TipoMaquinaria

# Registra los modelos
admin.site.register(Maquinaria)
admin.site.register(TipoMaquinaria)