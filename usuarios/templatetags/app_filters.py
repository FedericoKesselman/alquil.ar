from django import template

register = template.Library()

@register.filter(name='pluralize_es')
def pluralize_es(value, arg='s'):
    """
    Devuelve una cadena vacía si el valor es 1, de lo contrario, devuelve el argumento.
    Útil para pluralizar en español.
    
    Uso: {{ value|pluralize_es:"s" }}
    """
    if ',' in arg:
        singular, plural = arg.split(',')
        if int(value) == 1:
            return singular
        return plural
    else:
        if int(value) == 1:
            return ''
        return arg
