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

@register.filter
def multiply(value, arg):
    """Multiplica dos números"""
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return 0

@register.filter
def divide(value, arg):
    """Divide dos números"""
    try:
        return float(value) / float(arg)
    except (ValueError, TypeError, ZeroDivisionError):
        return 0
        
@register.filter
def add(value, arg):
    """Suma dos números"""
    try:
        return float(value) + float(arg)
    except (ValueError, TypeError):
        return 0