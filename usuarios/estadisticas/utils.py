from django.db.models import Count, Sum, Q
from django.utils import timezone
from datetime import datetime
from reservas.models import Reserva, Reembolso
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
        # Obtener todas las reservas en el rango de fechas sin filtrar por estado
        # Usamos fecha_creacion para tener un filtro más preciso
        reservas = Reserva.objects.filter(
            fecha_creacion__date__gte=fecha_desde,
            fecha_creacion__date__lte=fecha_hasta
        )
        
        if not reservas.exists():
            context['error'] = "No hay datos suficientes para computar la estadística solicitada."
            return context
        
        # Agrupar por maquinaria y contar, teniendo en cuenta la cantidad solicitada
        maquinas_stats = reservas.values(
            'maquinaria__id',
            'maquinaria__nombre',
            'maquinaria__precio_por_dia'
        ).annotate(
            total_alquileres=Sum('cantidad_solicitada'),
            total_ingresos=Sum('precio_total')
        ).order_by('-total_alquileres')  # Mostrar todas las máquinas con reservas
        
        if not maquinas_stats:
            context['error'] = "No hay datos suficientes para computar la estadística solicitada."
            return context
            
        # Preparar información detallada para cada máquina
        info_adicional = []
        for i, item in enumerate(maquinas_stats, 1):
            nombre = item['maquinaria__nombre']
            cantidad = item['total_alquileres']
            ingresos = float(item['total_ingresos'])
            machine_id = item['maquinaria__id']
            info_adicional.append(f"{i}. <strong>{nombre}</strong> - {cantidad} alquileres - ${ingresos:.2f}")
        
        context['datos_grafico'] = {
            'tipo': 'bar',
            'titulo': 'Máquinas Más Alquiladas',
            'labels': [item['maquinaria__nombre'] for item in maquinas_stats],
            'data': [item['total_alquileres'] for item in maquinas_stats],
            'color': 'rgba(54, 162, 235, 0.6)',
            'borde': 'rgba(54, 162, 235, 1)',
            'leyenda': 'Número de Alquileres',
            'informacion_adicional': "<br>".join(info_adicional)
        }
        
    elif tipo_estadistica == 'usuarios_reservas':
        # Obtener todas las reservas relevantes en el rango de fechas
        # Solo consideramos reservas CONFIRMADA, FINALIZADA y NO_DEVUELTA
        reservas = Reserva.objects.filter(
            fecha_creacion__date__gte=fecha_desde,
            fecha_creacion__date__lte=fecha_hasta,
            estado__in=['CONFIRMADA', 'FINALIZADA', 'NO_DEVUELTA']
        )
        
        if not reservas.exists():
            context['error'] = "No hay datos suficientes para computar la estadística solicitada."
            return context
        
        # Agrupar por cliente usando los campos correctos del modelo Usuario personalizado
        usuarios_stats = reservas.values(
            'cliente__nombre',
            'cliente__dni'
        ).annotate(
            total_reservas=Count('id'),
            total_monto=Sum('precio_total')  # También calculamos el monto total
        ).order_by('-total_reservas')[:10]  # Top 10 usuarios
        
        if not usuarios_stats:
            context['error'] = "No hay datos suficientes para computar la estadística solicitada."
            return context
            
        # Agregamos información adicional sobre montos
        for item in usuarios_stats:
            item['monto_formateado'] = f"${float(item['total_monto']):.2f}"
        
        # Crear etiquetas que incluyan nombre, DNI y monto total
        labels = []
        for item in usuarios_stats:
            labels.append(f"{item['cliente__nombre']} (DNI: {item['cliente__dni']}) - {item['monto_formateado']}")
        
        # Información adicional para mostrar debajo del gráfico
        info_adicional = []
        for i, item in enumerate(usuarios_stats, 1):
            info_adicional.append(f"{i}. {item['cliente__nombre']} - {item['total_reservas']} reservas - {item['monto_formateado']}")
        
        context['datos_grafico'] = {
            'tipo': 'bar',
            'titulo': 'Usuarios con Más Reservas',
            'labels': labels,
            'data': [item['total_reservas'] for item in usuarios_stats],
            'color': 'rgba(75, 192, 192, 0.6)',
            'borde': 'rgba(75, 192, 192, 1)',
            'leyenda': 'Número de Reservas',
            'informacion_adicional': "<br>".join(info_adicional)
        }
        
    elif tipo_estadistica == 'ingresos_reembolsos':
        # Calcular ingresos (reservas confirmadas o finalizadas)
        ingresos_query = Reserva.objects.filter(
            Q(estado='CONFIRMADA') | Q(estado='FINALIZADA'),
            # Usar fecha de creación en lugar de fecha de inicio/fin para capturar todas las reservas creadas en el período
            fecha_creacion__date__gte=fecha_desde,
            fecha_creacion__date__lte=fecha_hasta
        )
        
        # Calcular el monto total de ingresos
        monto_ingresos = ingresos_query.aggregate(total=Sum('precio_total'))['total'] or 0
        
        # Contar el número de reservas que generan ingresos
        cantidad_reservas = ingresos_query.count()
        
        # Calcular reembolsos (de la tabla Reembolsos)
        # Solo se consideran reembolsos registrados por empleados al finalizar reservas canceladas
        reembolsos_query = Reembolso.objects.filter(
            fecha_reembolso__date__gte=fecha_desde,
            fecha_reembolso__date__lte=fecha_hasta
        )
        
        # Calcular el monto total de reembolsos
        monto_reembolsos = reembolsos_query.aggregate(total=Sum('monto'))['total'] or 0
        
        # Contar el número de reembolsos
        cantidad_reembolsos = reembolsos_query.count()
        
        if monto_ingresos == 0 and monto_reembolsos == 0:
            context['error'] = "No hay datos suficientes para computar la estadística solicitada."
            return context
        
        # Calcular el balance neto
        balance_neto = monto_ingresos - monto_reembolsos
        
        # Crear información detallada
        info_detallada = [
            f"<strong>Ingresos:</strong> ${float(monto_ingresos):.2f} ({cantidad_reservas} reservas)",
            f"<strong>Reembolsos:</strong> ${float(monto_reembolsos):.2f} ({cantidad_reembolsos} reembolsos)",
            f"<strong>Balance neto:</strong> ${float(balance_neto):.2f}"
        ]
        
        context['datos_grafico'] = {
            'tipo': 'pie',
            'titulo': 'Ingresos vs Reembolsos',
            'labels': [f'Ingresos (${float(monto_ingresos):.2f})', f'Reembolsos (${float(monto_reembolsos):.2f})'],
            'data': [float(monto_ingresos), float(monto_reembolsos)],
            'colores': ['rgba(75, 192, 192, 0.6)', 'rgba(255, 99, 132, 0.6)'],
            'bordes': ['rgba(75, 192, 192, 1)', 'rgba(255, 99, 132, 1)'],
            'informacion_adicional': "<br>".join(info_detallada)
        }
    
    return context