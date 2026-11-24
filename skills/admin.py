from django.contrib import admin

from .models import RoleProfile, RoleSkill, Skill, SkillCategory


class RoleSkillInline(admin.TabularInline):
    model = RoleSkill
    extra = 1
    autocomplete_fields = ['skill']


@admin.register(SkillCategory)
class SkillCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'skill_count', 'created_at')
    search_fields = ('name',)

    def skill_count(self, obj):
        return obj.skills.count()
    skill_count.short_description = 'Skills'


@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'is_active', 'created_at')
    list_filter = ('category', 'is_active')
    search_fields = ('name',)
    list_editable = ('is_active',)


@admin.register(RoleProfile)
class RoleProfileAdmin(admin.ModelAdmin):
    list_display = ('name', 'required_skills_count', 'created_at')
    search_fields = ('name', 'description')
    inlines = [RoleSkillInline]

    def required_skills_count(self, obj):
        return obj.role_skills.count()
    required_skills_count.short_description = 'Required Skills'
