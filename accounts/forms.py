from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from orgs.models import Company, Institution

from .models import UserRole

User = get_user_model()


class RegistrationForm(forms.ModelForm):
    first_name = forms.CharField(max_length=100, required=True, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'First Name'}))
    last_name = forms.CharField(max_length=100, required=True, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Last Name'}))
    email = forms.EmailField(required=True, widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'name@example.com'}))

    role = forms.ChoiceField(
        choices=[
            (UserRole.STUDENT, 'Student'),
            (UserRole.FACULTY, 'Faculty (Mentor)'),
            (UserRole.RECRUITER, 'Recruiter'),
            (UserRole.OFFICER, 'Placement Officer'),
        ],
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'id_role'}),
    )

    institution = forms.ModelChoiceField(
        queryset=Institution.objects.filter(is_approved=True),
        required=False,
        empty_label='-- Select Institution --',
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'id_institution'}),
        help_text='Required for students, faculty, and placement officers.',
    )

    company = forms.ModelChoiceField(
        queryset=Company.objects.all(),
        required=False,
        empty_label='-- Select Company --',
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'id_company'}),
        help_text='Required for recruiters.',
    )

    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Minimum 8 characters with letter & digit'}),
        help_text='Must be at least 8 characters long and contain both letters and numbers.',
    )
    confirm_password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Re-enter password'}),
    )

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'role', 'institution', 'company']

    def clean_email(self):
        email = self.cleaned_data.get('email', '').strip().lower()
        if User.objects.filter(email=email).exists():
            raise ValidationError('A user with this email address already exists.')
        return email

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        confirm_password = cleaned_data.get('confirm_password')
        role = cleaned_data.get('role')
        institution = cleaned_data.get('institution')
        company = cleaned_data.get('company')

        if password and confirm_password:
            if password != confirm_password:
                self.add_error('confirm_password', 'Passwords do not match.')
            else:
                try:
                    validate_password(password)
                except ValidationError as e:
                    self.add_error('password', e)

        # Role-based association validation
        if role in [UserRole.STUDENT, UserRole.FACULTY, UserRole.OFFICER]:
            if not institution and Institution.objects.filter(is_approved=True).exists():
                self.add_error('institution', 'Please select your institution.')
            cleaned_data['company'] = None
        elif role == UserRole.RECRUITER:
            if not company and Company.objects.exists():
                self.add_error('company', 'Please select your company.')
            cleaned_data['institution'] = None

        return cleaned_data


class LoginForm(forms.Form):
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'name@example.com', 'autocomplete': 'email'})
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Password', 'autocomplete': 'current-password'})
    )


class PasswordResetRequestForm(forms.Form):
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'name@example.com'})
    )


class SetNewPasswordForm(forms.Form):
    new_password1 = forms.CharField(
        label='New Password',
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'New password'}),
        help_text='Must be at least 8 characters long and contain both letters and numbers.',
    )
    new_password2 = forms.CharField(
        label='Confirm New Password',
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Confirm new password'}),
    )

    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get('new_password1')
        p2 = cleaned_data.get('new_password2')
        if p1 and p2:
            if p1 != p2:
                self.add_error('new_password2', 'Passwords do not match.')
            else:
                try:
                    validate_password(p1)
                except ValidationError as e:
                    self.add_error('new_password1', e)
        return cleaned_data


class ResendVerificationForm(forms.Form):
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'name@example.com'})
    )
