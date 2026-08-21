import json
import urllib.error
import urllib.request
import uuid

from django.conf import settings
from django.utils import timezone


class FactureError(Exception):
    pass


# =========================================================
# CONFIGURACIÓN
# =========================================================

def _config():
    return {
        "api_url": getattr(settings, "FACTURE_API_URL", "").rstrip("/"),
        "api_key": getattr(settings, "FACTURE_API_KEY", ""),
        "empresa_id": getattr(settings, "FACTURE_EMPRESA_ID", ""),
        "cod_comercio": getattr(settings, "FACTURE_COD_COMERCIO", ""),
        "cod_terminal": getattr(settings, "FACTURE_COD_TERMINAL", ""),
        "modo": getattr(settings, "FACTURE_MODO", "sandbox"),
        "envio_habilitado": getattr(
            settings,
            "FACTURE_ENVIO_HABILITADO",
            False,
        ),
    }


def configuracion_publica():
    """
    Devuelve únicamente información segura para diagnóstico.
    Nunca expone la API key.
    """
    cfg = _config()

    return {
        "api_url": cfg["api_url"],
        "empresa_id": cfg["empresa_id"],
        "cod_comercio": cfg["cod_comercio"],
        "cod_terminal": cfg["cod_terminal"],
        "modo": cfg["modo"],
        "envio_habilitado": cfg["envio_habilitado"],
        "api_key_configurada": bool(cfg["api_key"]),
    }


def _validar_conexion():
    cfg = _config()

    if not cfg["api_url"]:
        raise FactureError("Falta FACTURE_API_URL.")

    if not cfg["api_key"]:
        raise FactureError("Falta FACTURE_API_KEY.")

    if cfg["modo"] not in {"sandbox", "produccion"}:
        raise FactureError(
            "FACTURE_MODO debe ser 'sandbox' o 'produccion'."
        )

    return cfg


def _validar_configuracion_basica():
    cfg = _validar_conexion()

    if not cfg["empresa_id"]:
        raise FactureError("Falta FACTURE_EMPRESA_ID.")

    if not cfg["cod_comercio"]:
        raise FactureError("Falta FACTURE_COD_COMERCIO.")

    if not cfg["cod_terminal"]:
        raise FactureError("Falta FACTURE_COD_TERMINAL.")

    return cfg


# =========================================================
# HTTP / API
# =========================================================

