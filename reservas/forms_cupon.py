from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from usuarios.models import Cupon
from decimal import Decimal


class AplicarCuponForm(forms.Form):
    """
    Formulario para aplicar un cupón de descuento a una reserva.
    """
    codigo_cupon = forms.CharField(
        max_length=20, 
        label="Código de Cupón",
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ingrese el código del cupón'})
    )
    
    def __init__(self, *args, **kwargs):
        self.cliente = kwargs.pop('cliente', None)
        self.precio_reserva = kwargs.pop('precio_reserva', 0)
        super().__init__(*args, **kwargs)
    
    def clean_codigo_cupon(self):
        codigo = self.cleaned_data.get('codigo_cupon')
        if not codigo:
            return None
        
        # Verificar si existe el cupón
        try:
            cupon = Cupon.objects.get(codigo=codigo)
        except Cupon.DoesNotExist:
            raise ValidationError("El cupón ingresado no existe.")
        
        # Verificar si el cupón pertenece al cliente
        if self.cliente and cupon.cliente.id != self.cliente.id:
            raise ValidationError("Este cupón no te pertenece.")
        
        # Verificar si el cupón está vigente
        today = timezone.now().date()
        if cupon.fecha_vencimiento < today:
            raise ValidationError("Este cupón ha vencido.")
        
        # Verificar si el cupón ya fue usado
        if cupon.usado:
            raise ValidationError("Este cupón ya ha sido utilizado.")
        
        # El cupón es válido
        return codigo
    
    def get_descuento(self):
        """Calcula el descuento a aplicar basado en el cupón"""
        codigo = self.cleaned_data.get('codigo_cupon')
        if not codigo:
            return 0
        
        cupon = Cupon.objects.get(codigo=codigo)
        
        if cupon.tipo == 'PORCENTAJE':
            # Descuento porcentual
            descuento = (Decimal(cupon.valor) / 100) * Decimal(self.precio_reserva)
        else:
            # Descuento de monto fijo
            descuento = min(Decimal(cupon.valor), Decimal(self.precio_reserva))
            
        return descuento
    
    def aplicar_cupon(self, reserva):
        """Aplica el cupón a la reserva y lo marca como usado"""
        codigo = self.cleaned_data.get('codigo_cupon')
        if not codigo:
            return False
        
        cupon = Cupon.objects.get(codigo=codigo)
        descuento = self.get_descuento()
        
        # Actualizar la reserva
        reserva.precio_antes_descuento = reserva.precio_total
        reserva.descuento_aplicado = descuento
        reserva.precio_total = reserva.precio_total - descuento
        reserva.save()
        
        # Actualizar el cupón
        cupon.usado = True
        cupon.reserva_uso = reserva
        cupon.save()
        
        return True
