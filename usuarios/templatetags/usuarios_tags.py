from django import template
from usuarios.calificaciones import obtener_calificacion_promedio_cliente

register = template.Library()

@register.filter(name='obtener_calificacion_cliente')
def obtener_calificacion_cliente(cliente_id):
    """
    Filtro de plantilla para obtener la calificación promedio de un cliente.
    
    Uso en plantilla: {{ cliente.id|obtener_calificacion_cliente }}
    
    Args:
        cliente_id: ID del cliente
        
    Returns:
        float: Calificación promedio del cliente, o None si no tiene calificaciones
    """
    if cliente_id is None:
        return None
        
    try:
        calificacion = obtener_calificacion_promedio_cliente(cliente_id)
        
        # Si la calificación es un número, formatearlo para mostrar solo un decimal
        if calificacion is not None:
            return calificacion
        return None
    except Exception as e:
        # Si hay algún error, devolvemos None para que no falle la plantilla
        print(f"Error en filtro obtener_calificacion_cliente para ID {cliente_id}: {str(e)}")
        return None
