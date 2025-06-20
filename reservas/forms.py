# reservas/forms.py
from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from .models import Reserva
from maquinarias.models import MaquinariaStock
from usuarios.models import Sucursal, Usuario
from datetime import datetime, timedelta


class ReservaForm(forms.ModelForm):
    """Formulario base para crear reservas"""
    
    class Meta:
        model = Reserva
        fields = ['fecha_inicio', 'fecha_fin', 'cantidad_solicitada', 'sucursal_retiro', 'maquinaria', 'cliente']
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
            'sucursal_retiro': forms.Select(
                attrs={
                    'class': 'form-control',
                }
            ),
            'maquinaria': forms.HiddenInput(),
            'cliente': forms.HiddenInput()
        }
        labels = {
            'fecha_inicio': 'Fecha de Inicio',
            'fecha_fin': 'Fecha de Finalización',
            'cantidad_solicitada': 'Cantidad Solicitada',
            'sucursal_retiro': 'Sucursal de Retiro',
            'cliente': 'Seleccionar Cliente'
        }

    def __init__(self, *args, **kwargs):
        self._maquinaria = kwargs.pop('maquinaria', None)
        self._usuario = kwargs.pop('usuario', None)
        super().__init__(*args, **kwargs)

        if self._maquinaria:
            self.fields['maquinaria'].initial = self._maquinaria.id
            # Mostrar solo las sucursales activas que tienen la maquinaria asignada
            self.fields['sucursal_retiro'].queryset = Sucursal.objects.filter(
                stocks__maquinaria=self._maquinaria,
                activa=True
            ).distinct()
            # Agregar información de stock al label de cada sucursal
            choices = []
            for sucursal in self.fields['sucursal_retiro'].queryset:
                try:
                    stock = self._maquinaria.stocks.get(sucursal=sucursal)
                    choices.append(
                        (sucursal.id, f"{sucursal.nombre} - Stock: {stock.stock}")
                    )
                except MaquinariaStock.DoesNotExist:
                    continue
            self.fields['sucursal_retiro'].choices = choices

        if self._usuario:
            if self._usuario.tipo == 'EMPLEADO':
                # Para empleados, mostrar selector de clientes
                self.fields['cliente'] = forms.ModelChoiceField(
                    queryset=Usuario.objects.filter(tipo='CLIENTE'),
                    widget=forms.Select(attrs={'class': 'form-control'}),
                    label='Cliente'
                )
            else:
                # Para clientes, establecer el cliente automáticamente
                self.fields['cliente'].initial = self._usuario.id

    def clean_cantidad_solicitada(self):
        cantidad = self.cleaned_data.get('cantidad_solicitada')
        if cantidad is not None and cantidad <= 0:
            raise forms.ValidationError("La cantidad debe ser mayor a 0")
        return cantidad

    def clean(self):
        cleaned_data = super().clean()
        fecha_inicio = cleaned_data.get('fecha_inicio')
        fecha_fin = cleaned_data.get('fecha_fin')
        
        if fecha_inicio and fecha_fin:
            # Validar que la fecha de inicio no sea anterior a hoy
            if fecha_inicio < timezone.now().date():
                raise forms.ValidationError("La fecha de inicio no puede ser anterior a hoy")
            
            # Validar que la fecha de fin no sea anterior a la fecha de inicio
            if fecha_fin < fecha_inicio:
                raise forms.ValidationError("La fecha de finalización debe ser posterior a la fecha de inicio")
            
            # Calcular la cantidad de días
            dias = (fecha_fin - fecha_inicio).days + 1
            
            # Validar contra los límites de la maquinaria
            if self._maquinaria:
                if dias < self._maquinaria.minimo:
                    raise forms.ValidationError(
                        f"El período mínimo de reserva es de {self._maquinaria.minimo} días"
                    )
                if dias > self._maquinaria.maximo:
                    raise forms.ValidationError(
                        f"El período máximo de reserva es de {self._maquinaria.maximo} días"
                    )
        
        return cleaned_data

    def calcular_precio_total(self):
        """Calcula el precio total de la reserva"""
        if not self.is_valid() or not self._maquinaria:
            return 0
        
        fecha_inicio = self.cleaned_data['fecha_inicio']
        fecha_fin = self.cleaned_data['fecha_fin']
        cantidad = self.cleaned_data['cantidad_solicitada']
        
        dias = (fecha_fin - fecha_inicio).days
        return self._maquinaria.precio_por_dia * dias * cantidad


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


class ReservaEmpleadoForm(forms.ModelForm):
    """Formulario para que empleados creen reservas"""
    cliente = forms.ModelChoiceField(
        queryset=Usuario.objects.filter(tipo='CLIENTE'),
        label='Cliente',
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    class Meta:
        model = Reserva
        fields = ['cliente', 'maquinaria', 'fecha_inicio', 'fecha_fin', 
                 'cantidad_solicitada', 'sucursal_retiro']
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
                    'min': '1'
                }
            ),
            'maquinaria': forms.Select(
                attrs={
                    'class': 'form-control'
                }
            ),
            'sucursal_retiro': forms.Select(
                attrs={
                    'class': 'form-control'
                }
            )
        }
        
    def clean(self):
        cleaned_data = super().clean()
        fecha_inicio = cleaned_data.get('fecha_inicio')
        fecha_fin = cleaned_data.get('fecha_fin')
        maquinaria = cleaned_data.get('maquinaria')
        cantidad = cleaned_data.get('cantidad_solicitada')
        sucursal = cleaned_data.get('sucursal_retiro')
        
        if all([fecha_inicio, fecha_fin, maquinaria, cantidad, sucursal]):
            # Verificar disponibilidad
            stock_disponible = sucursal.get_stock_disponible(
                maquinaria,
                fecha_inicio,
                fecha_fin,
                cantidad
            )
            
            if stock_disponible < cantidad:
                raise forms.ValidationError(
                    f'No hay suficiente stock disponible en la sucursal seleccionada. '
                    f'Stock disponible: {stock_disponible}'
                )
        
        return cleaned_data


class ReservaPorCodigoForm(forms.Form):
    """Formulario para procesar una reserva mediante su código"""
    codigo_reserva = forms.CharField(
        max_length=6,
        min_length=6,
        label='Código de Reserva',
        widget=forms.TextInput(
            attrs={
                'class': 'form-control',
                'placeholder': 'Ingrese el código de 6 dígitos',
                'pattern': '[0-9]{6}',
                'title': 'El código debe contener 6 dígitos',
                'inputmode': 'numeric'
            }
        )
    )

    def clean_codigo_reserva(self):
        codigo = self.cleaned_data['codigo_reserva']
        # Verificar que sean solo dígitos
        if not codigo.isdigit() or len(codigo) != 6:
            raise ValidationError("El código debe contener exactamente 6 dígitos.")
        return codigo