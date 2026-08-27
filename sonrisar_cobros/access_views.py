from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import user_passes_test
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from pagos.models import SesionAcceso
from .middleware import _client_ip


def home_redirect(request):
    return redirect("caja:tablero" if request.user.is_authenticated else "acceso_login")


@require_http_methods(["GET", "POST"])
def access_login(request):
    if request.user.is_authenticated:
        return redirect("caja:tablero")

    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        user = authenticate(request, username=username, password=password)
        if user is None:
            messages.error(request, "Usuario o contraseña incorrectos.")
        elif not user.is_active:
            messages.error(request, "Esta cuenta está deshabilitada.")
        else:
            ahora = timezone.now()
            SesionAcceso.objects.filter(
                usuario=user,
                salida__isnull=True,
            ).update(
                salida=ahora,
                motivo_salida="nueva_sesion",
            )
            login(request, user)
            acceso = SesionAcceso.objects.create(
                usuario=user,
                ingreso=ahora,
                ultima_actividad=ahora,
                direccion_ip=_client_ip(request),
                navegador=request.META.get("HTTP_USER_AGENT", "")[:255],
                clave_sesion=request.session.session_key or "",
            )
            request.session["sesion_acceso_id"] = acceso.id
            destino = request.POST.get("next") or request.GET.get("next")
            if not destino or not destino.startswith("/") or destino.startswith("//"):
                destino = reverse("caja:tablero")
            return redirect(destino)

    return render(request, "cuentas/login.html", {"next": request.GET.get("next", "")})


@require_POST
def access_logout(request):
    if request.user.is_authenticated:
        ahora = timezone.now()
        acceso_id = request.session.get("sesion_acceso_id")
        SesionAcceso.objects.filter(
            id=acceso_id,
            usuario=request.user,
            salida__isnull=True,
        ).update(
            salida=ahora,
            ultima_actividad=ahora,
            motivo_salida="manual",
        )
    logout(request)
    return redirect("acceso_login")


@user_passes_test(lambda user: user.is_active and user.is_staff)
def access_history(request):
    sesiones = SesionAcceso.objects.select_related("usuario").all()[:300]
    return render(request, "cuentas/historial.html", {"sesiones": sesiones})
