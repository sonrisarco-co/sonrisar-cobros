from django import template

register = template.Library()


@register.filter
def importe_uy(monto):
    return format(monto, ",.2f").translate(str.maketrans(",.", ".,"))
