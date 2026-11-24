from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError

from skills.models import Skill, SkillLevel

from .models import Certification, Project, StudentProfile, StudentSkill


class StudentCSVImportForm(forms.Form):
    csv_file = forms.FileField(
        label='Select CSV File',
        help_text='Required columns: roll_no, name, email, programme, batch, cgpa. Max size: 5 MB.',
        widget=forms.FileInput(attrs={'class': 'form-control', 'accept': '.csv'}),
    )

    def clean_csv_file(self):
        file = self.cleaned_data.get('csv_file')
        if not file:
            raise ValidationError('Please choose a file to upload.')

        if not file.name.lower().endswith('.csv'):
            raise ValidationError('Uploaded file must have a .csv extension.')

        max_size = getattr(settings, 'MAX_UPLOAD_SIZE_CSV', 5 * 1024 * 1024)
        if file.size > max_size:
            raise ValidationError(f'File size exceeds limit of {max_size // (1024 * 1024)} MB.')

        return file


class StudentProfileForm(forms.ModelForm):
    class Meta:
        model = StudentProfile
        fields = ['programme', 'batch', 'graduation_year', 'cgpa', 'resume_file']
        widgets = {
            'programme': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. B.Tech Computer Science'}),
            'batch': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. 2026'}),
            'graduation_year': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'e.g. 2026'}),
            'cgpa': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0.00', 'max': '10.00', 'placeholder': 'e.g. 8.75'}),
            'resume_file': forms.FileInput(attrs={'class': 'form-control', 'accept': '.pdf'}),
        }
        help_texts = {
            'resume_file': 'Upload PDF resume (Maximum size: 2 MB).',
            'cgpa': 'Cumulative Grade Point Average on a 10.0 scale.',
        }

    def clean_resume_file(self):
        resume = self.cleaned_data.get('resume_file')
        if resume:
            # Check file extension
            if not resume.name.lower().endswith('.pdf'):
                raise ValidationError('Resume must be a PDF document (.pdf).')

            # Check file size limit: 2 MB
            max_size = getattr(settings, 'MAX_UPLOAD_SIZE_RESUME', 2 * 1024 * 1024)
            if resume.size > max_size:
                raise ValidationError(f'Resume file size ({resume.size // 1024} KB) exceeds the 2 MB limit.')

        return resume


class StudentSkillForm(forms.ModelForm):
    level = forms.ChoiceField(
        choices=SkillLevel.choices,
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text='1 Beginner, 2 Intermediate, 3 Advanced, 4 Expert',
    )

    class Meta:
        model = StudentSkill
        fields = ['skill', 'level']
        widgets = {
            'skill': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        student = kwargs.pop('student', None)
        super().__init__(*args, **kwargs)
        if student and not self.instance.pk:
            # Exclude skills the student already claimed
            existing_skill_ids = student.skills.values_list('skill_id', flat=True)
            self.fields['skill'].queryset = Skill.objects.filter(is_active=True).exclude(id__in=existing_skill_ids)
        elif self.instance.pk:
            # If editing, skill is fixed
            self.fields['skill'].disabled = True
        else:
            self.fields['skill'].queryset = Skill.objects.filter(is_active=True)


class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = ['title', 'description', 'link']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Real-Time Chat Engine'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Brief description of architecture, stack, and results'}),
            'link': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://github.com/username/project'}),
        }


class CertificationForm(forms.ModelForm):
    issued_on = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
    )

    class Meta:
        model = Certification
        fields = ['name', 'issuer', 'issued_on', 'credential_url']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. AWS Certified Solutions Architect'}),
            'issuer': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Amazon Web Services'}),
            'credential_url': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://credly.com/badges/...'}),
        }


class SkillRejectForm(forms.Form):
    rejection_reason = forms.CharField(
        required=True,
        widget=forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Mandatory reason for rejection...'}),
    )


class SkillAdjustLevelForm(forms.Form):
    adjusted_level = forms.ChoiceField(
        choices=SkillLevel.choices,
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'}),
    )
