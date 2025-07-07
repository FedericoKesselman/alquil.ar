from django.db.models import Count, Sum, Q
from django.utils import timezone
from datetime import datetime
from reservas.models import Reserva
from maquinarias.models import Maquinaria
import json

def generar_estadisticas(fecha_desde, fecha_hasta, tipo_estadistica):
    """
    Genera los datos de estadísticas según el tipo y rango de fechas solicitados
    
    Args:
        fecha_desde (date): Fecha inicial para filtrar datos
        fecha_hasta (date): Fecha final para filtrar datos
        tipo_estadistica (str): Tipo de estadística a generar
        
    Returns:
        dict: Contexto con los datos para renderizar la estadística
    """
    context = {
        'fecha_desde': fecha_desde,
        'fecha_hasta': fecha_hasta,
        'tipo_estadistica': tipo_estadistica
    }
    
    if tipo_estadistica == 'maquinas_alquiladas':
        # Obtener reservas confirmadas o finalizadas en el rango de fechas
        reservas = Reserva.objects.filter(
            estado__in=['CONFIRMADA', 'FINALIZADA'],
            fecha_inicio__gte=fecha_desde,
            fecha_fin__lte=fecha_hasta
        )
        
        if not reservas.exists():
            context['error'] = "No hay datos suficientes para computar la estadística solicitada."
            return context
        
        # Agrupar por maquinaria y contar, teniendo en cuenta la cantidad solicitada
        maquinas_stats = reservas.values(
            'maquinaria__nombre'
        ).annotate(
            total_alquileres=Sum('cantidad_solicitada')
        ).order_by('-total_alquileres')[:10]  # Top 10 máquinas
        
        if not maquinas_stats:
            context['error'] = "No hay datos suficientes para computar la estadística solicitada."
            return context
        
        context['datos_grafico'] = {
            'tipo': 'bar',
            'titulo': 'Máquinas Más Alquiladas',
            'labels': [item['maquinaria__nombre'] for item in maquinas_stats],
            'data': [item['total_alquileres'] for item in maquinas_stats],
            'color': 'rgba(54, 162, 235, 0.6)',
            'borde': 'rgba(54, 162, 235, 1)',
            'leyenda': 'Número de Alquileres'
        }
        
    elif tipo_estadistica == 'usuarios_reservas':
        # Obtener todas las reservas en el rango de fechas
        reservas = Reserva.objects.filter(
            fecha_inicio__gte=fecha_desde,
            fecha_fin__lte=fecha_hasta
        )
        
        if not reservas.exists():
            context['error'] = "No hay datos suficientes para computar la estadística solicitada."
            return context
        
        # Agrupar por cliente usando los campos correctos del modelo Usuario personalizado
        usuarios_stats = reservas.values(
            'cliente__nombre',
            'cliente__dni'
        ).annotate(
            total_reservas=Count('id')
        ).order_by('-total_reservas')[:10]  # Top 10 usuarios
        
        if not usuarios_stats:
            context['error'] = "No hay datos suficientes para computar la estadística solicitada."
            return context
        
        context['datos_grafico'] = {
            'tipo': 'bar',
            'titulo': 'Usuarios con Más Reservas',
            'labels': [f"{item['cliente__nombre']} (DNI: {item['cliente__dni']})" for item in usuarios_stats],
            'data': [item['total_reservas'] for item in usuarios_stats],
            'color': 'rgba(75, 192, 192, 0.6)',
            'borde': 'rgba(75, 192, 192, 1)',
            'leyenda': 'Número de Reservas'
        }
        
    elif tipo_estadistica == 'ingresos_reembolsos':
        # Calcular ingresos (reservas confirmadas o finalizadas)
        ingresos = Reserva.objects.filter(
            Q(estado='CONFIRMADA') | Q(estado='FINALIZADA'),
            fecha_inicio__gte=fecha_desde,
            fecha_fin__lte=fecha_hasta
        ).aggregate(total=Sum('precio_total'))['total'] or 0
        
        # Calcular reembolsos (reservas canceladas)
        reembolsos = Reserva.objects.filter(
            estado='CANCELADA',
            fecha_inicio__gte=fecha_desde,
            fecha_fin__lte=fecha_hasta
        ).aggregate(total=Sum('precio_total'))['total'] or 0
        
        if ingresos == 0 and reembolsos == 0:
            context['error'] = "No hay datos suficientes para computar la estadística solicitada."
            return context
        
        context['datos_grafico'] = {
            'tipo': 'pie',
            'titulo': 'Ingresos vs Reembolsos',
            'labels': ['Ingresos', 'Reembolsos'],
            'data': [float(ingresos), float(reembolsos)],
            'colores': ['rgba(75, 192, 192, 0.6)', 'rgba(255, 99, 132, 0.6)'],
            'bordes': ['rgba(75, 192, 192, 1)', 'rgba(255, 99, 132, 1)']
        }
    
    return context