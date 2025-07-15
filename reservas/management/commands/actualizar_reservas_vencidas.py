from django.core.management.base import BaseCommand
from reservas.models import Reserva

class Command(BaseCommand):
    help = 'Actualiza el estado de las reservas vencidas y finaliza las que nunca fueron retiradas'

    def handle(self, *args, **options):
        # Actualizar reservas ENTREGADAS a NO_DEVUELTA
        count_no_devueltas = Reserva.actualizar_reservas_vencidas()
        self.stdout.write(
            self.style.SUCCESS(f'Se actualizaron {count_no_devueltas} reservas vencidas a estado "No Devuelta"')
        )
        
        # Finalizar reservas CONFIRMADAS que nunca fueron retiradas
        count_finalizadas = Reserva.finalizar_reservas_no_retiradas()
        self.stdout.write(
            self.style.SUCCESS(f'Se finalizaron automáticamente {count_finalizadas} reservas que nunca fueron retiradas')
        )
