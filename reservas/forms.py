# reservas/forms.py
from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from .models import Reserva
from usuarios.models import Sucursal
from datetime import datetime, timedelta


class ReservaForm(forms.ModelForm):
    """Formulario base para crear reservas"""
    
    class Meta:
        model = Reserva
        fields = ['fecha_inicio', 'fecha_fin', 'cantidad_solicitada']
        widgets = {
            'fecha_inicio': forms.DateInput(
                attrs={
                    'type': 'date',
                    'class': 'form-control',
                    'min': timezone.now().date().strftime('%Y-%m-%d')
                }
            ),
            'fecha_fin': forms.DateInput(
                attrs={
                    'type': 'date',
                    'class': 'form-control',
                    'min': timezone.now().date().strftime('%Y-%m-%d')
                }
            ),
            'cantidad_solicitada': forms.NumberInput(
                attrs={
                    'class': 'form-control',
                    'min': '1',
                    'placeholder': 'Cantidad de máquinas'
                }
            ),
        }
        labels = {
            'fecha_inicio': 'Fecha de Inicio',
            'fecha_fin': 'Fecha de Finalización',
            'cantidad_solicitada': 'Cantidad Solicitada',
        }

    def __init__(self, *args, **kwargs):
        self.maquinaria = kwargs.pop('maquinaria', None)
        self.usuario = kwargs.pop('usuario', None)
        super().__init__(*args, **kwargs)
        
        # Configurar validaciones dinámicas basadas en la maquinaria
        if self.maquinaria:
            # Actualizar el widget de cantidad con el máximo stock disponible
            max_stock = self.maquinaria.get_stock_disponible_total()
            self.fields['cantidad_solicitada'].widget.attrs.update({
                'max': str(max_stock),
                'title': f'Máximo disponible: {max_stock}'
            })
            
            # Agregar información de días mínimos y máximos en los labels
            self.fields['fecha_inicio'].help_text = f'Mínimo {self.maquinaria.minimo} días, máximo {self.maquinaria.maximo} días'
            self.fields['fecha_fin'].help_text = f'La reserva debe ser entre {self.maquinaria.minimo} y {self.maquinaria.maximo} días'

    def clean(self):
        cleaned_data = super().clean()
        fecha_inicio = cleaned_data.get('fecha_inicio')
        fecha_fin = cleaned_data.get('fecha_fin')
        cantidad_solicitada = cleaned_data.get('cantidad_solicitada')

        if not all([fecha_inicio, fecha_fin, cantidad_solicitada, self.maquinaria]):
            return cleaned_data

        # Validar fechas
        if fecha_inicio >= fecha_fin:
            raise ValidationError('La fecha de fin debe ser posterior a la fecha de inicio.')

        if fecha_inicio < timezone.now().date():
            raise ValidationError('La fecha de inicio no puede ser anterior a hoy.')

        # Validar días mínimos y máximos
        dias_reserva = (fecha_fin - fecha_inicio).days
        if dias_reserva < self.maquinaria.minimo:
            raise ValidationError(f'La reserva debe ser de mínimo {self.maquinaria.minimo} días.')

        if dias_reserva > self.maquinaria.maximo:
            raise ValidationError(f'La reserva no puede exceder {self.maquinaria.maximo} días.')

        # Validar disponibilidad
        disponibilidad = Reserva.verificar_disponibilidad(
            maquinaria=self.maquinaria,
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
            cantidad_solicitada=cantidad_solicitada
        )

        if not disponibilidad['disponible']:
            raise ValidationError(f'No hay disponibilidad para las fechas seleccionadas. {disponibilidad["mensaje"]}')

        # Guardar información de disponibilidad para usar en la vista
        self.sucursales_disponibles = disponibilidad['sucursales_disponibles']

        return cleaned_data

    def calcular_precio_total(self):
        """Calcula el precio total de la reserva"""
        if not self.is_valid() or not self.maquinaria:
            return 0
        
        fecha_inicio = self.cleaned_data['fecha_inicio']
        fecha_fin = self.cleaned_data['fecha_fin']
        cantidad = self.cleaned_data['cantidad_solicitada']
        
        dias = (fecha_fin - fecha_inicio).days
        return self.maquinaria.precio_por_dia * dias * cantidad


