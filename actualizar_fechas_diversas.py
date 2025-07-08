#!/usr/bin/env python
"""
Script para distribuir las fechas de reservas en diferentes períodos
para poder probar el filtrado de estadísticas
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
from django.utils import timezone

def distribuir_fechas():
    """Distribuye las fechas de reservas en diferentes períodos"""
    
    # Obtener todas las reservas
    reservas = Reserva.objects.all()
    total_reservas = reservas.count()
    
    if total_reservas == 0:
        print("No hay reservas en la base de datos")
        return
    
    print(f"Distribuyendo fechas para {total_reservas} reservas...")
    
    # Definir períodos de fechas
    fechas_base = [
        datetime(2023, 10, 15, 10, 30, 0),  # Octubre 2023
        datetime(2023, 11, 20, 14, 45, 0),  # Noviembre 2023
        datetime(2023, 12, 10, 9, 15, 0),   # Diciembre 2023
        datetime(2024, 1, 15, 16, 20, 0),   # Enero 2024
        datetime(2024, 2, 25, 11, 0, 0),    # Febrero 2024
        datetime(2024, 3, 20, 13, 30, 0),   # Marzo 2024
        datetime(2024, 4, 12, 15, 45, 0),   # Abril 2024
        datetime(2024, 5, 8, 12, 15, 0),    # Mayo 2024
        datetime(2024, 6, 5, 17, 0, 0),     # Junio 2024
        datetime(2025, 7, 8, 16, 46, 0),    # Julio 2025 (actual)
    ]
    
    # Distribuir reservas en estos períodos
    reservas_por_periodo = total_reservas // len(fechas_base)
    resto = total_reservas % len(fechas_base)
    
    contador = 0
    for i, fecha_base in enumerate(fechas_base):
        # Calcular cuántas reservas van en este período
        cantidad = reservas_por_periodo + (1 if i < resto else 0)
        
        # Obtener las reservas para este período
        reservas_periodo = list(reservas[contador:contador + cantidad])
        
        for j, reserva in enumerate(reservas_periodo):
            # Agregar variación aleatoria de días (±7 días)
            variacion_dias = random.randint(-7, 7)
            variacion_horas = random.randint(-5, 5)
            
            nueva_fecha = fecha_base + timedelta(days=variacion_dias, hours=variacion_horas)
            
            # Convertir a timezone aware
            nueva_fecha_tz = timezone.make_aware(nueva_fecha)
            
            # Actualizar la reserva
            reserva.fecha_creacion = nueva_fecha_tz
            
            # También actualizar fecha_inicio y fecha_fin para que sean coherentes
            # (fecha_inicio unos días después de fecha_creacion)
            dias_adelante = random.randint(1, 14)  # Entre 1 y 14 días después
            duracion = random.randint(1, 4)  # Duración entre 1 y 4 días (máximo 4)
            
            fecha_inicio = nueva_fecha_tz.date() + timedelta(days=dias_adelante)
            fecha_fin = fecha_inicio + timedelta(days=duracion)
            
            # Usar update para saltarse las validaciones del modelo
            Reserva.objects.filter(id=reserva.id).update(
                fecha_creacion=nueva_fecha_tz,
                fecha_inicio=fecha_inicio,
                fecha_fin=fecha_fin
            )
            
            print(f"Reserva {reserva.id}: {nueva_fecha_tz.strftime('%Y-%m-%d %H:%M:%S')}")
        
        contador += cantidad
    
    # También actualizar algunos reembolsos si existen
    reembolsos = Reembolso.objects.all()
    if reembolsos.exists():
        print(f"\nActualizando fechas de {reembolsos.count()} reembolsos...")
        
        for reembolso in reembolsos:
            # Poner fecha de reembolso aleatoria en los últimos 6 meses
            fecha_base = datetime(2024, 6, 1, 10, 0, 0)
            variacion_dias = random.randint(0, 180)  # Últimos 6 meses
            variacion_horas = random.randint(0, 23)
            
            nueva_fecha = fecha_base + timedelta(days=variacion_dias, hours=variacion_horas)
            nueva_fecha_tz = timezone.make_aware(nueva_fecha)
            
            reembolso.fecha_reembolso = nueva_fecha_tz
            reembolso.save()
            
            print(f"Reembolso {reembolso.id}: {nueva_fecha_tz.strftime('%Y-%m-%d %H:%M:%S')}")
    
    print(f"\n✅ Fechas distribuidas exitosamente!")
    print("Ahora puedes probar el filtrado de estadísticas con diferentes rangos de fechas.")

if __name__ == '__main__':
    distribuir_fechas()
