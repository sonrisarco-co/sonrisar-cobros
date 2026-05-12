from django import forms
from .models import Pago


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