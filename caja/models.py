from django.db import models
from django.utils import timezone
from decimal import Decimal


class CashSession(models.Model):

    class Status(models.TextChoices):
        ABIERTA = "abierta", "Abierta"
        CERRADA = "cerrada", "Cerrada"

    fecha = models.DateField(
        default=timezone.localdate,
        unique=True,
        db_index=True
    )

    estado = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.ABIERTA,
        db_index=True
    )

    saldo_inicial = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0
    )

    efectivo = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0
    )

    tarjeta = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0
    )

    transferencia = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0
    )

    total_pagos = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0
    )

    saldo_final_declarado = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True
    )

    abierta_en = models.DateTimeField(auto_now_add=True)

    cerrada_en = models.DateTimeField(
        null=True,
        blank=True
    )

    notas = models.TextField(
        blank=True,
        default=""
    )

    @classmethod
    def obtener_caja_del_dia(cls):

        hoy = timezone.localdate()

        # =========================================
        # BUSCAR SOLO CAJA DE HOY
        # =========================================

        caja = cls.objects.filter(
            fecha=hoy
        ).first()

        if caja:
            return caja

        # =========================================
        # CREAR NUEVA CAJA LIMPIA
        # =========================================

        return cls.objects.create(
            fecha=hoy,
            estado=cls.Status.ABIERTA,
            saldo_inicial=Decimal("0.00"),
        )

        # =====================================================
        # SI EXISTE → DEVOLVERLA
        # =====================================================

        if caja_existente:
            return caja_existente

        # =====================================================
        # SI NO EXISTE → CREAR NUEVA
        # =====================================================

        return cls.objects.create(
            fecha=hoy,
            estado=cls.Status.ABIERTA,
        )


# ============================================================
# MOVIMIENTOS DE CAJA
# ============================================================

class MovimientoCaja(models.Model):

    class Tipo(models.TextChoices):
        ENTRADA = "entrada", "Entrada"
        SALIDA = "salida", "Salida"

    caja = models.ForeignKey(
        'CashSession',
        on_delete=models.CASCADE,
        related_name="movimientos"
    )

    tipo = models.CharField(
        max_length=10,
        choices=Tipo.choices
    )

    # =====================================================
    # NUEVO — CATEGORÍA PROFESIONAL
    # =====================================================

    categoria = models.CharField(
        max_length=100,
        blank=True,
        default=""
    )

    # =====================================================
    # DETALLE DEL MOVIMIENTO
    # =====================================================

    concepto = models.CharField(
        max_length=255
    )

    monto = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    fecha = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        ordering = ["-fecha"]

    def __str__(self):
        categoria = f"[{self.categoria}] " if self.categoria else ""

        return (
            f"{categoria}"
            f"{self.tipo.upper()} - "
            f"{self.concepto} "
            f"(${self.monto})"
        )