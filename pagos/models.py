from decimal import Decimal, ROUND_HALF_UP

from django.db import models
from django.utils import timezone
from caja.models import CashSession
from django.conf import settings


class Pago(models.Model):
    EFECTIVO = "efectivo"
    TARJETA = "tarjeta"
    TRANSFERENCIA = "transferencia"

    # Conservamos "tarjeta" como método interno para no romper caja/reportes
    # existentes. El detalle Débito/Crédito se guarda aparte.
    METODOS = [
        (EFECTIVO, "Efectivo"),
        (TARJETA, "Tarjeta"),
        (TRANSFERENCIA, "Transferencia"),
    ]

    TARJETA_DEBITO = "debito"
    TARJETA_CREDITO = "credito"

    TIPOS_TARJETA = [
        (TARJETA_DEBITO, "Débito"),
        (TARJETA_CREDITO, "Crédito"),
    ]

    CFE_NO_SOLICITADO = "no_solicitado"
    CFE_PENDIENTE = "pendiente"
    CFE_EMITIDO = "emitido"
    CFE_RECHAZADO = "rechazado"
    CFE_ANULADO = "anulado"

    ESTADOS_CFE = [
        (CFE_NO_SOLICITADO, "Sin CFE"),
        (CFE_PENDIENTE, "Pendiente CFE"),
        (CFE_EMITIDO, "CFE emitido"),
        (CFE_RECHAZADO, "CFE rechazado"),
        (CFE_ANULADO, "CFE anulado"),
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
    tipo_tarjeta = models.CharField(
        max_length=10,
        choices=TIPOS_TARJETA,
        blank=True,
        default="",
        help_text="Detalle del pago con tarjeta: débito o crédito."
    )
    concepto = models.CharField(max_length=200, blank=True)

    appointment_id = models.IntegerField(null=True, blank=True)
    patient_id = models.IntegerField(null=True, blank=True)

    protesis_id = models.IntegerField(null=True, blank=True)

    # ==========================================
    # PREPARACIÓN PARA FACTURACIÓN ELECTRÓNICA
    # ==========================================
    # Por ahora estos campos son solo internos.
    # No se envía nada a DGI/Facture hasta activar la integración.
    cfe_solicitado = models.BooleanField(
        default=False,
        verbose_name="Preparar comprobante electrónico"
    )

    cfe_estado = models.CharField(
        max_length=20,
        choices=ESTADOS_CFE,
        default=CFE_NO_SOLICITADO
    )

    # Guardamos la tasa aplicada al momento del cobro para conservar
    # el histórico aunque la configuración fiscal cambie en el futuro.
    tasa_iva_cfe = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("10.00")
    )

    cfe_tipo = models.CharField(max_length=20, blank=True)
    cfe_serie = models.CharField(max_length=10, blank=True)
    cfe_numero = models.CharField(max_length=30, blank=True)

    # Fecha fiscal real en la que se emitió el CFE.
    # Es independiente de la fecha en que se registró el pago.
    cfe_fecha_emision = models.DateField(
        null=True,
        blank=True
    )

    facture_cfe_id = models.CharField(max_length=100, blank=True)
    cfe_pdf_url = models.URLField(max_length=500, blank=True)
    cfe_xml_url = models.URLField(max_length=500, blank=True)
    cfe_xml_firmado = models.TextField(blank=True)
    cfe_error = models.TextField(blank=True)

    # ==========================================
    # NOTA DE CRÉDITO / ANULACIÓN DEL CFE
    # ==========================================
    # Se completa únicamente cuando el eTicket original fue corregido
    # mediante una Nota de Crédito electrónica.
    nc_cfe_id = models.CharField(max_length=100, blank=True)
    nc_serie = models.CharField(max_length=10, blank=True)
    nc_numero = models.CharField(max_length=30, blank=True)
    nc_xml_firmado = models.TextField(blank=True)
    nc_error = models.TextField(blank=True)

    fecha = models.DateTimeField(default=timezone.now)

    @property
    def metodo_detallado(self):
        if self.metodo == self.TARJETA:
            if self.tipo_tarjeta == self.TARJETA_DEBITO:
                return "Débito"
            if self.tipo_tarjeta == self.TARJETA_CREDITO:
                return "Crédito"
        return self.get_metodo_display()

    @property
    def monto_neto_cfe(self):
        """Base imponible cuando el monto cargado ya incluye IVA."""
        tasa = self.tasa_iva_cfe or Decimal("0.00")
        divisor = Decimal("1.00") + (tasa / Decimal("100.00"))
        if divisor == 0:
            return self.monto
        return (self.monto / divisor).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP
        )

    @property
    def monto_iva_cfe(self):
        """IVA incluido en el monto final."""
        return (self.monto - self.monto_neto_cfe).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP
        )

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
        ("devolucion_paciente", "Devolución a paciente"),
        ("entrega_temporal_paciente", "Entrega temporal a paciente"),
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