def _request_json(method, path, payload=None, timeout=15):
    cfg = _validar_conexion()

    url = f'{cfg["api_url"]}/{path.lstrip("/")}'
    data = None

    if payload is not None:
        data = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=data,
        method=method.upper(),
        headers={
            "Authorization": f'Bearer {cfg["api_key"]}',
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "curl/8.0 SonrisarCobros/1.0",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read().decode(
                "utf-8",
                errors="replace",
            )

            try:
                body = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                body = {"raw": raw}

            return {
                "ok": True,
                "status": response.status,
                "data": body,
            }

    except urllib.error.HTTPError as exc:
        raw = exc.read().decode(
            "utf-8",
            errors="replace",
        )

        try:
            body = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            body = {"raw": raw}

        return {
            "ok": False,
            "status": exc.code,
            "error": body,
        }

    except urllib.error.URLError as exc:
        raise FactureError(
            f"No se pudo conectar con Facture: {exc.reason}"
        ) from exc


# =========================================================
# PRUEBA DE CONEXIÓN
# =========================================================

def probar_conexion():
    """
    Prueba autenticación contra Facture consultando las
    empresas disponibles para la credencial configurada.

    NO emite ningún CFE.
    Funciona tanto en sandbox como en producción.
    """
    resultado = _request_json(
        "GET",
        "/api/v1/usuario/empresas",
    )

    resultado["config"] = configuracion_publica()

    return resultado


# =========================================================
# EMISIÓN GENÉRICA
# =========================================================

def emitir_cfe(payload):
    """
    Envía un comprobante a Facture.

    Protección principal:
    mientras FACTURE_ENVIO_HABILITADO=False,
    ningún CFE puede ser emitido.
    """
    cfg = _validar_configuracion_basica()

    if not cfg["envio_habilitado"]:
        raise FactureError(
            "Emisión deshabilitada. "
            "Primero validar la conexión con Facture y luego activar "
            "FACTURE_ENVIO_HABILITADO de forma explícita."
        )

    return _request_json(
        "POST",
        "/api/v1/comprobante/emitir",
        payload=payload,
        timeout=30,
    )


# =========================================================
# MEDIOS DE PAGO
# =========================================================

def _medio_pago_facture(pago):
    metodo = (
        getattr(pago, "metodo", "")
        or ""
    ).strip().lower()

    tipo_tarjeta = (
        getattr(pago, "tipo_tarjeta", "")
        or ""
    ).strip().lower()

    if metodo == "efectivo":
        return 1, "Efectivo"

    if metodo == "tarjeta":
        if tipo_tarjeta == "debito":
            return 2, "Débito"

        if tipo_tarjeta == "credito":
            return 2, "Crédito"

        return 2, "Tarjeta"

    if metodo == "transferencia":
        return 3, "Transferencia"

    raise FactureError(
        f"Medio de pago no soportado para CFE: "
        f"{metodo or 'vacío'}"
    )


# =========================================================
# ETICKET - CFE 101
# =========================================================

def construir_payload_eticket(pago):
    """
    Construye el eTicket de Sonrisar.

    CFE 101 = eTicket
    montoBruto 1 = importe con IVA incluido
    indicadorFacturacion 2 = IVA tasa mínima (10 %)
    formaPago 1 = Contado
    moneda = UYU
    """
    cfg = _validar_configuracion_basica()

    fecha_emision = timezone.localdate()
    monto = float(pago.monto)

    id_medio_pago, glosa_medio_pago = (
        _medio_pago_facture(pago)
    )

    identificador = (
        f"sonrisar-cobros-"
        f"{cfg['modo']}-"
        f"eticket-pago-{pago.id}"
    )

    return {
        "idEmpresa": cfg["empresa_id"],
        "codComercio": cfg["cod_comercio"],
        "codTerminal": cfg["cod_terminal"],
        "uuid": str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                identificador,
            )
        ),
        "origen": "Api",
        "registrarComprobanteInterno": False,
        "cfe": {
            "idDoc": {
                "tipoCfe": 101,
                "fechaEmision": fecha_emision.isoformat(),
                "montoBruto": 1,
                "formaPago": 1,
            },
            "detalles": [
                {
                    "numeroLineaDetalle": 1,
                    "indicadorFacturacion": 2,
                    "nombreItem": (
                        pago.concepto
                        or "Servicio odontológico"
                    ),
                    "cantidad": 1,
                    "unidadMedida": "N/A",
                    "precioUnitario": monto,
                    "montoItem": monto,
                }
            ],
            "mediosPago": [
                {
                    "numeroLineaMedioPago": 1,
                    "idMedioPago": id_medio_pago,
                    "idCuentaBanco": 0,
                    "glosaMedioPago": glosa_medio_pago,
                    "ordenMedioPago": 1,
                    "tipoMonedaMedioPago": "UYU",
                    "tipoCambioMedioPago": 1,
                    "valorPago": monto,
                    "titular": 0,
                    "nomDoc": "",
                    "proveedorPos": 0,
                }
            ],
            "complementoFiscal": {},
        },
    }


def emitir_pago(pago):
    """
    Emite un eTicket para el pago indicado.

    Funciona tanto en sandbox como en producción.
    La emisión real sigue dependiendo de
    FACTURE_ENVIO_HABILITADO.
    """
    payload = construir_payload_eticket(pago)
    return emitir_cfe(payload)


# =========================================================
# NOTA DE CRÉDITO - CFE 102
# =========================================================

