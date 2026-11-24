from django import forms

from .models import RoleProfile, RoleSkill, Skill, SkillCategory, SkillLevel


class SkillCategoryForm(forms.ModelForm):
    class Meta:
        model = SkillCategory
        fields = ['name', 'description']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Programming Languages, Cloud, AI/ML'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Category scope and details'}),
        }


class SkillForm(forms.ModelForm):
    class Meta:
        model = Skill
        fields = ['name', 'category', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Python, PostgreSQL, Docker'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class RoleProfileForm(forms.ModelForm):
    class Meta:
        model = RoleProfile
        fields = ['name', 'description']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Backend Engineer, Data Analyst'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Role responsibilities and baseline competencies'}),
        }


class RoleSkillForm(forms.ModelForm):
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
        help_text='Importance weight from 1 (low) to 5 (critical)',
    )

    class Meta:
        model = RoleSkill
        fields = ['skill', 'required_level', 'weight']
        widgets = {
            'skill': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        role = kwargs.pop('role', None)
        super().__init__(*args, **kwargs)
        if role:
            # Exclude already assigned skills
            existing_skill_ids = role.role_skills.values_list('skill_id', flat=True)
            self.fields['skill'].queryset = Skill.objects.filter(is_active=True).exclude(id__in=existing_skill_ids)
        else:
            self.fields['skill'].queryset = Skill.objects.filter(is_active=True)
