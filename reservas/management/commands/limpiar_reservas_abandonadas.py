from django.core.management.base import BaseCommand
from django.utils import timezone
from reservas.models import Reserva
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Elimina reservas abandonadas en estado PENDIENTE_PAGO'

    def handle(self, *args, **options):
        # Obtener reservas en PENDIENTE_PAGO creadas hace más de 30 minutos
        tiempo_limite = timezone.now() - timezone.timedelta(minutes=30)
        
        reservas_abandonadas = Reserva.objects.filter(
            estado='PENDIENTE_PAGO',
            fecha_creacion__lt=tiempo_limite
        )
        
        count = reservas_abandonadas.count()
        if count > 0:
            logger.info(f"Eliminando {count} reservas abandonadas")
            self.stdout.write(f"Eliminando {count} reservas abandonadas")
            
            # Eliminar las reservas abandonadas
            reservas_abandonadas.delete()
            
            self.stdout.write(self.style.SUCCESS(f"Se eliminaron {count} reservas abandonadas"))
        else:
            self.stdout.write("No se encontraron reservas abandonadas para eliminar")
