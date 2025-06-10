#maquinarias/models.py
from django.db import models
from usuarios.models import Sucursal

class TipoMaquinaria(models.Model):
    nombre = models.CharField(max_length=50, unique=True)
    descripcion = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.nombre

    class Meta:
        verbose_name = "Tipo de Maquinaria"
        verbose_name_plural = "Tipos de Maquinaria"

class Maquinaria(models.Model):
    nombre = models.CharField(max_length=100)
    tipo = models.ForeignKey(TipoMaquinaria, on_delete=models.PROTECT, related_name='maquinarias')
    marca = models.CharField(max_length=50)
    modelo = models.CharField(max_length=50)
    anio = models.SmallIntegerField()
    descripcion = models.TextField()
    imagen = models.ImageField(upload_to='maquinarias/images', null=True, blank=True)
    precio_por_dia = models.FloatField()
    # Mantenemos estos campos para compatibilidad, pero serán calculados
    stock_total = models.PositiveIntegerField(default=0)
    stock_disponible = models.PositiveIntegerField(default=0)
    minimo = models.SmallIntegerField()
    maximo = models.SmallIntegerField()
    cantDias_total = models.SmallIntegerField()
    cantDias_parcial = models.SmallIntegerField()
    cantDias_nulo = models.SmallIntegerField()
    
    # Relación many-to-many con Sucursal a través de MaquinariaStock
    sucursales = models.ManyToManyField(Sucursal, through='MaquinariaStock', related_name='maquinarias')

    def __str__(self):
        return f"{self.nombre} - {self.marca} {self.modelo}"

    def actualizar_stocks(self):
        """Actualiza los campos de stock total y disponible"""
        from django.db.models import Sum
        
        # Calcular stocks desde MaquinariaStock
        stocks = self.stocks.aggregate(
            total=Sum('stock'),
            disponible=Sum('stock_disponible')
        )
        
        # Actualizar los campos
        self.stock_total = stocks['total'] or 0
        self.stock_disponible = stocks['disponible'] or 0
        
        # Guardar sin llamar al save() normal para evitar recursión
        Maquinaria.objects.filter(pk=self.pk).update(
            stock_total=self.stock_total,
            stock_disponible=self.stock_disponible
        )

    def get_stock_total(self):
        """Calcula el stock total sumando el stock de todas las sucursales"""
        return self.stocks.aggregate(total=models.Sum('stock'))['total'] or 0
    
    def get_stock_disponible_total(self):
        """Calcula el stock disponible total sumando el stock disponible de todas las sucursales"""
        return self.stocks.aggregate(total=models.Sum('stock_disponible'))['total'] or 0
    
    def get_stock_por_sucursal(self):
        """Devuelve un diccionario con el stock por sucursal"""
        return {
            stock.sucursal.nombre: {
                'stock': stock.stock,
                'disponible': stock.stock_disponible,
                'sucursal_id': stock.sucursal.id
            }
            for stock in self.stocks.select_related('sucursal').all()
        }

    def save(self, *args, **kwargs):
        # Primero guardar el objeto
        super().save(*args, **kwargs)
        # Luego actualizar los stocks
        self.actualizar_stocks()

class MaquinariaStock(models.Model):
    """Tabla intermedia para manejar el stock de maquinarias por sucursal"""
    maquinaria = models.ForeignKey(Maquinaria, on_delete=models.CASCADE, related_name='stocks')
    sucursal = models.ForeignKey(Sucursal, on_delete=models.CASCADE, related_name='stocks')
    stock = models.PositiveIntegerField(default=0, verbose_name="Stock Total")
    stock_disponible = models.PositiveIntegerField(default=0, verbose_name="Stock Disponible")
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('maquinaria', 'sucursal')
        verbose_name = "Stock de Maquinaria"
        verbose_name_plural = "Stocks de Maquinaria"

    def __str__(self):
        return f"{self.maquinaria.nombre} - {self.sucursal.nombre} (Stock: {self.stock})"

    def save(self, *args, **kwargs):
        # Si es nuevo registro o se modificó el stock, actualizar stock_disponible
        if not self.pk or self._state.adding:
            self.stock_disponible = self.stock
        super().save(*args, **kwargs)
        
        # Actualizar los totales de la maquinaria
        self.maquinaria.actualizar_stocks()

    def delete(self, *args, **kwargs):
        maquinaria = self.maquinaria
        super().delete(*args, **kwargs)
        # Actualizar los totales de la maquinaria después de eliminar
        maquinaria.actualizar_stocks()