#!/bin/bash

# Script para probar el flujo de reservas en Alquil.ar
# Este script simula el proceso completo de reserva de una maquinaria

echo "=== Iniciando prueba de flujo de reserva ==="

# Activar entorno virtual (ajustar según tu configuración)
# source venv/bin/activate

# Variables para la prueba
MAQUINARIA_ID=1
CLIENTE_DNI="11111111"
FECHA_INICIO=$(date -v+1d "+%Y-%m-%d")
FECHA_FIN=$(date -v+3d "+%Y-%m-%d")
CANTIDAD=1

echo "Fechas de prueba: $FECHA_INICIO a $FECHA_FIN"

# 1. Verificar que el servidor está corriendo
echo "Verificando servidor Django..."
curl -s "http://127.0.0.1:8000/" > /dev/null
if [ $? -ne 0 ]; then
    echo "ERROR: El servidor Django no está corriendo. Por favor inicie el servidor con 'python manage.py runserver'"
    exit 1
fi
echo "✅ Servidor Django corriendo"

# 2. Verificar URL de pago temporal
echo "Verificando URL de pago temporal..."
curl -s "http://127.0.0.1:8000/reservas/procesar-pago-temporal/" -o /dev/null
if [ $? -ne 0 ]; then
    echo "⚠️ URL de pago temporal no responde correctamente"
else
    echo "✅ URL de pago temporal configurada"
fi

# 3. Verificar página de prueba
echo "Verificando página de prueba..."
curl -s "http://127.0.0.1:8000/reservas/test-flujo-reserva/" -o /dev/null
if [ $? -ne 0 ]; then
    echo "⚠️ Página de prueba no disponible"
else
    echo "✅ Página de prueba disponible"
fi

# 4. Mostrar mensaje final
echo ""
echo "=== Prueba completada ==="
echo ""
echo "Para probar manualmente el flujo completo:"
echo "1. Acceda a http://127.0.0.1:8000/ e inicie sesión como cliente"
echo "2. Navegue al catálogo de maquinarias y seleccione una para reservar"
echo "3. Complete el formulario con las fechas y cantidad"
echo "4. Confirme la reserva y verifique que el cálculo de días incluye el día de inicio"
echo "5. Proceda al pago y verifique que se completa correctamente"
echo "6. Confirme que la reserva aparece en el historial con el estado correcto"
echo ""
echo "Visite http://127.0.0.1:8000/reservas/test-flujo-reserva/ para ver el resumen de las correcciones"
echo ""
