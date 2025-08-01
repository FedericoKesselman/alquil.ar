# Alquil.AR 

Plataforma integral para la gestión de alquiler de maquinarias con pagos en línea y sistema de calificaciones.

## Características

- **Gestión de Reservas**: Sistema completo de reservas con fechas, stock y sucursales
- **Pagos Seguros**: Integración con MercadoPago (QR y Checkout)
- **Sistema de Calificaciones**: Recargos automáticos según historial del cliente
- **Gestión de Stock**: Control de inventario por sucursal
- **Notificaciones**: Emails automáticos de confirmación y reembolsos
- **Cupones de Descuento**: Sistema de promociones y descuentos
- **Roles de Usuario**: Admin, Empleados y Clientes con permisos específicos

## Tecnologías Utilizadas:

- **Backend**: Django 5.2.1 (Python)
- **Base de Datos**: SQLite
- **Frontend**: Bootstrap 5 + Crispy Forms
- **Pagos**: MercadoPago SDK
- **Túnel**: Ngrok para webhooks

## Instalación 

1. **Clonar el repositorio**
```bash
git clone https://github.com/FedericoKesselman/alquil.ar.git
cd alquil.ar
```

2. **Instalar dependencias**
```bash
pip install -r requirements.txt
```

3. **Configurar variables de entorno**

Crear un archivo `.env` en la raíz del proyecto:
```env
# MercadoPago Credentials (Reemplazar con tus credenciales reales)
MP_ACCESS_TOKEN=TEST-1234567890-123456-abcdef123456789-12345678
MP_PUBLIC_KEY=TEST-abcdef12-3456-78ab-cdef-123456789abc

# Ngrok URL (Actualizar cada vez que inicies ngrok)
NGROK_URL=https://tu-subdominio-unico.ngrok.io
```

4. **Ejecutar migraciones**
```bash
python manage.py migrate
```

5. **Crear superusuario**
```bash
python manage.py createsuperuser
```

6. **Iniciar el servidor**
```bash
python manage.py runserver
```

## Configuración MercadoPago + Ngrok

### 1. Obtener credenciales de MercadoPago

1. Registrarse en [MercadoPago Developers](https://www.mercadopago.com.ar/developers)
2. Crear una aplicación
3. Copiar las credenciales de **TEST** (Access Token y Public Key)
4. Actualizar el archivo `.env`

### 2. Configurar Ngrok

1. **Descargar ngrok** desde [ngrok.com](https://ngrok.com/)
2. **Iniciar túnel** (en terminal separada):
```bash
ngrok http 8000
```
3. **Copiar la URL HTTPS** generada (ej: `https://abc123.ngrok.io`)
4. **Actualizar `.env`** con la nueva URL de ngrok
5. **Reiniciar Django** para aplicar cambios

> ⚠️ **Importante**: La URL de ngrok cambia cada vez que lo reinicias. Actualiza la variable `NGROK_URL` cada vez.

## Uso del Sistema

### Para Clientes
- Explorar catálogo de maquinarias
- Crear reservas con fechas específicas
- Pagar con MercadoPago (tarjeta o QR)
- Recibir códigos de reserva por email
- Aplicar cupones de descuento

### Para Empleados
- Procesar entregas y devoluciones
- Generar códigos QR para pagos presenciales
- Confirmar reservas en sucursal
- Gestionar reembolsos

### Para Administradores
- Gestión completa de usuarios y maquinarias
- Control de stock por sucursal
- Administración de cupones
- Reportes y estadísticas

## Estructura del Proyecto

```
alquil.ar/
├── usuarios/          # Gestión de usuarios y autenticación
├── maquinarias/       # Catálogo y stock de maquinarias
├── reservas/          # Sistema de reservas y pagos
├── core/              # Templates base y utilidades
├── static/            # Archivos estáticos (CSS, JS, img)
├── manage.py          # Django management
└── requirements.txt   # Dependencias Python
```

## Equipo de Desarrollo

- [Ignacio Battaglino](https://github.com/IgnacioBattaglino)
- [Joaquín Di Lorenzo](https://github.com/JoaquinDiLorenzo)
- [Federico Kesselman](https://github.com/FedericoKesselman)
- [Baltazar Menvielle](https://github.com/baltumenvielle)

---

*Proyecto desarrollado para la materia **Ingeniería de Software 2***
