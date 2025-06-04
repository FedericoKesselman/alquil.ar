from django.db import models

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
    imagen = models.ImageField(upload_to='maquinarias/', null=True, blank=True)
    precio_por_dia = models.FloatField()
    stock_total = models.PositiveIntegerField(default=0)
    stock_disponible = models.PositiveIntegerField(default=0)
    minimo = models.SmallIntegerField()
    maximo = models.SmallIntegerField()
    cantDias_total = models.SmallIntegerField()
    cantDias_parcial = models.SmallIntegerField()
    cantDias_nulo = models.SmallIntegerField()

    def __str__(self):
        return f"{self.nombre} - {self.marca} {self.modelo}"

    def save(self, *args, **kwargs):
        # Si es una nueva maquinaria, inicializar stock_disponible igual a stock_total
        if not self.pk:
            self.stock_disponible = self.stock_total
        super().save(*args, **kwargs)