def construir_payload_nota_credito_eticket(
    pago,
    razon="Anulación de eTicket",
):
    """
    Construye una Nota de Crédito de eTicket
    para anular TOTALMENTE el CFE original.
    """
    cfg = _validar_configuracion_basica()

    if not getattr(pago, "cfe_serie", ""):
        raise FactureError(
            "El pago no tiene serie del eTicket original."
        )

    if not getattr(pago, "cfe_numero", ""):
        raise FactureError(
            "El pago no tiene número del eTicket original."
        )

    try:
        numero_original = int(pago.cfe_numero)
    except (TypeError, ValueError) as exc:
        raise FactureError(
            f"Número de CFE original inválido: "
            f"{pago.cfe_numero!r}"
        ) from exc

    monto = float(pago.monto)

    fecha_emision_nc = timezone.localdate()

    # Para los CFE nuevos usamos la fecha fiscal real guardada.
    # El fallback permite seguir trabajando con CFE antiguos
    # de sandbox emitidos antes de existir este campo.
    fecha_original = (
        getattr(pago, "cfe_fecha_emision", None)
        or pago.fecha.date()
    )

    identificador = (
        f"sonrisar-cobros-"
        f"{cfg['modo']}-"
        f"nota-credito-pago-{pago.id}"
    )

    return {
        "idEmpresa": cfg["empresa_id"],
        "codComercio": cfg["cod_comercio"],
        "codTerminal": cfg["cod_terminal"],
        "uuid": str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                identificador,
            )
        ),
        "origen": "Api",
        "registrarComprobanteInterno": False,
        "cfe": {
            "idDoc": {
                "tipoCfe": 102,
                "fechaEmision": (
                    fecha_emision_nc.isoformat()
                ),
                "montoBruto": 1,
                "formaPago": 1,
            },
            "detalles": [
                {
                    "numeroLineaDetalle": 1,
                    "indicadorFacturacion": 2,
                    "nombreItem": (
                        pago.concepto
                        or "Servicio odontológico"
                    ),
                    "cantidad": 1,
                    "unidadMedida": "N/A",
                    "precioUnitario": monto,
                    "montoItem": monto,
                }
            ],
            "referencias": [
                {
                    "numeroLineaReferencia": 1,
                    "tipoDocumentoReferencia": 101,
                    "serieFacturaReferencia": str(
                        pago.cfe_serie
                    ),
                    "numeroFacturaReferencia": (
                        numero_original
                    ),
                    "fechaFacturaReferencia": (
                        fecha_original.isoformat()
                    ),
                    "tipoMonedaCfeReferencia": "UYU",
                    "razonReferencia": razon,
                }
            ],
            "complementoFiscal": {},
        },
    }


def emitir_nota_credito_pago(
    pago,
    razon="Anulación de eTicket",
):
    """
    Emite una Nota de Crédito CFE 102 para
    anular totalmente el eTicket original.

    Funciona en sandbox y producción.
    """
    payload = construir_payload_nota_credito_eticket(
        pago,
        razon=razon,
    )

    return emitir_cfe(payload)


# =========================================================
# COMPATIBILIDAD TEMPORAL
# =========================================================
# Estas funciones se mantienen por ahora porque views.py
# todavía utiliza los nombres antiguos.
# Las eliminaremos cuando adaptemos las vistas.

def construir_payload_eticket_sandbox(pago):
    return construir_payload_eticket(pago)


def emitir_pago_sandbox(pago):
    return emitir_pago(pago)


def construir_payload_nota_credito_eticket_sandbox(
    pago,
    razon="Anulación de eTicket",
):
    return construir_payload_nota_credito_eticket(
        pago,
        razon=razon,
    )


def emitir_nota_credito_pago_sandbox(
    pago,
    razon="Anulación de eTicket",
):
    return emitir_nota_credito_pago(
        pago,
        razon=razon,
    )


# =========================================================
# PDF DE CFE
# =========================================================

def obtener_pdf_cfe_por_folio(
    tipo_cfe,
    serie,
    numero,
):
    """
    Obtiene desde Facture el PDF de un CFE ya emitido.
    No genera un comprobante nuevo.
    """
    cfg = _validar_configuracion_basica()

    url = (
        f'{cfg["api_url"]}'
        f'/api/v1/cfeemitido/pdf'
    )

    payload = {
        "tipo_cfe": int(tipo_cfe),
        "serie": str(serie),
        "numero": int(numero),
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "x-api-key": cfg["api_key"],
            "Content-Type": "application/json",
            "Accept": "application/pdf",
            "User-Agent": "curl/8.0 SonrisarCobros/1.0",
        },
    )

    try:
        with urllib.request.urlopen(
            req,
            timeout=30,
        ) as response:
            return {
                "ok": True,
                "status": response.status,
                "content_type": response.headers.get(
                    "Content-Type",
                    "",
                ),
                "content": response.read(),
            }

    except urllib.error.HTTPError as exc:
        raw = exc.read().decode(
            "utf-8",
            errors="replace",
        )

        try:
            body = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            body = {"raw": raw}

        return {
            "ok": False,
            "status": exc.code,
            "error": body,
        }

    except urllib.error.URLError as exc:
        raise FactureError(
            "No se pudo obtener el PDF desde Facture: "
            f"{exc.reason}"
        ) from exc