from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import Usuario, Sucursal
from .calificaciones import CalificacionCliente


# Registra los modelos
admin.site.register(CalificacionCliente)
@admin.register(Sucursal)
class SucursalAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'direccion', 'telefono', 'activa')
    list_filter = ('activa',)
    search_fields = ('nombre', 'direccion')
    
    def has_delete_permission(self, request, obj=None):
        if not obj:
            return True
        
        # Check if the branch has active reservations
        from reservas.models import Reserva
        has_active_reservations = Reserva.objects.filter(
            sucursal_retiro=obj
        ).exclude(
            estado='FINALIZADA'
        ).exists()
        
        return not has_active_reservations
    
    def get_readonly_fields(self, request, obj=None):
        readonly_fields = list(self.readonly_fields)
        if obj:
            # Check if the branch has active reservations
            from reservas.models import Reserva
            has_active_reservations = Reserva.objects.filter(
                sucursal_retiro=obj
            ).exclude(
                estado='FINALIZADA'
            ).exists()
            
            if has_active_reservations:
                readonly_fields.extend(['nombre', 'direccion', 'activa'])
                # Add a message that this branch can't be deactivated
                from django.contrib import messages
                messages.warning(
                    request, 
                    "Esta sucursal tiene reservas en curso y no puede ser desactivada ni editada completamente."
                )
        
        return readonly_fields

class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'first_name', 'last_name', 'tipo', 'is_active')
    list_filter = ('tipo', 'is_active', 'is_staff')
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Información Personal', {'fields': ('first_name', 'last_name', 'email', 'dni')}),
        ('Permisos', {'fields': ('is_active', 'is_staff', 'is_superuser', 'tipo', 'sucursal')}),
        ('Fechas Importantes', {'fields': ('last_login', 'date_joined')}),
    )
    search_fields = ('username', 'first_name', 'last_name', 'email', 'dni')

admin.site.register(Usuario, CustomUserAdmin)