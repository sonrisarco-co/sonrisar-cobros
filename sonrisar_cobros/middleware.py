from datetime import timedelta

from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone

from pagos.models import SesionAcceso


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

        if request.user.is_authenticated and not request.path.startswith("/admin/"):
            self._registrar_actividad(request)

        return self.get_response(request)

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
