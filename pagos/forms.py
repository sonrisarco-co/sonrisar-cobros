from django import forms
from .models import Pago, HoraExtraRecepcionista


class PagoForm(forms.ModelForm):

    class Meta:
        model = Pago

        fields = [
            "monto",
            "paciente",
            "concepto",
            "metodo",
        ]

        widgets = {

            "monto": forms.NumberInput(attrs={
                "class": "form-control",
                "placeholder": "0.00",
            }),

            "paciente": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Ej: Luis Hernández",
            }),

            "concepto": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Ej: Control / Ortodoncia / Limpieza",
            }),

            "metodo": forms.Select(attrs={
                "class": "form-control",
            }),
        }


class HoraExtraRecepcionistaForm(forms.ModelForm):
    modo = forms.ChoiceField(
        label="Forma de carga", choices=[("dia", "Un día"), ("rango", "Varios días · lunes a viernes")],
        initial="dia", required=False,
        widget=forms.Select(attrs={"class": "form-control"}))
    hasta = forms.DateField(
        label="Hasta (inclusive)", required=False,
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}))

    def clean(self):
        datos = super().clean()
        if datos.get("modo") == "rango":
            inicio, fin = datos.get("fecha"), datos.get("hasta")
            if not fin:
                self.add_error("hasta", "Selecciona la fecha final.")
            elif inicio and (fin < inicio or (fin - inicio).days > 30):
                self.add_error("hasta", "Elige un rango de hasta 31 días, posterior o igual al inicio.")
        return datos

    class Meta:
        model = HoraExtraRecepcionista
        fields = ["modo", "fecha", "hasta", "horas", "notas"]
        labels = {"fecha": "Fecha", "horas": "Horas extra por día", "notas": "Notas"}
        widgets = {
            "fecha": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "horas": forms.NumberInput(attrs={"min": "0.25", "step": "0.25", "class": "form-control", "placeholder": "Ej.: 1.5"}),
            "notas": forms.TextInput(attrs={"class": "form-control", "placeholder": "Opcional"}),
        }

    def clean_horas(self):
        horas = self.cleaned_data["horas"]
        if horas <= 0:
            raise forms.ValidationError("Ingresa una cantidad de horas mayor que cero.")
        return horas
