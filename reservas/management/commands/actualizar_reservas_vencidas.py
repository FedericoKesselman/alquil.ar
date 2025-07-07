from django.core.management.base import BaseCommand
from reservas.models import Reserva

class Command(BaseCommand):
    help = 'Actualiza el estado de las reservas cuya fecha de fin ya pasó a NO_DEVUELTA'

    def handle(self, *args, **options):
        count = Reserva.actualizar_reservas_vencidas()
        self.stdout.write(
            self.style.SUCCESS(f'Se actualizaron {count} reservas vencidas a estado "No Devuelta"')
        )
