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

    appointment_id = models.IntegerField(null=True, blank=True)
    patient_id = models.IntegerField(null=True, blank=True)

    fecha = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.paciente or 'Sin nombre'} - ${self.monto}"


class Gasto(models.Model):
    METODOS = [
        ("efectivo", "Efectivo"),
        ("transferencia", "Transferencia"),
        ("tarjeta", "Tarjeta"),
    ]

    CATEGORIAS = [
        ("insumos", "Insumos"),
        ("laboratorio", "Laboratorio"),
        ("alquiler", "Alquiler"),
        ("servicios", "Servicios"),
        ("sueldos", "Sueldos"),
        ("mantenimiento", "Mantenimiento"),
        ("otros", "Otros"),
    ]

    proveedor = models.CharField(max_length=150, blank=True)

    categoria = models.CharField(
        max_length=50,
        choices=CATEGORIAS
    )

    concepto = models.CharField(max_length=255)

    monto = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    metodo = models.CharField(
        max_length=20,
        choices=METODOS
    )

    afecta_caja = models.BooleanField(
        default=True,
        verbose_name="Afecta caja del día"
    )

    fecha = models.DateTimeField(
        auto_now_add=True
    )

    caja = models.ForeignKey(
        CashSession,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    def __str__(self):
        return f"{self.concepto} - ${self.monto}"


class CompraProveedor(models.Model):
    proveedor = models.CharField(
        max_length=150
    )

    fecha = models.DateField(
        default=timezone.now
    )

    fecha_vencimiento = models.DateField(
        null=True,
        blank=True
    )

    numero_boleta = models.CharField(
        max_length=100,
        blank=True
    )

    concepto = models.CharField(
        max_length=255,
        blank=True
    )

    monto_total = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    observaciones = models.TextField(
        blank=True
    )

    creada_en = models.DateTimeField(
        auto_now_add=True
    )

    def total_pagado(self):
        return sum(
            pago.monto for pago in self.pagos.all()
        )

    def saldo_pendiente(self):
        return self.monto_total - self.total_pagado()

    def estado(self):
        pagado = self.total_pagado()

        if pagado <= 0:
            return "Pendiente"

        if pagado < self.monto_total:
            return "Parcial"

        return "Pagada"

    def estado_vencimiento(self):

        if self.estado() == "Pagada":
            return "Pagada"

        if not self.fecha_vencimiento:
            return "Sin vencimiento"

        hoy = timezone.localdate()

        if self.fecha_vencimiento < hoy:
            return "Vencida"

        if self.fecha_vencimiento == hoy:
            return "Vence hoy"

        return "Al día"

    def __str__(self):
        return f"{self.proveedor} - ${self.monto_total}"


class PagoCompraProveedor(models.Model):
    METODOS = [
        ("efectivo", "Efectivo"),
        ("transferencia", "Transferencia"),
        ("tarjeta", "Tarjeta"),
    ]

    compra = models.ForeignKey(
        CompraProveedor,
        on_delete=models.CASCADE,
        related_name="pagos"
    )

    monto = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    metodo = models.CharField(
        max_length=20,
        choices=METODOS
    )

    afecta_caja = models.BooleanField(
        default=True
    )

    gasto = models.ForeignKey(
        Gasto,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    fecha = models.DateTimeField(
        default=timezone.now
    )

    observaciones = models.CharField(
        max_length=255,
        blank=True
    )

    def __str__(self):
        return f"{self.compra.proveedor} - ${self.monto}"