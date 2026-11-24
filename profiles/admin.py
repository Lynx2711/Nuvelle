from django.contrib import admin

from .models import Certification, Project, StudentProfile, StudentSkill


class StudentSkillInline(admin.TabularInline):
    model = StudentSkill
    extra = 0
    autocomplete_fields = ['skill']


class ProjectInline(admin.TabularInline):
    model = Project
    extra = 0


class CertificationInline(admin.TabularInline):
    model = Certification
    extra = 0


@admin.register(StudentProfile)
class StudentProfileAdmin(admin.ModelAdmin):
    list_display = ('roll_no', 'user_email', 'institution', 'programme', 'batch', 'cgpa', 'completeness')
    list_filter = ('institution', 'programme', 'batch')
    search_fields = ('roll_no', 'user__email', 'user__first_name', 'user__last_name')
    inlines = [StudentSkillInline, ProjectInline, CertificationInline]

    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = 'Email'

    def completeness(self, obj):
        return f"{obj.completeness_percentage}%"
    completeness.short_description = 'Profile %'


@admin.register(StudentSkill)
class StudentSkillAdmin(admin.ModelAdmin):
    list_display = ('student', 'skill', 'level', 'status', 'verified_by', 'updated_at')
    list_filter = ('status', 'level', 'student__institution')
    search_fields = ('student__roll_no', 'student__user__email', 'skill__name')
