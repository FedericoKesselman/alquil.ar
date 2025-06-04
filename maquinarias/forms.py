from django import forms
from django.core.validators import RegexValidator, MinValueValidator
from .models import Maquinaria, TipoMaquinaria

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

class MaquinariaForm(forms.Form):
    # Declaro los campos del formulario
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
    stock_total = forms.IntegerField(
        label="Stock Total",
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Cantidad total disponible'}),
        validators=[MinValueValidator(0, 'El stock debe ser mayor o igual a 0')]
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
        validators=[MinValueValidator(0, 'Los días parciales deben ser mayor o igual a 0')]
    )
    cantDias_nulo = forms.IntegerField(
        label="Cantidad de Días para Devolución Nula",
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Días nulos'}),
        validators=[MinValueValidator(0, 'Los días nulos deben ser mayor o igual a 0')]
    )

    # Extraigo la info de los campos y la chequeo
    def clean_nombre(self):
        nombre = self.cleaned_data.get('nombre')
        instance_id = getattr(self, 'instance_id', None)
        
        # Verificar si existe una maquinaria con el mismo nombre
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
        stock_total = cleaned_data.get('stock_total')
        
        if minimo is not None and maximo is not None:
            if maximo <= minimo:
                raise forms.ValidationError('El valor máximo debe ser mayor que el mínimo.')
        
        cantDias_total = cleaned_data.get('cantDias_total', 0)
        cantDias_parcial = cleaned_data.get('cantDias_parcial', 0)
        cantDias_nulo = cleaned_data.get('cantDias_nulo', 0)

        if cantDias_parcial > cantDias_total:
            raise forms.ValidationError('La cantidad de días parciales no puede ser mayor a la cantidad total.')

        if cantDias_nulo > cantDias_parcial:
            raise forms.ValidationError('La cantidad de días nulos no puede ser mayor a la cantidad total.')
        
        suma_dias = cantDias_total + cantDias_parcial + cantDias_nulo
        if suma_dias > 365:
            raise forms.ValidationError('La suma total de días no puede exceder 365 días.')

        return cleaned_data

    def save(self): # Se guarda la maquinaria
        maquinaria = Maquinaria.objects.create(
            nombre=self.cleaned_data['nombre'],
            tipo=self.cleaned_data['tipo'],
            marca=self.cleaned_data['marca'],
            modelo=self.cleaned_data['modelo'],
            anio=self.cleaned_data['anio'],
            descripcion=self.cleaned_data['descripcion'],
            imagen=self.cleaned_data.get('imagen'),
            precio_por_dia=self.cleaned_data['precio_por_dia'],
            stock_total=self.cleaned_data['stock_total'],
            stock_disponible=self.cleaned_data['stock_total'],  # Inicialmente igual al stock total
            minimo=self.cleaned_data['minimo'],
            maximo=self.cleaned_data['maximo'],
            cantDias_total=self.cleaned_data['cantDias_total'],
            cantDias_parcial=self.cleaned_data['cantDias_parcial'],
            cantDias_nulo=self.cleaned_data['cantDias_nulo']
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
            self.fields['stock_total'].initial = instance.stock_total
            self.fields['minimo'].initial = instance.minimo
            self.fields['maximo'].initial = instance.maximo
            self.fields['cantDias_total'].initial = instance.cantDias_total
            self.fields['cantDias_parcial'].initial = instance.cantDias_parcial
            self.fields['cantDias_nulo'].initial = instance.cantDias_nulo

    def save(self):
        instance_id = getattr(self, 'instance_id', None)
        if not instance_id:
            return super().save()
        
        maquinaria = Maquinaria.objects.get(id=instance_id)
        old_stock_total = maquinaria.stock_total
        new_stock_total = self.cleaned_data['stock_total']
        
        # Actualizar el stock disponible proporcionalmente
        if old_stock_total != new_stock_total:
            stock_diff = new_stock_total - old_stock_total
            maquinaria.stock_disponible = max(0, maquinaria.stock_disponible + stock_diff)
        
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
        maquinaria.stock_total = new_stock_total
        maquinaria.minimo = self.cleaned_data['minimo']
        maquinaria.maximo = self.cleaned_data['maximo']
        maquinaria.cantDias_total = self.cleaned_data['cantDias_total']
        maquinaria.cantDias_parcial = self.cleaned_data['cantDias_parcial']
        maquinaria.cantDias_nulo = self.cleaned_data['cantDias_nulo']
        
        maquinaria.save()
        return maquinaria