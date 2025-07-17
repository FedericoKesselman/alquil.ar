#maquinarias/models.py
from django.db import models
from usuarios.models import Sucursal, Usuario

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
    # Nuevo campo para identificar maquinarias eliminadas/placeholder
    es_placeholder = models.BooleanField(default=False)
    
    # Relación many-to-many con Sucursal a través de MaquinariaStock
    sucursales = models.ManyToManyField(Sucursal, through='MaquinariaStock', related_name='maquinarias')

    def __str__(self):
        return f"{self.nombre} - {self.marca} {self.modelo}"

    def get_precio_para_cliente(self, cliente=None):
        """
        Calcula el precio por día considerando recargos según la calificación del cliente:
        - Clientes con 1 estrella o menos: 30% de recargo
        - Clientes con 2 estrellas o menos (pero más de 1): 20% de recargo
        - Clientes con más de 2 estrellas: sin recargo
        
        Args:
            cliente: Usuario cliente para el que se calcula el precio
            
        Returns:
            tuple: (precio ajustado, porcentaje de recargo)
        """
        if not cliente or not hasattr(cliente, 'calificacion'):
            return (self.precio_por_dia, 0)
            
        if cliente.calificacion <= 1.0:
            # Aplicar recargo del 30% para clientes con 1 estrella o menos
            return (self.precio_por_dia * 1.3, 30)
        elif cliente.calificacion <= 2.0:
            # Aplicar recargo del 20% para clientes con 2 estrellas o menos (pero más de 1)
            return (self.precio_por_dia * 1.2, 20)
            
        return (self.precio_por_dia, 0)

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

    def delete(self, *args, **kwargs):
        """
        Override the delete method to prevent deletion if the machinery
        has any reservations that are not in 'FINALIZADA' state.
        """
        # Import here to avoid circular imports
        from reservas.models import Reserva
        
        # Check if there are any non-finalized reservations for this machinery
        non_finalized_reservations = Reserva.objects.filter(
            maquinaria=self
        ).exclude(
            estado='FINALIZADA'
        )
        
        if non_finalized_reservations.exists():
            # Get details of non-finalized reservations for better error message
            from django.db.models.deletion import ProtectedError
            raise ProtectedError(
                f"No se puede eliminar la maquinaria '{self.nombre}' porque tiene reservas que no están finalizadas.",
                self
            )
        
        # Check if there are any finalized reservations for this machinery
        finalized_reservations = Reserva.objects.filter(
            maquinaria=self, 
            estado='FINALIZADA'
        ).exists()
        
        if finalized_reservations:
            # Get or create a placeholder for machinery
            from maquinarias.views import get_or_create_deleted_machinery_placeholder
            maquinaria_placeholder = get_or_create_deleted_machinery_placeholder()
            
            # Transfer all finalized reservations to the placeholder
            Reserva.objects.filter(
                maquinaria=self,
                estado='FINALIZADA'
            ).update(maquinaria=maquinaria_placeholder)
            
            # Now we can safely delete the machinery
            return super().delete(*args, **kwargs)
        
        # If there are no reservations at all, just delete normally
        return super().delete(*args, **kwargs)

    def clean(self):
        """
        Validate that critical properties can't be changed when there are active reservations
        """
        if self.pk:  # Only for existing objects (not for new ones)
            # Get the original object from the database
            original = Maquinaria.objects.get(pk=self.pk)
            
            # Import here to avoid circular imports
            from reservas.models import Reserva
            has_active_reservations = Reserva.objects.filter(
                maquinaria=self
            ).exclude(
                estado='FINALIZADA'
            ).exists()
            
            if has_active_reservations:
                # Check if critical fields are being modified
                if self.nombre != original.nombre or self.tipo != original.tipo:
                    from django.core.exceptions import ValidationError
                    raise ValidationError("No se pueden modificar los datos básicos de una maquinaria con reservas en curso")
        
        return super().clean()

    def save(self, *args, **kwargs):
        # Run validation
        self.full_clean()
        # Save the object
        super().save(*args, **kwargs)
        # Then update stocks
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

class MaquinariaFavorita(models.Model):
    """Modelo para guardar las maquinarias favoritas de los clientes"""
    usuario = models.ForeignKey(Usuario, on_delete=models.CASCADE, related_name='maquinarias_favoritas')
    maquinaria = models.ForeignKey(Maquinaria, on_delete=models.CASCADE, related_name='favoritos')
    fecha_agregado = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('usuario', 'maquinaria')
        verbose_name = "Maquinaria Favorita"
        verbose_name_plural = "Maquinarias Favoritas"

    def __str__(self):
        return f"{self.usuario.nombre} - {self.maquinaria.nombre}"