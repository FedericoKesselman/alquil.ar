# maquinarias/templatetags/math_extras.py
from django import template

register = template.Library()

@register.filter
def sub(value, arg):
    """Resta dos números"""
    try:
        return int(value) - int(arg)
    except (ValueError, TypeError):
        return 0