class DevolucionPaciente(models.Model):
    METODOS = [
        ("efectivo", "Efectivo"),
        ("transferencia", "Transferencia"),
        ("tarjeta", "Tarjeta"),
    ]

    TIPO_DEFINITIVA = "definitiva"
    TIPO_TEMPORAL = "temporal"
    TIPOS = [
        (TIPO_DEFINITIVA, "Definitiva"),
        (TIPO_TEMPORAL, "Temporal / pendiente de reintegro"),
    ]

    pago_original = models.ForeignKey(
        Pago,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="devoluciones"
    )

    gasto = models.OneToOneField(
        Gasto,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="devolucion_paciente"
    )

    paciente = models.CharField(max_length=100)
    patient_id = models.IntegerField(null=True, blank=True, db_index=True)
    appointment_id = models.IntegerField(null=True, blank=True, db_index=True)
    protesis_id = models.IntegerField(null=True, blank=True, db_index=True)

    monto = models.DecimalField(max_digits=10, decimal_places=2)
    metodo = models.CharField(max_length=20, choices=METODOS)
    concepto = models.CharField(max_length=255, blank=True)
    fecha = models.DateTimeField(default=timezone.now, db_index=True)

    # Tipo de devolución. Los registros históricos quedan como definitivos
    # por defecto para conservar exactamente el comportamiento anterior.
    tipo = models.CharField(
        max_length=20,
        choices=TIPOS,
        default=TIPO_DEFINITIVA,
        db_index=True,
    )

    # Solo se usa para devoluciones temporales. Mientras reintegrada=False,
    # el dinero está pendiente de volver, pero NO reduce el total pagado
    # odontológico del paciente.
    reintegrada = models.BooleanField(default=False, db_index=True)
    fecha_reintegro = models.DateTimeField(null=True, blank=True)

    @property
    def es_temporal(self):
        return self.tipo == self.TIPO_TEMPORAL

    @property
    def pendiente_reintegro(self):
        return self.es_temporal and not self.reintegrada

    @property
    def afecta_saldo_odontologico(self):
        return self.tipo == self.TIPO_DEFINITIVA

    # ==========================================
    # NOTA DE CRÉDITO ELECTRÓNICA
    # ==========================================
    nc_solicitada = models.BooleanField(
        default=False,
        verbose_name="Emitir Nota de Crédito"
    )

    nc_cfe_id = models.CharField(
        max_length=100,
        blank=True
    )

    nc_serie = models.CharField(
        max_length=10,
        blank=True
    )

    nc_numero = models.CharField(
        max_length=30,
        blank=True
    )

    nc_fecha_emision = models.DateField(
        null=True,
        blank=True
    )

    nc_xml_firmado = models.TextField(
        blank=True
    )

    nc_error = models.TextField(
        blank=True
    )

    class Meta:
        ordering = ["-fecha", "-id"]

    def __str__(self):
        return f"Devolución - {self.paciente} - ${self.monto}"


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


class SesionAcceso(models.Model):
    MOTIVO_SALIDA = [
        ("manual", "Salida registrada"),
        ("nueva_sesion", "Cierre al iniciar una nueva sesión"),
        ("expirada", "Sesión expirada"),
    ]

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="sesiones_sonrisar_cobros",
    )
    ingreso = models.DateTimeField(default=timezone.now, db_index=True)
    ultima_actividad = models.DateTimeField(default=timezone.now)
    salida = models.DateTimeField(null=True, blank=True, db_index=True)
    motivo_salida = models.CharField(
        max_length=20,
        choices=MOTIVO_SALIDA,
        blank=True,
    )
    direccion_ip = models.GenericIPAddressField(null=True, blank=True)
    navegador = models.CharField(max_length=255, blank=True)
    clave_sesion = models.CharField(max_length=40, blank=True, db_index=True)

    class Meta:
        ordering = ["-ingreso", "-id"]
        verbose_name = "sesión de acceso"
        verbose_name_plural = "sesiones de acceso"

    @property
    def abierta(self):
        return self.salida is None

    def __str__(self):
        nombre = self.usuario.get_username() if self.usuario else "Usuario eliminado"
        return f"{nombre} - {self.ingreso:%d/%m/%Y %H:%M}"
