from django.db import transaction
from caja.services import get_or_create_today_cash
from .models import Payment


@transaction.atomic
def crear_pago(*, paciente_nombre, concepto, monto, metodo):
    caja = get_or_create_today_cash()

    pago = Payment.objects.create(
        caja=caja,
        paciente_nombre=paciente_nombre.strip(),
        concepto=concepto.strip(),
        monto=monto,
        metodo=metodo,
    )
    return pago
