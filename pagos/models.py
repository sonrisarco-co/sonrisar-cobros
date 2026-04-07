from django.db import models
from django.utils import timezone
from caja.models import CashSession


class Pago(models.Model):
    EFECTIVO = "efectivo"
    TARJETA = "tarjeta"
    TRANSFERENCIA = "transferencia"

    METODOS = [
        (EFECTIVO, "Efectivo"),
        (TARJETA, "Tarjeta"),
        (TRANSFERENCIA, "Transferencia"),
    ]

    caja = models.ForeignKey(
        CashSession,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    paciente = models.CharField(max_length=100, blank=True)
    monto = models.DecimalField(max_digits=10, decimal_places=2)
    metodo = models.CharField(max_length=20, choices=METODOS)
    concepto = models.CharField(max_length=200, blank=True)

    # 🔥 CAMBIO IMPORTANTE
    fecha = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.paciente or 'Sin nombre'} - ${self.monto}"
