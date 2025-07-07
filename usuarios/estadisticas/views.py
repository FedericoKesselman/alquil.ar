from datetime import datetime
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from usuarios.decorators import solo_admin
from .utils import generar_estadisticas
import logging

logger = logging.getLogger(__name__)

@login_required
@solo_admin
def procesar_estadisticas(request):
    """
    Procesa una solicitud AJAX para generar estadísticas
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)
    
    fecha_desde = request.POST.get('fecha_desde')
    fecha_hasta = request.POST.get('fecha_hasta')
    tipo_estadistica = request.POST.get('tipo_estadistica')
    
    if not fecha_desde or not fecha_hasta or not tipo_estadistica:
        return JsonResponse({'error': 'Parámetros incompletos'}, status=400)
    
    try:
        fecha_desde = datetime.strptime(fecha_desde, '%Y-%m-%d').date()
        fecha_hasta = datetime.strptime(fecha_hasta, '%Y-%m-%d').date()
        
        if fecha_desde > fecha_hasta:
            return JsonResponse({'error': 'La fecha inicial debe ser anterior a la fecha final'}, status=400)
            
        resultado = generar_estadisticas(fecha_desde, fecha_hasta, tipo_estadistica)
        
        if 'error' in resultado:
            return JsonResponse({'error': resultado['error']}, status=200)
        
        return JsonResponse(resultado)
    
    except ValueError:
        logger.error("Error de formato de fecha al procesar estadísticas")
        return JsonResponse({'error': 'Formato de fecha inválido'}, status=400)
    except Exception as e:
        logger.exception("Error al generar estadísticas")
        return JsonResponse({'error': f'Error inesperado: {str(e)}'}, status=500)