from decimal import Decimal

from django.db import models
from django.utils import timezone


class CashSession(models.Model):

    class Status(models.TextChoices):
        ABIERTA = "abierta", "Abierta"
        CERRADA = "cerrada", "Cerrada"

    fecha = models.DateField(
        default=timezone.localdate,
        unique=True,
        db_index=True,
    )

    estado = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.ABIERTA,
        db_index=True,
    )

    saldo_inicial = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
    )

    efectivo = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
    )

    tarjeta = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
    )

    transferencia = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
    )

    total_pagos = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
    )

    saldo_final_declarado = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )

    abierta_en = models.DateTimeField(auto_now_add=True)

    cerrada_en = models.DateTimeField(
        null=True,
        blank=True,
    )

    notas = models.TextField(
        blank=True,
        default="",
    )

    @classmethod
    def obtener_caja_del_dia(cls):
        hoy = timezone.localdate()

        caja = cls.objects.filter(fecha=hoy).first()

        if caja:
            return caja

        return cls.objects.create(
            fecha=hoy,
            estado=cls.Status.ABIERTA,
            saldo_inicial=Decimal("0.00"),
        )

    class Meta:
        ordering = ["-fecha"]

    def __str__(self):
        return f"Caja {self.fecha} ({self.estado})"


# ============================================================
# MOVIMIENTOS DE CAJA
# ============================================================

class MovimientoCaja(models.Model):

    class Tipo(models.TextChoices):
        ENTRADA = "entrada", "Entrada"
        SALIDA = "salida", "Salida"

    caja = models.ForeignKey(
        CashSession,
        on_delete=models.CASCADE,
        related_name="movimientos",
    )

    tipo = models.CharField(
        max_length=10,
        choices=Tipo.choices,
    )

    categoria = models.CharField(
        max_length=100,
        blank=True,
        default="",
    )

    concepto = models.CharField(
        max_length=255,
    )

    monto = models.DecimalField(
        max_digits=10,
        decimal_places=2,
    )

    fecha = models.DateTimeField(
        auto_now_add=True,
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


# ============================================================
# ARQUEOS DE CAJA
# Controles intermedios que NO cierran la caja del día.
# ============================================================

class ArqueoCaja(models.Model):

    class Tipo(models.TextChoices):
        CAMBIO_TURNO = "cambio_turno", "Cambio de turno"
        CONTROL = "control", "Control"
        PRE_CIERRE = "pre_cierre", "Previo al cierre"

    caja = models.ForeignKey(
        CashSession,
        on_delete=models.CASCADE,
        related_name="arqueos",
    )

    tipo = models.CharField(
        max_length=20,
        choices=Tipo.choices,
        default=Tipo.CAMBIO_TURNO,
    )

    responsable = models.CharField(
        max_length=120,
    )

    saldo_esperado = models.DecimalField(
        max_digits=12,
        decimal_places=2,
    )

    saldo_contado = models.DecimalField(
        max_digits=12,
        decimal_places=2,
    )

    diferencia = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        editable=False,
    )

    observacion = models.TextField(
        blank=True,
        default="",
    )

    fecha = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
    )

    def save(self, *args, **kwargs):
        esperado = self.saldo_esperado or Decimal("0.00")
        contado = self.saldo_contado or Decimal("0.00")
        self.diferencia = contado - esperado
        super().save(*args, **kwargs)

    class Meta:
        ordering = ["-fecha"]
        verbose_name = "Arqueo de caja"
        verbose_name_plural = "Arqueos de caja"

    def __str__(self):
        return (
            f"Arqueo {self.caja.fecha} - "
            f"{self.responsable} - "
            f"Diferencia ${self.diferencia}"
        )
