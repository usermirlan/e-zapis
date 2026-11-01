"""Шаблонный фильтр склонения русских существительных после числительных.

Пример: {{ n }} {{ n|ru_plural:"свободный слот,свободных слота,свободных слотов" }}
→ 1 свободный слот, 3 свободных слота, 24 свободных слота, 25 свободных слотов.
"""
from django import template

register = template.Library()


@register.filter
def ru_plural(value, forms):
    try:
        n = abs(int(value))
    except (TypeError, ValueError):
        return ''
    one, few, many = [f.strip() for f in forms.split(',')]
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many
