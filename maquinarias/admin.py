from django.contrib import admin
from .models import Maquinaria, TipoMaquinaria, MaquinariaStock

class MaquinariaStockInline(admin.TabularInline):
    model = MaquinariaStock
    extra = 0

@admin.register(Maquinaria)
class MaquinariaAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'tipo', 'marca', 'modelo', 'precio_por_dia', 'stock_total', 'stock_disponible')
    list_filter = ('tipo', 'marca')
    search_fields = ('nombre', 'marca', 'modelo', 'descripcion')
    inlines = [MaquinariaStockInline]
    
    def has_delete_permission(self, request, obj=None):
        if not obj:
            return True
        
        # Check if the machinery has active reservations
        from reservas.models import Reserva
        has_active_reservations = Reserva.objects.filter(
            maquinaria=obj
        ).exclude(
            estado='FINALIZADA'
        ).exists()
        
        return not has_active_reservations
    
    def get_readonly_fields(self, request, obj=None):
        readonly_fields = list(self.readonly_fields)
        if obj:
            # Check if the machinery has active reservations
            from reservas.models import Reserva
            has_active_reservations = Reserva.objects.filter(
                maquinaria=obj
            ).exclude(
                estado='FINALIZADA'
            ).exists()
            
            if has_active_reservations:
                readonly_fields.extend(['nombre', 'tipo', 'marca', 'modelo'])
                # Add a message that this machinery can't be fully edited
                from django.contrib import messages
                messages.warning(
                    request, 
                    "Esta maquinaria tiene reservas en curso y no puede ser editada completamente."
                )
        
        return readonly_fields

@admin.register(TipoMaquinaria)
class TipoMaquinariaAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'descripcion')
    search_fields = ('nombre', 'descripcion')

@admin.register(MaquinariaStock)
class MaquinariaStockAdmin(admin.ModelAdmin):
    list_display = ('maquinaria', 'sucursal', 'stock', 'stock_disponible', 'fecha_actualizacion')
    list_filter = ('sucursal',)
    search_fields = ('maquinaria__nombre', 'sucursal__nombre')