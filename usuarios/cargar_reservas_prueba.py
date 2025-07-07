from datetime import date, timedelta
from reservas.models import Reserva
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
Reserva.objects.create(
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
Reserva.objects.create(
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

# Reservas para cliente2 (id=13)
Reserva.objects.create(
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
Reserva.objects.create(
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

# Reservas para cliente3
Reserva.objects.create(
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
Reserva.objects.create(
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

print("Reservas de prueba creadas correctamente.")