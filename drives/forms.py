from django import forms

from opportunities.models import Opportunity, OpportunityStatus
from orgs.models import Institution

from .models import DriveRound, Offer, PlacementDrive


class PlacementDriveForm(forms.ModelForm):
    drive_date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        help_text="Scheduled date for on-campus/virtual drive",
    )

    class Meta:
        model = PlacementDrive
        fields = ['opportunity', 'institution', 'drive_date', 'venue', 'rules', 'status']
        widgets = {
            'opportunity': forms.Select(attrs={'class': 'form-select'}),
            'institution': forms.Select(attrs={'class': 'form-select'}),
            'venue': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Auditorium / Lab 3 / Microsoft Teams'}),
            'rules': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Specific eligibility, guidelines, and dress code'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        # Restrict opportunity choices depending on user
        if user and user.role == 'recruiter' and user.company:
            self.fields['opportunity'].queryset = Opportunity.objects.filter(
                company=user.company,
                status=OpportunityStatus.PUBLISHED,
            )
        else:
            self.fields['opportunity'].queryset = Opportunity.objects.filter(
                status=OpportunityStatus.PUBLISHED,
            )

        self.fields['institution'].queryset = Institution.objects.filter(is_approved=True)


class DriveRoundForm(forms.ModelForm):
    round_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
    )

    class Meta:
        model = DriveRound
        fields = ['name', 'sequence', 'round_date', 'description', 'is_completed']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Online Coding Assessment'}),
            'sequence': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 10}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Evaluation criteria'}),
            'is_completed': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class OfferForm(forms.ModelForm):
    offered_on = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
    )

    class Meta:
        model = Offer
        fields = ['package', 'offered_on', 'notes']
        widgets = {
            'package': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'e.g. 1200000', 'step': '1000'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Designation, joining terms, stipends'}),
        }
