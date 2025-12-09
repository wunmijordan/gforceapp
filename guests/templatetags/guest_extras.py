from django import template

register = template.Library()

@register.filter
def status_color(value):
    mapping = {
        'Planted': 'success',
        'Planted Elsewhere': 'danger',
        'Relocated': 'primary',
        'Work in Progress': 'warning',
        'New Guest': 'gray-800',
    }
    return mapping.get(value, 'gray-800')


@register.filter
def attr(obj, field_name):
    """
    Safely get an attribute from a model instance or a dict.
    Returns None if not found.
    """
    if isinstance(obj, dict):
        return obj.get(field_name)
    return getattr(obj, field_name, None)


@register.filter
def get_item(dictionary, key):
    return dictionary.get(key)
