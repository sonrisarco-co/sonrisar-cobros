from django.urls import path
from . import views

app_name = "caja"

urlpatterns = [
    path("", views.tablero, name="tablero"),
    path("movimiento/nuevo/", views.movimiento_nuevo, name="movimiento_nuevo"),
    path("cerrar/", views.cerrar_caja, name="cerrar"),
    path("cerradas/", views.cajas_cerradas, name="cerradas"),
    path("saldo-inicial/", views.saldo_inicial, name="saldo_inicial"),

]
