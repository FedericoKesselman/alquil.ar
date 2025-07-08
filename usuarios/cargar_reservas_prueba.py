from datetime import date, timedelta
from reservas.models import Reserva, Reembolso
from usuarios.models import Usuario, Sucursal
from maquinarias.models import Maquinaria

# Clientes
cliente1 = Usuario.objects.get(id=12)
cliente2 = Usuario.objects.get(id=13)
cliente3 = Usuario.objects.get(id=15)

# Maquinarias (elige 3 distintas)
maq1 = Maquinaria.objects.first()
maq2 = Maquinaria.objects.all()[1]
maq3 = Maquinaria.objects.all()[2]

# Sucursales (elige 2)
suc1 = Sucursal.objects.first()
suc2 = Sucursal.objects.all()[1]

# Fechas base
hoy = date.today()
base_fecha = hoy - timedelta(days=800)

# Reservas para cliente1
reserva1 = Reserva.objects.create(
    cliente=cliente1,
    maquinaria=maq1,
    sucursal_retiro=suc1,
    fecha_inicio=base_fecha,
    fecha_fin=base_fecha + timedelta(days=maq1.minimo - 1),
    cantidad_solicitada=1,
    precio_total=10000,
    tipo_pago="ONLINE",
    estado="FINALIZADA"
)
reserva2 = Reserva.objects.create(
    cliente=cliente1,
    maquinaria=maq2,
    sucursal_retiro=suc2,
    fecha_inicio=base_fecha + timedelta(days=10),
    fecha_fin=base_fecha + timedelta(days=10 + maq2.minimo - 1),
    cantidad_solicitada=2,
    precio_total=8000,
    tipo_pago="ONLINE",
    estado="CANCELADA"
)

# Crear reembolso para la reserva cancelada del cliente1
Reembolso.objects.create(
    cliente=cliente1,
    reserva=reserva2,
    monto=6000,  # Reembolso parcial
    dni_cliente=cliente1.dni
)

# Reservas para cliente2 (id=13)
reserva3 = Reserva.objects.create(
    cliente=cliente2,
    maquinaria=maq2,
    sucursal_retiro=suc1,
    fecha_inicio=base_fecha + timedelta(days=20),
    fecha_fin=base_fecha + timedelta(days=20 + maq2.minimo - 1),
    cantidad_solicitada=1,
    precio_total=12000,
    tipo_pago="ONLINE",
    estado="FINALIZADA"
)
reserva4 = Reserva.objects.create(
    cliente=cliente2,
    maquinaria=maq3,
    sucursal_retiro=suc2,
    fecha_inicio=base_fecha + timedelta(days=30),
    fecha_fin=base_fecha + timedelta(days=30 + maq3.minimo - 1),
    cantidad_solicitada=1,
    precio_total=5000,
    tipo_pago="ONLINE",
    estado="CANCELADA"
)

# Crear reembolso completo para la reserva cancelada del cliente2
Reembolso.objects.create(
    cliente=cliente2,
    reserva=reserva4,
    monto=5000,  # Reembolso completo
    dni_cliente=cliente2.dni
)

# Reservas para cliente3
reserva5 = Reserva.objects.create(
    cliente=cliente3,
    maquinaria=maq1,
    sucursal_retiro=suc2,
    fecha_inicio=base_fecha + timedelta(days=40),
    fecha_fin=base_fecha + timedelta(days=40 + maq1.minimo - 1),
    cantidad_solicitada=1,
    precio_total=15000,
    tipo_pago="ONLINE",
    estado="FINALIZADA"
)
reserva6 = Reserva.objects.create(
    cliente=cliente3,
    maquinaria=maq3,
    sucursal_retiro=suc1,
    fecha_inicio=base_fecha + timedelta(days=50),
    fecha_fin=base_fecha + timedelta(days=50 + maq3.minimo - 1),
    cantidad_solicitada=2,
    precio_total=9000,
    tipo_pago="ONLINE",
    estado="CANCELADA"
)

# Crear otro reembolso para el cliente3
Reembolso.objects.create(
    cliente=cliente3,
    reserva=reserva6,
    monto=7500,  # Reembolso parcial (retienen 1500 por gastos administrativos)
    dni_cliente=cliente3.dni
)

# Crear reservas adicionales para tener más datos de prueba
reserva7 = Reserva.objects.create(
    cliente=cliente1,
    maquinaria=maq3,
    sucursal_retiro=suc1,
    fecha_inicio=base_fecha + timedelta(days=60),
    fecha_fin=base_fecha + timedelta(days=60 + maq3.minimo - 1),
    cantidad_solicitada=1,
    precio_total=4500,
    tipo_pago="PRESENCIAL",
    estado="CONFIRMADA"
)

reserva8 = Reserva.objects.create(
    cliente=cliente2,
    maquinaria=maq1,
    sucursal_retiro=suc2,
    fecha_inicio=base_fecha + timedelta(days=70),
    fecha_fin=base_fecha + timedelta(days=70 + maq1.minimo - 1),
    cantidad_solicitada=3,
    precio_total=25000,
    tipo_pago="ONLINE",
    estado="FINALIZADA"
)

# Crear una reserva más reciente (hace 30 días) con reembolso reciente
reserva_reciente = Reserva.objects.create(
    cliente=cliente3,
    maquinaria=maq2,
    sucursal_retiro=suc1,
    fecha_inicio=hoy - timedelta(days=30),
    fecha_fin=hoy - timedelta(days=30) + timedelta(days=maq2.minimo - 1),
    cantidad_solicitada=1,
    precio_total=7000,
    tipo_pago="ONLINE",
    estado="CANCELADA"
)

# Crear reembolso reciente para mostrar datos más actuales
Reembolso.objects.create(
    cliente=cliente3,
    reserva=reserva_reciente,
    monto=6300,  # Reembolso parcial reciente
    dni_cliente=cliente3.dni
)

print("Reservas de prueba y reembolsos creados correctamente.")
print(f"Se crearon {Reserva.objects.count()} reservas en total.")
print(f"Se crearon {Reembolso.objects.count()} reembolsos en total.")