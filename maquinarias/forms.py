from django import forms
from django.core.validators import RegexValidator, MinValueValidator
from django.forms import formset_factory
from .models import Maquinaria, TipoMaquinaria, MaquinariaStock
from usuarios.models import Sucursal

class TipoMaquinariaForm(forms.ModelForm):
    class Meta:
        model = TipoMaquinaria
        fields = ['nombre', 'descripcion']
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nombre del tipo de maquinaria'}),
            'descripcion': forms.Textarea(attrs={
                'class': 'form-control',
                'placeholder': 'Descripción del tipo de maquinaria',
                'rows': 3
            })
        }

    def clean_nombre(self):
        nombre = self.cleaned_data.get('nombre')
        if TipoMaquinaria.objects.filter(nombre=nombre).exists():
            if not self.instance.pk or (self.instance.pk and self.instance.nombre != nombre):
                raise forms.ValidationError('Ya existe un tipo de maquinaria con este nombre.')
        return nombre

class MaquinariaStockForm(forms.Form):
    """Formulario para el stock por sucursal"""
    sucursal = forms.ModelChoiceField(
        queryset=Sucursal.objects.filter(activa=True),
        widget=forms.Select(attrs={'class': 'form-control'}),
        label="Sucursal"
    )
    stock = forms.IntegerField(
        min_value=0,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Stock'}),
        label="Stock"
    )

    def clean(self):
        cleaned_data = super().clean()
        sucursal = cleaned_data.get('sucursal')
        stock = cleaned_data.get('stock')

        if sucursal and stock < 0:
            raise forms.ValidationError("Stock invalido.")

        return cleaned_data

# Crear un formset para múltiples stocks por sucursal
MaquinariaStockFormSet = formset_factory(
    MaquinariaStockForm, 
    extra=1,  # Mostrar un formulario extra vacío
    can_delete=True  # Permitir eliminar formularios
)

