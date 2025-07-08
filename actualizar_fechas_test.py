#!/usr/bin/env python
"""
Script para actualizar fechas de reservas con datos de prueba
Ejecutar con: python actualizar_fechas_test.py
"""
import os
import sys
import django
from datetime import datetime, timedelta
import random

# Configurar Django
sys.path.append('/Users/nacho/Facultad/UNIVERSIDAD/TERCER AÑO/Ing2/alquil.ar')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'alquilar.settings')
django.setup()

from reservas.models import Reserva, Reembolso

def actualizar_fechas_reservas():
    """Actualiza las fechas de las reservas con datos distribuidos en el tiempo"""
    
    reservas = Reserva.objects.all()
    print(f"Actualizando fechas para {reservas.count()} reservas...")
    
    # Fechas base para distribuir
    fechas_base = [
        datetime(2023, 6, 15),   # Junio 2023
        datetime(2023, 9, 20),   # Septiembre 2023
        datetime(2023, 12, 10),  # Diciembre 2023
        datetime(2024, 2, 14),   # Febrero 2024
        datetime(2024, 4, 18),   # Abril 2024
        datetime(2024, 6, 22),   # Junio 2024
        datetime(2024, 8, 12),   # Agosto 2024
        datetime(2024, 10, 5),   # Octubre 2024
        datetime(2024, 12, 1),   # Diciembre 2024
        datetime(2025, 1, 10),   # Enero 2025
    ]
    
    for i, reserva in enumerate(reservas):
        # Seleccionar una fecha base aleatoria
        fecha_base = random.choice(fechas_base)
        
        # Agregar variación aleatoria de días
        variacion_dias = random.randint(-30, 30)
        fecha_nueva = fecha_base + timedelta(days=variacion_dias)
        
        # Agregar variación de horas
        hora_aleatoria = random.randint(8, 18)
        minuto_aleatorio = random.randint(0, 59)
        
        fecha_nueva = fecha_nueva.replace(hour=hora_aleatoria, minute=minuto_aleatorio)
        
        # Actualizar la reserva
        reserva.fecha_creacion = fecha_nueva
        
        # También actualizar fecha_inicio y fecha_fin para que sean consistentes
        if reserva.fecha_inicio:
            diferencia_inicio = reserva.fecha_inicio - reserva.fecha_creacion
            reserva.fecha_inicio = fecha_nueva + diferencia_inicio
        
        if reserva.fecha_fin:
            diferencia_fin = reserva.fecha_fin - reserva.fecha_creacion
            reserva.fecha_fin = fecha_nueva + diferencia_fin
        
        reserva.save()
        print(f"Reserva {reserva.id}: Nueva fecha {fecha_nueva.strftime('%Y-%m-%d %H:%M')}")
    
    print("✅ Fechas de reservas actualizadas correctamente")

def actualizar_fechas_reembolsos():
    """Actualiza las fechas de los reembolsos"""
    
    reembolsos = Reembolso.objects.all()
    if not reembolsos.exists():
        print("No hay reembolsos para actualizar")
        return
        
    print(f"Actualizando fechas para {reembolsos.count()} reembolsos...")
    
    for reembolso in reembolsos:
        # Los reembolsos deberían ser posteriores a las reservas
        if reembolso.reserva:
            fecha_reserva = reembolso.reserva.fecha_creacion
            dias_despues = random.randint(1, 30)  # 1-30 días después
            fecha_reembolso = fecha_reserva + timedelta(days=dias_despues)
            
            reembolso.fecha_reembolso = fecha_reembolso
            reembolso.save()
            print(f"Reembolso {reembolso.id}: Nueva fecha {fecha_reembolso.strftime('%Y-%m-%d')}")
    
    print("✅ Fechas de reembolsos actualizadas correctamente")

if __name__ == "__main__":
    print("🔄 Iniciando actualización de fechas...")
    actualizar_fechas_reservas()
    actualizar_fechas_reembolsos()
    print("🎉 ¡Actualización completada!")
