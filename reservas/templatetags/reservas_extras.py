# reservas/templatetags/reservas_extras.py
from django import template
from datetime import datetime

register = template.Library()

@register.filter
def days_until(fecha_inicio, fecha_fin):
    """
    Calcula la diferencia en días entre dos fechas
    """
    try:
        if isinstance(fecha_inicio, str):
            fecha_inicio = datetime.strptime(fecha_inicio, '%Y-%m-%d').date()
        if isinstance(fecha_fin, str):
            fecha_fin = datetime.strptime(fecha_fin, '%Y-%m-%d').date()
        
        delta = fecha_fin - fecha_inicio
        return delta.days
    except (ValueError, TypeError, AttributeError):
        return 0

@register.filter
def multiply(value, arg):
    """
    Multiplica dos valores
    """
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return 0

@register.filter
def format_price(value):
    """
    Formatea un precio con separadores de miles
    """
    try:
        return f"${float(value):,.2f}".replace(',', '.')
    except (ValueError, TypeError):
        return f"${value}"