from datetime import timedelta

from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.cache import add_never_cache_headers

from pagos.models import SesionAcceso

from .live import LIVE_PAGES, PIN_ON_RELOAD, REVISION_ROUTE, current_revision


class AccessControlMiddleware:
    """Protege las pantallas y mantiene la última actividad del turno."""

    EXEMPT_PREFIXES = (
        "/cuenta/ingresar/",
        "/admin/",
        "/static/",
        "/pagos/api/",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.path.startswith(self.EXEMPT_PREFIXES) and not request.user.is_authenticated:
            login_url = reverse("acceso_login")
            return redirect(f"{login_url}?next={request.get_full_path()}")

        if (request.user.is_authenticated
                and not request.path.startswith("/admin/")
                and request.path != reverse(REVISION_ROUTE)):
            self._registrar_actividad(request)

        response = self.get_response(request)
        if hasattr(request, "cobros_live_revision"):
            add_never_cache_headers(response)
        return response

    def process_view(self, request, view_func, view_args, view_kwargs):
        view_name = request.resolver_match.view_name
        if request.method == "GET" and request.user.is_authenticated and view_name in LIVE_PAGES:
            # Capture the revision before the view reads the financial records.
            request.cobros_live_revision = current_revision()
            request.cobros_live_manual = view_name in PIN_ON_RELOAD

    @staticmethod
    def _registrar_actividad(request):
        ahora = timezone.now()
        acceso_id = request.session.get("sesion_acceso_id")
        acceso = SesionAcceso.objects.filter(
            id=acceso_id,
            usuario=request.user,
            salida__isnull=True,
        ).first()

        if not acceso:
            acceso = SesionAcceso.objects.create(
                usuario=request.user,
                ingreso=ahora,
                ultima_actividad=ahora,
                direccion_ip=_client_ip(request),
                navegador=request.META.get("HTTP_USER_AGENT", "")[:255],
                clave_sesion=request.session.session_key or "",
            )
            request.session["sesion_acceso_id"] = acceso.id
            return

        if ahora - acceso.ultima_actividad >= timedelta(minutes=2):
            SesionAcceso.objects.filter(id=acceso.id).update(ultima_actividad=ahora)


def _client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    return request.META.get("REMOTE_ADDR") or None