class MaquinariaForm(forms.Form):
    # Campos básicos de la maquinaria
    nombre = forms.CharField(
        label="Nombre de la maquinaria",
        max_length=100,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nombre de la maquinaria'})
    )
    tipo = forms.ModelChoiceField(
        label="Tipo",
        queryset=TipoMaquinaria.objects.all(),
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    marca = forms.CharField(
        label="Marca",
        max_length=50,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Marca'})
    )
    modelo = forms.CharField(
        label="Modelo",
        max_length=50,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Modelo'})
    )
    anio = forms.IntegerField(
        label="Año",
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Año de fabricación'}),
        validators=[MinValueValidator(1900, 'El año debe ser mayor a 1900')]
    )
    descripcion = forms.CharField(
        label="Descripción",
        widget=forms.Textarea(attrs={
            'class': 'form-control', 
            'placeholder': 'Descripción detallada de la maquinaria',
            'rows': 4
        })
    )
    imagen = forms.ImageField(
        label="Imagen",
        required=True,
        widget=forms.ClearableFileInput(attrs={'class': 'form-control'})
    )
    precio_por_dia = forms.FloatField(
        label="Precio por día",
        widget=forms.NumberInput(attrs={
            'class': 'form-control', 
            'placeholder': 'Precio por día',
            'step': '0.01'
        }),
        validators=[MinValueValidator(0.01, 'El precio debe ser mayor a 0')]
    )
    minimo = forms.IntegerField(
        label="Cantidad Mínima de Días",
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Cantidad mínima'}),
        validators=[MinValueValidator(0, 'El valor mínimo debe ser mayor o igual a 0')]
    )
    maximo = forms.IntegerField(
        label="Cantidad Máxima de Días",
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Cantidad máxima'}),
        validators=[MinValueValidator(1, 'El valor máximo debe ser mayor a 0')]
    )
    cantDias_total = forms.IntegerField(
        label="Cantidad de Días para Devolución Total",
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Días totales'}),
        validators=[MinValueValidator(0, 'Los días totales deben ser mayor o igual a 0')]
    )
    cantDias_parcial = forms.IntegerField(
        label="Cantidad de Días para Devolución Parcial",
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Días parciales'}),
        validators=[MinValueValidator(0, 'Los días parciales deben ser mayor or igual a 0')]
    )
    cantDias_nulo = forms.IntegerField(
        label="Cantidad de Días para Devolución Nula",
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Días nulos'}),
        validators=[MinValueValidator(0, 'Los días nulos deben ser mayor o igual a 0')]
    )

    def clean_nombre(self):
        nombre = self.cleaned_data.get('nombre')
        instance_id = getattr(self, 'instance_id', None)
        
        query = Maquinaria.objects.filter(nombre=nombre)
        if instance_id:
            query = query.exclude(id=instance_id)
            
        if query.exists():
            raise forms.ValidationError('Ya existe una maquinaria con este nombre.')
        return nombre

    def clean(self):
        cleaned_data = super().clean()
        minimo = cleaned_data.get('minimo')
        maximo = cleaned_data.get('maximo')
        
        if minimo is not None and maximo is not None:
            if maximo <= minimo:
                raise forms.ValidationError('El valor máximo debe ser mayor que el mínimo.')
        
        cantDias_total = cleaned_data.get('cantDias_total', 0)
        cantDias_parcial = cleaned_data.get('cantDias_parcial', 0)
        cantDias_nulo = cleaned_data.get('cantDias_nulo', 0)

        if cantDias_parcial > cantDias_total:
            raise forms.ValidationError('La cantidad de días parciales no puede ser mayor a la cantidad total.')

        if cantDias_nulo > cantDias_parcial:
            raise forms.ValidationError('La cantidad de días nulos no puede ser mayor a la cantidad parcial.')
        
        suma_dias = cantDias_total + cantDias_parcial + cantDias_nulo
        if suma_dias > 365:
            raise forms.ValidationError('La suma total de días no puede exceder 365 días.')

        return cleaned_data

    def save(self, stocks_data=None):
        """Guarda la maquinaria y sus stocks por sucursal"""
        maquinaria = Maquinaria.objects.create(
            nombre=self.cleaned_data['nombre'],
            tipo=self.cleaned_data['tipo'],
            marca=self.cleaned_data['marca'],
            modelo=self.cleaned_data['modelo'],
            anio=self.cleaned_data['anio'],
            descripcion=self.cleaned_data['descripcion'],
            imagen=self.cleaned_data.get('imagen'),
            precio_por_dia=self.cleaned_data['precio_por_dia'],
            minimo=self.cleaned_data['minimo'],
            maximo=self.cleaned_data['maximo'],
            cantDias_total=self.cleaned_data['cantDias_total'],
            cantDias_parcial=self.cleaned_data['cantDias_parcial'],
            cantDias_nulo=self.cleaned_data['cantDias_nulo']
        )
        
        # Crear los stocks por sucursal
        if stocks_data:
            for stock_data in stocks_data:
                if stock_data.get('sucursal') and stock_data.get('stock') is not None:
                    MaquinariaStock.objects.create(
                        maquinaria=maquinaria,
                        sucursal=stock_data['sucursal'],
                        stock=stock_data['stock']
                    )
        
        return maquinaria

class MaquinariaUpdateForm(MaquinariaForm):
    def __init__(self, *args, **kwargs):
        instance = kwargs.pop('instance', None)
        super().__init__(*args, **kwargs)
        if instance:
            self.instance_id = instance.id
            # Pre-poblar el formulario con los datos de la instancia
            self.fields['nombre'].initial = instance.nombre
            self.fields['tipo'].initial = instance.tipo
            self.fields['marca'].initial = instance.marca
            self.fields['modelo'].initial = instance.modelo
            self.fields['anio'].initial = instance.anio
            self.fields['descripcion'].initial = instance.descripcion
            self.fields['precio_por_dia'].initial = instance.precio_por_dia
            self.fields['minimo'].initial = instance.minimo
            self.fields['maximo'].initial = instance.maximo
            self.fields['cantDias_total'].initial = instance.cantDias_total
            self.fields['cantDias_parcial'].initial = instance.cantDias_parcial
            self.fields['cantDias_nulo'].initial = instance.cantDias_nulo

    def save(self, stocks_data=None):
        instance_id = getattr(self, 'instance_id', None)
        if not instance_id:
            return super().save(stocks_data)
        
        maquinaria = Maquinaria.objects.get(id=instance_id)
        
        # Actualizar todos los campos
        maquinaria.nombre = self.cleaned_data['nombre']
        maquinaria.tipo = self.cleaned_data['tipo']
        maquinaria.marca = self.cleaned_data['marca']
        maquinaria.modelo = self.cleaned_data['modelo']
        maquinaria.anio = self.cleaned_data['anio']
        maquinaria.descripcion = self.cleaned_data['descripcion']
        if self.cleaned_data.get('imagen'):
            maquinaria.imagen = self.cleaned_data['imagen']
        maquinaria.precio_por_dia = self.cleaned_data['precio_por_dia']
        maquinaria.minimo = self.cleaned_data['minimo']
        maquinaria.maximo = self.cleaned_data['maximo']
        maquinaria.cantDias_total = self.cleaned_data['cantDias_total']
        maquinaria.cantDias_parcial = self.cleaned_data['cantDias_parcial']
        maquinaria.cantDias_nulo = self.cleaned_data['cantDias_nulo']
        
        maquinaria.save()
        
        # Actualizar stocks por sucursal
        if stocks_data is not None:
            # Eliminar stocks existentes que no están en los nuevos datos
            existing_stocks = {stock.sucursal.id: stock for stock in maquinaria.stocks.all()}
            new_sucursal_ids = {stock_data.get('sucursal').id for stock_data in stocks_data 
                              if stock_data.get('sucursal') and not stock_data.get('DELETE', False)}
            
            # Eliminar stocks que ya no están
            for sucursal_id, stock in existing_stocks.items():
                if sucursal_id not in new_sucursal_ids:
                    stock.delete()
            
            # Crear o actualizar stocks
            for stock_data in stocks_data:
                if stock_data.get('DELETE', False):
                    continue
                    
                sucursal = stock_data.get('sucursal')
                stock_cantidad = stock_data.get('stock')
                
                if sucursal and stock_cantidad is not None:
                    stock_obj, created = MaquinariaStock.objects.get_or_create(
                        maquinaria=maquinaria,
                        sucursal=sucursal,
                        defaults={'stock': stock_cantidad}
                    )
                    if not created:
                        # Calcular la diferencia para actualizar stock_disponible
                        diferencia = stock_cantidad - stock_obj.stock
                        stock_obj.stock = stock_cantidad
                        stock_obj.stock_disponible = max(0, stock_obj.stock_disponible + diferencia)
                        stock_obj.save()
        
        return maquinaria
