from hashlib import sha256

from django.db import connection
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from caja.models import ArqueoCaja, CashSession, MovimientoCaja
from pagos.models import (
    CompraProveedor,
    DevolucionPaciente,
    Gasto,
    HoraExtraRecepcionista,
    LiquidacionRecepcionista,
    Pago,
    PagoCompraProveedor,
    PagoExtrasRecepcionista,
    Recepcionista,
)


REVISION_ROUTE = "cobros_live_revision"
LIVE_PAGES = {
    "caja:tablero",
    "caja:arqueo",
    "caja:historial_arqueos",
    "caja:cerradas",
    "caja:movimientos_financieros",
    "pagos:historial",
    "pagos:lista_gastos",
    "pagos:compras_proveedores",
    "pagos:compra_proveedor_detalle",
    "pagos:horas_recepcionista",
    "reportes:reporte_mensual",
}
# These views consume a one-use PIN grant when opening the page.
PIN_ON_RELOAD = {"caja:cerradas", "caja:movimientos_financieros", "caja:historial_arqueos"}
LIVE_MODELS = (
    ArqueoCaja, CashSession, MovimientoCaja, CompraProveedor, DevolucionPaciente,
    Gasto, HoraExtraRecepcionista, LiquidacionRecepcionista, Pago,
    PagoCompraProveedor, PagoExtrasRecepcionista, Recepcionista,
)


def current_revision():
    digest = sha256()
    if connection.vendor == "postgresql":
        # MVCC row versions cover inserts, edits and deletes, including writes
        # from Pro, without locking or transferring any financial records.
        queries = []
        for model in LIVE_MODELS:
            table = connection.ops.quote_name(model._meta.db_table)
            queries.append(
                f"SELECT md5(string_agg(id::text || ':' || xmin::text, ',' ORDER BY id)) FROM {table}"
            )
        with connection.cursor() as cursor:
            cursor.execute("SELECT " + ", ".join(f"({query})" for query in queries))
            digest.update(repr(cursor.fetchone()).encode())
    else:
        for model in LIVE_MODELS:
            digest.update(model._meta.label.encode())
            for row in model.objects.order_by("pk").values_list().iterator():
                digest.update(repr(row).encode())
    return digest.hexdigest()


@never_cache
@require_GET
def revision(request):
    return JsonResponse({"revision": current_revision()})
