import json
import urllib.error
import urllib.request
import uuid

from django.conf import settings
from django.utils import timezone


class FactureError(Exception):
    pass


def _config():
    return {
        "api_url": getattr(settings, "FACTURE_API_URL", "").rstrip("/"),
        "api_key": getattr(settings, "FACTURE_API_KEY", ""),
        "empresa_id": getattr(settings, "FACTURE_EMPRESA_ID", ""),
        "cod_comercio": getattr(settings, "FACTURE_COD_COMERCIO", ""),
        "cod_terminal": getattr(settings, "FACTURE_COD_TERMINAL", ""),
        "modo": getattr(settings, "FACTURE_MODO", "sandbox"),
        "envio_habilitado": getattr(settings, "FACTURE_ENVIO_HABILITADO", False),
    }


def configuracion_publica():
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


def _request_json(method, path, payload=None, timeout=15):
    cfg = _config()

    if not cfg["api_url"]:
        raise FactureError("Falta FACTURE_API_URL.")
    if not cfg["api_key"]:
        raise FactureError("Falta FACTURE_API_KEY.")

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
            raw = response.read().decode("utf-8", errors="replace")
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
        raw = exc.read().decode("utf-8", errors="replace")
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
        raise FactureError(f"No se pudo conectar con Facture: {exc.reason}") from exc


def probar_conexion():
    """
    Prueba autenticación contra el sandbox consultando las empresas
    disponibles para la credencial actual. NO emite ningún CFE.
    """
    resultado = _request_json("GET", "/api/v1/usuario/empresas")
    resultado["config"] = configuracion_publica()
    return resultado


def emitir_cfe(payload):
    """
    Preparado para la próxima etapa.
    Por seguridad no permite emitir mientras FACTURE_ENVIO_HABILITADO=False.
    """
    cfg = _config()

    if not cfg["envio_habilitado"]:
        raise FactureError(
            "Emisión deshabilitada. Primero validar conexión y luego activar "
            "FACTURE_ENVIO_HABILITADO de forma explícita."
        )

    return _request_json(
        "POST",
        "/api/v1/comprobante/emitir",
        payload=payload,
        timeout=30,
    )