class SeleccionSucursalForm(forms.Form):
    """Formulario para seleccionar la sucursal de retiro"""
    
    sucursal_retiro = forms.ModelChoiceField(
        queryset=Sucursal.objects.none(),
        widget=forms.RadioSelect,
        label='Seleccione la sucursal donde retirar la maquinaria',
        empty_label=None
    )

    def __init__(self, *args, **kwargs):
        sucursales_disponibles = kwargs.pop('sucursales_disponibles', [])
        super().__init__(*args, **kwargs)
        
        # Crear opciones con información de stock
        choices = []
        for info_sucursal in sucursales_disponibles:
            sucursal = info_sucursal['sucursal']
            stock_disponible = info_sucursal['stock_disponible']
            label = f"{sucursal.nombre} - {sucursal.direccion} (Disponible: {stock_disponible})"
            choices.append((sucursal.id, label))
        
        self.fields['sucursal_retiro'].queryset = Sucursal.objects.filter(
            id__in=[info['sucursal'].id for info in sucursales_disponibles]
        )
        
        # Personalizar las etiquetas
        self.fields['sucursal_retiro'].widget.choices = choices


class ConfirmacionPagoForm(forms.Form):
    """Formulario para que empleados confirmen pagos presenciales"""
    
    observaciones = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Observaciones sobre el pago (opcional)'
        }),
        required=False,
        label='Observaciones'
    )
    
    confirmar_pago = forms.BooleanField(
        required=True,
        label='Confirmo que el cliente ha realizado el pago',
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )


class BusquedaReservasForm(forms.Form):
    """Formulario para buscar y filtrar reservas"""
    
    ESTADO_CHOICES = [('', 'Todos los estados')] + Reserva.ESTADO_CHOICES
    
    cliente = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Nombre o DNI del cliente'
        }),
        label='Cliente'
    )
    
    estado = forms.ChoiceField(
        choices=ESTADO_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'}),
        label='Estado'
    )
    
    fecha_desde = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'form-control'
        }),
        label='Desde'
    )
    
    fecha_hasta = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'form-control'
        }),
        label='Hasta'
    )
    
    maquinaria = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Nombre de la maquinaria'
        }),
        label='Maquinaria'
    )


class EditarReservaForm(forms.ModelForm):
    """Formulario para editar reservas (solo para admins y empleados)"""
    
    class Meta:
        model = Reserva
        fields = ['fecha_inicio', 'fecha_fin', 'cantidad_solicitada', 'estado', 'observaciones']
        widgets = {
            'fecha_inicio': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'fecha_fin': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'cantidad_solicitada': forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
            'estado': forms.Select(attrs={'class': 'form-control'}),
            'observaciones': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
        }

    def __init__(self, *args, **kwargs):
        self.usuario = kwargs.pop('usuario', None)
        super().__init__(*args, **kwargs)
        
        # Los clientes no pueden editar el estado
        if self.usuario and self.usuario.tipo == 'CLIENTE':
            self.fields['estado'].widget.attrs['disabled'] = True
            self.fields['observaciones'].widget.attrs['readonly'] = True

    def clean(self):
        cleaned_data = super().clean()
        
        # Realizar las mismas validaciones que el formulario de creación
        if self.instance.pk:  # Solo si estamos editando
            fecha_inicio = cleaned_data.get('fecha_inicio')
            fecha_fin = cleaned_data.get('fecha_fin')
            cantidad_solicitada = cleaned_data.get('cantidad_solicitada')
            
            if all([fecha_inicio, fecha_fin, cantidad_solicitada]):
                # Validar disponibilidad excluyendo la reserva actual
                disponibilidad = Reserva.verificar_disponibilidad(
                    maquinaria=self.instance.maquinaria,
                    fecha_inicio=fecha_inicio,
                    fecha_fin=fecha_fin,
                    cantidad_solicitada=cantidad_solicitada,
                    sucursal=self.instance.sucursal_retiro,
                    excluir_reserva=self.instance.id
                )
                
                if not disponibilidad['disponible']:
                    raise ValidationError('No hay disponibilidad para las nuevas fechas seleccionadas.')
        
        return cleaned_data