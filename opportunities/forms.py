from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from skills.models import Skill, SkillLevel

from .models import Opportunity, OpportunitySkill


class OpportunityForm(forms.ModelForm):
    deadline = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
        help_text='Deadline for students to apply.',
    )

    class Meta:
        model = Opportunity
        fields = [
            'title',
            'type',
            'mode',
            'location',
            'openings',
            'pay_min',
            'pay_max',
            'deadline',
            'min_cgpa',
            'programme',
            'batch',
            'description',
        ]
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Software Engineer Intern'}),
            'type': forms.Select(attrs={'class': 'form-select'}),
            'mode': forms.Select(attrs={'class': 'form-select'}),
            'location': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Bengaluru, Remote'}),
            'openings': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'pay_min': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Min (INR)'}),
            'pay_max': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Max (INR)'}),
            'min_cgpa': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0.00', 'max': '10.00', 'placeholder': 'e.g. 7.50'}),
            'programme': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. B.Tech Computer Science (leave empty for all)'}),
            'batch': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. 2026 (leave empty for all)'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 5, 'placeholder': 'Role responsibilities, team details, and qualifications...'}),
        }

    def clean_deadline(self):
        deadline = self.cleaned_data.get('deadline')
        if deadline and deadline <= timezone.now():
            raise ValidationError('Deadline must be set to a future date and time.')
        return deadline

    def clean(self):
        cleaned_data = super().clean()
        pay_min = cleaned_data.get('pay_min')
        pay_max = cleaned_data.get('pay_max')

        if pay_min and pay_max and pay_min > pay_max:
            self.add_error('pay_max', 'Maximum pay cannot be less than minimum pay.')

        return cleaned_data


class OpportunitySkillForm(forms.ModelForm):
    required_level = forms.ChoiceField(
        choices=SkillLevel.choices,
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text='1 Beginner, 2 Intermediate, 3 Advanced, 4 Expert',
    )
    weight = forms.IntegerField(
        min_value=1,
        max_value=5,
        initial=1,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 5}),
        help_text='Skill importance weight from 1 (low) to 5 (critical)',
    )

    class Meta:
        model = OpportunitySkill
        fields = ['skill', 'required_level', 'weight']
        widgets = {
            'skill': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        opportunity = kwargs.pop('opportunity', None)
        super().__init__(*args, **kwargs)
        if opportunity:
            existing_skill_ids = opportunity.required_skills.values_list('skill_id', flat=True)
            self.fields['skill'].queryset = Skill.objects.filter(is_active=True).exclude(id__in=existing_skill_ids)
        else:
            self.fields['skill'].queryset = Skill.objects.filter(is_active=True)
