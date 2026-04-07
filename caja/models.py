from django.db import models
from django.utils import timezone


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
    cerrada_en = models.DateTimeField(null=True, blank=True)

    notas = models.TextField(blank=True, default="")

    @staticmethod
    def obtener_caja_del_dia():
        hoy = timezone.localdate()
        caja, _ = CashSession.objects.get_or_create(
            fecha=hoy,
            defaults={'estado': CashSession.Status.ABIERTA}
        )
        return caja

    class Meta:
        ordering = ["-fecha"]

    def __str__(self):
        return f"Caja {self.fecha} ({self.estado})"


    
# ============================================================
# NUEVO — MOVIMIENTOS DE CAJA (NO ROMPE NADA DEL SISTEMA)
# ============================================================

class MovimientoCaja(models.Model):
    class Tipo(models.TextChoices):
        ENTRADA = "entrada", "Entrada"
        SALIDA = "salida", "Salida"

    caja = models.ForeignKey(
        'CashSession',  # <--- así, sin importar nada arriba
        on_delete=models.CASCADE,
        related_name="movimientos"
    )

    tipo = models.CharField(max_length=10, choices=Tipo.choices)
    concepto = models.CharField(max_length=255)
    monto = models.DecimalField(max_digits=10, decimal_places=2)
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fecha"]

    def __str__(self):
        return f"{self.tipo.upper()} - {self.concepto} (${self.monto})"




