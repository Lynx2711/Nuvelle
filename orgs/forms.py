from django import forms

from .models import Company, Institution


class InstitutionForm(forms.ModelForm):
    class Meta:
        model = Institution
        fields = ['name', 'city', 'is_approved']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. National Institute of Technology'}),
            'city': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Bengaluru'}),
            'is_approved': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class CompanyForm(forms.ModelForm):
    class Meta:
        model = Company
        fields = ['name', 'website', 'industry', 'is_approved']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Acme Innovations'}),
            'website': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://example.com'}),
            'industry': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Fintech, Healthcare'}),
            'is_approved': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
