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
    class Meta:
        model = HoraExtraRecepcionista
        fields = ["fecha", "horas", "notas"]
        labels = {"fecha": "Fecha", "horas": "Horas extra", "notas": "Notas"}
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
