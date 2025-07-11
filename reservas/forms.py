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
        error_messages = {
            'fecha_inicio': {
                'required': 'Por favor seleccione una fecha de inicio',
                'invalid': 'La fecha de inicio no es válida'
            },
            'fecha_fin': {
                'required': 'Por favor seleccione una fecha de finalización',
                'invalid': 'La fecha de finalización no es válida'
            },
            'cantidad_solicitada': {
                'required': 'Por favor indique la cantidad de máquinas',
                'invalid': 'La cantidad ingresada no es válida',
                'min_value': 'La cantidad debe ser al menos 1'
            },
            'sucursal_retiro': {
                'required': 'Por favor seleccione una sucursal de retiro',
                'invalid_choice': 'La sucursal seleccionada no es válida'
            }
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
                # Para empleados, mostrar campo de DNI del cliente
                self.fields['dni_cliente'] = forms.CharField(
                    max_length=8,
                    min_length=1,
                    label='DNI del Cliente',
                    widget=forms.TextInput(attrs={
                        'class': 'form-control',
                        'placeholder': 'Ingrese el DNI del cliente (1-8 dígitos)',
                        'pattern': '[0-9]{1,8}',
                        'title': 'El DNI debe contener entre 1 y 8 dígitos',
                        'inputmode': 'numeric'
                    })
                )
                # Eliminar el campo de cliente del formulario (se buscará por DNI)
                if 'cliente' in self.fields:
                    del self.fields['cliente']
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
        
        # Si el usuario es un empleado y ha introducido un DNI de cliente, buscar el cliente
        if self._usuario and self._usuario.tipo == 'EMPLEADO':
            dni_cliente = cleaned_data.get('dni_cliente')
            if not dni_cliente:
                raise forms.ValidationError("Debe ingresar el DNI del cliente")
                
            try:
                cliente = Usuario.objects.get(dni=dni_cliente, tipo='CLIENTE')
                # Añadir el cliente encontrado a los datos limpiados
                cleaned_data['cliente'] = cliente
                
                # Verificar que el cliente no tenga reservas activas o canceladas
                reserva_existente = Reserva.objects.filter(
                    cliente=cliente,
                    estado__in=['CONFIRMADA', 'CANCELADA']
                ).exists()
                
                if reserva_existente:
                    raise forms.ValidationError(
                        f"El cliente con DNI {dni_cliente} ya tiene una reserva activa o cancelada. No puede crear una nueva reserva."
                    )
            except Usuario.DoesNotExist:
                raise forms.ValidationError(f"DNI ingresado no registrado en el sistema")
        
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
        
        dias = (fecha_fin - fecha_inicio).days + 1  # +1 para incluir el día de inicio
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
        es_empleado = kwargs.pop('es_empleado', False)
        super().__init__(*args, **kwargs)
        
        # Crear opciones con información de stock solo para empleados
        choices = []
        for info_sucursal in sucursales_disponibles:
            sucursal = info_sucursal['sucursal']
            stock_disponible = info_sucursal['stock_disponible']
            
            # Solo mostrar stock disponible si es empleado o admin
            if es_empleado:
                label = f"{sucursal.nombre} - {sucursal.direccion} (Disponible: {stock_disponible})"
            else:
                label = f"{sucursal.nombre} - {sucursal.direccion}"
                
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
    dni_cliente = forms.CharField(
        max_length=8,
        min_length=1,
        label='DNI del Cliente',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Ingrese el DNI del cliente (1-8 dígitos)',
            'pattern': '[0-9]{1,8}',
            'title': 'El DNI debe contener entre 1 y 8 dígitos',
            'inputmode': 'numeric'
        })
    )
    
    class Meta:
        model = Reserva
        fields = ['maquinaria', 'fecha_inicio', 'fecha_fin', 
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
        dni_cliente = cleaned_data.get('dni_cliente')
        
        # Verificar que exista un cliente con ese DNI
        try:
            cliente = Usuario.objects.get(dni=dni_cliente, tipo='CLIENTE')
            # Guardar el cliente encontrado en los datos limpiados
            cleaned_data['cliente'] = cliente
            
            # Verificar que el cliente no tenga reservas activas o canceladas
            reserva_existente = Reserva.objects.filter(
                cliente=cliente,
                estado__in=['CONFIRMADA', 'CANCELADA']
            ).exists()
            
            if reserva_existente:
                raise forms.ValidationError(
                    "El cliente seleccionado ya tiene una reserva activa o cancelada. No puede crear una nueva reserva."
                )
                
        except Usuario.DoesNotExist:
            raise forms.ValidationError("DNI ingresado no registrado en el sistema")
        
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
    
    dni_cliente = forms.CharField(
        max_length=8,
        min_length=1,
        label='DNI del Cliente',
        widget=forms.TextInput(
            attrs={
                'class': 'form-control',
                'placeholder': 'Ingrese el DNI del cliente (1-8 dígitos)',
                'pattern': '[0-9]{1,8}',
                'title': 'El DNI debe contener entre 1 y 8 dígitos',
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
        
    def clean_dni_cliente(self):
        dni = self.cleaned_data['dni_cliente']
        # Verificar que sean solo dígitos
        if not dni.isdigit() or not (1 <= len(dni) <= 8):
            raise ValidationError("El DNI debe contener entre 1 y 8 dígitos.")
        return dni
        
    def clean(self):
        cleaned_data = super().clean()
        codigo = cleaned_data.get('codigo_reserva')
        dni = cleaned_data.get('dni_cliente')
        
        if codigo and dni:
            # Verificar que el código de reserva y el DNI coincidan con una reserva existente
            try:
                reserva = Reserva.objects.get(codigo_reserva=codigo)
                if reserva.cliente.dni != dni:
                    raise forms.ValidationError(
                        "El DNI ingresado no coincide con el cliente de la reserva."
                    )
            except Reserva.DoesNotExist:
                # Este error se manejará en la vista
                pass
                
        return cleaned_data


class DevolucionForm(forms.Form):
    """Formulario para procesar la devolución de una maquinaria"""
    
    RATING_CHOICES = [
        (0.5, '0.5 estrella'),
        (1.0, '1 estrella'),
        (1.5, '1.5 estrellas'),
        (2.0, '2 estrellas'),
        (2.5, '2.5 estrellas'),
        (3.0, '3 estrellas'),
        (3.5, '3.5 estrellas'),
        (4.0, '4 estrellas'),
        (4.5, '4.5 estrellas'),
        (5.0, '5 estrellas'),
    ]
    
    calificacion_cliente = forms.FloatField(
        required=True,
        label='Calificación del cliente',
        widget=forms.HiddenInput(
            attrs={
                'id': 'calificacion-cliente-input'
            }
        ),
        initial=5.0,
        min_value=0.5,
        max_value=5.0
    )
    
    observaciones = forms.CharField(
        widget=forms.Textarea(
            attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Observaciones sobre el estado de la maquinaria (opcional)'
            }
        ),
        required=False,
        label='Observaciones'
    )