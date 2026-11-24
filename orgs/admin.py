from django.contrib import admin

from .models import Company, Institution


@admin.action(description='Approve selected institutions')
def approve_institutions(modeladmin, request, queryset):
    queryset.update(is_approved=True)


@admin.action(description='Reject/Unapprove selected institutions')
def unapprove_institutions(modeladmin, request, queryset):
    queryset.update(is_approved=False)


@admin.action(description='Approve selected companies')
def approve_companies(modeladmin, request, queryset):
    queryset.update(is_approved=True)


@admin.action(description='Reject/Unapprove selected companies')
def unapprove_companies(modeladmin, request, queryset):
    queryset.update(is_approved=False)


@admin.register(Institution)
class InstitutionAdmin(admin.ModelAdmin):
    list_display = ('name', 'city', 'is_approved', 'created_at')
    list_filter = ('is_approved', 'city')
    search_fields = ('name', 'city')
    actions = [approve_institutions, unapprove_institutions]


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ('name', 'industry', 'website', 'is_approved', 'created_at')
    list_filter = ('is_approved', 'industry')
    search_fields = ('name', 'industry')
    actions = [approve_companies, unapprove_companies]
