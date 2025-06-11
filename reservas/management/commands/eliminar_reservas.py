from django.core.management.base import BaseCommand
from django.db import transaction
from reservas.models import Reserva
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Elimina todas las reservas de la base de datos'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Forzar la eliminación sin pedir confirmación',
        )

    def handle(self, *args, **options):
        try:
            # Contar reservas antes de eliminar
            total_reservas = Reserva.objects.count()
            
            if total_reservas == 0:
                self.stdout.write(
                    self.style.WARNING('No hay reservas para eliminar.')
                )
                return
            
            # Si no se usa --force, pedir confirmación
            if not options['force']:
                confirmacion = input(f'¿Estás seguro que deseas eliminar {total_reservas} reservas? Esta acción no se puede deshacer. [s/N]: ')
                if confirmacion.lower() != 's':
                    self.stdout.write(
                        self.style.WARNING('Operación cancelada.')
                    )
                    return

            # Usar transacción para asegurar que todo se elimina o nada
            with transaction.atomic():
                # Registrar información antes de eliminar
                logger.info(f'Iniciando eliminación de {total_reservas} reservas')
                logger.info(f'Timestamp: {timezone.now()}')
                
                # Eliminar todas las reservas
                Reserva.objects.all().delete()
                
                # Confirmar eliminación
                self.stdout.write(
                    self.style.SUCCESS(f'Se eliminaron exitosamente {total_reservas} reservas.')
                )
                logger.info(f'Eliminación completada. {total_reservas} reservas eliminadas.')

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error al eliminar las reservas: {str(e)}')
            )
            logger.error(f'Error al eliminar reservas: {str(e)}')
            raise 