def construir_payload_eticket_sandbox(pago):
    """
    Construye un eTicket contado de prueba para Facture sandbox.
    - tipoCfe 101 = eTicket
    - montoBruto 1 = precio con IVA incluido
    - indicadorFacturacion 2 = IVA tasa mínima
    - formaPago 1 = Contado
    - mediosPago estándar Facture:
      1 = Efectivo, 2 = Tarjeta, 3 = Transferencia.
      Débito y Crédito de Sonrisar se informan como Tarjeta (idMedioPago=2).
    """
    cfg = _config()

    fecha_emision = pago.fecha.date().isoformat()
    monto = float(pago.monto)

    metodo = (getattr(pago, "metodo", "") or "").strip().lower()
    tipo_tarjeta = (getattr(pago, "tipo_tarjeta", "") or "").strip().lower()

    if metodo == "efectivo":
        id_medio_pago = 1
        glosa_medio_pago = "Efectivo"
    elif metodo == "tarjeta":
        id_medio_pago = 2
        if tipo_tarjeta == "debito":
            glosa_medio_pago = "Débito"
        elif tipo_tarjeta == "credito":
            glosa_medio_pago = "Crédito"
        else:
            glosa_medio_pago = "Tarjeta"
    elif metodo == "transferencia":
        id_medio_pago = 3
        glosa_medio_pago = "Transferencia"
    else:
        raise FactureError(
            f"Medio de pago no soportado para CFE: {metodo or 'vacío'}"
        )

    return {
        "idEmpresa": cfg["empresa_id"],
        "codComercio": cfg["cod_comercio"],
        "codTerminal": cfg["cod_terminal"],
        "uuid": str(uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"sonrisar-cobros-sandbox-pago-{pago.id}"
        )),
        "origen": "Api",
        "registrarComprobanteInterno": False,
        "cfe": {
            "idDoc": {
                "tipoCfe": 101,
                "fechaEmision": fecha_emision,
                "montoBruto": 1,
                "formaPago": 1,
            },
            "detalles": [
                {
                    "numeroLineaDetalle": 1,
                    "indicadorFacturacion": 2,
                    "nombreItem": pago.concepto or "Servicio odontológico",
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


def emitir_pago_sandbox(pago):
    cfg = _config()

    if cfg["modo"] != "sandbox":
        raise FactureError("Esta función solo puede usarse en sandbox.")

    payload = construir_payload_eticket_sandbox(pago)
    return emitir_cfe(payload)


def construir_payload_nota_credito_eticket_sandbox(
    pago,
    razon="Anulación de eTicket",
):
    """
    Construye una Nota de Crédito de eTicket (tipo CFE 102) para sandbox,
    referenciando el eTicket original asociado al pago.

    Esta primera versión está pensada para una anulación TOTAL:
    - mismo importe que el eTicket original
    - IVA tasa mínima
    - referencia al tipo 101, serie y número originales
    """
    cfg = _config()

    if not getattr(pago, "cfe_serie", "") or not getattr(pago, "cfe_numero", ""):
        raise FactureError(
            "El pago no tiene serie/número del eTicket original para referenciar."
        )

    monto = float(pago.monto)
    fecha_emision = timezone.localdate().isoformat()

    try:
        numero_original = int(pago.cfe_numero)
    except (TypeError, ValueError) as exc:
        raise FactureError(
            f"Número de CFE original inválido: {pago.cfe_numero!r}"
        ) from exc

    # La fecha del CFE original coincide con la fecha usada al emitir el pago.
    fecha_original = pago.fecha.date().isoformat()

    return {
        "idEmpresa": cfg["empresa_id"],
        "codComercio": cfg["cod_comercio"],
        "codTerminal": cfg["cod_terminal"],
        "uuid": str(uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"sonrisar-cobros-sandbox-nc-pago-{pago.id}"
        )),
        "origen": "Api",
        "registrarComprobanteInterno": False,
        "cfe": {
            "idDoc": {
                "tipoCfe": 102,
                "fechaEmision": fecha_emision,
                "montoBruto": 1,
                "formaPago": 1,
            },
            "detalles": [
                {
                    "numeroLineaDetalle": 1,
                    "indicadorFacturacion": 2,
                    "nombreItem": pago.concepto or "Servicio odontológico",
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
                    "serieFacturaReferencia": str(pago.cfe_serie),
                    "numeroFacturaReferencia": numero_original,
                    "fechaFacturaReferencia": fecha_original,
                    "tipoMonedaCfeReferencia": "UYU",
                    "razonReferencia": razon,
                }
            ],
            "complementoFiscal": {},
        },
    }


def emitir_nota_credito_pago_sandbox(
    pago,
    razon="Anulación de eTicket",
):
    """
    Emite en sandbox una Nota de Crédito de eTicket (CFE 102)
    que anula totalmente el CFE original del pago.
    """
    cfg = _config()

    if cfg["modo"] != "sandbox":
        raise FactureError("Esta función solo puede usarse en sandbox.")

    payload = construir_payload_nota_credito_eticket_sandbox(
        pago,
        razon=razon,
    )
    return emitir_cfe(payload)


def obtener_pdf_cfe_por_folio(tipo_cfe, serie, numero):
    """Obtiene el PDF de un CFE ya emitido desde Facture."""
    cfg = _config()

    if not cfg["api_url"]:
        raise FactureError("Falta FACTURE_API_URL.")
    if not cfg["api_key"]:
        raise FactureError("Falta FACTURE_API_KEY.")

    url = f'{cfg["api_url"]}/api/v1/cfeemitido/pdf'
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
        with urllib.request.urlopen(req, timeout=30) as response:
            return {
                "ok": True,
                "status": response.status,
                "content_type": response.headers.get("Content-Type", ""),
                "content": response.read(),
            }
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            body = {"raw": raw}
        return {"ok": False, "status": exc.code, "error": body}
    except urllib.error.URLError as exc:
        raise FactureError(f"No se pudo obtener el PDF desde Facture: {exc.reason}") from exc
