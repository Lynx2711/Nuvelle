from django.contrib import admin

from .models import Opportunity, OpportunitySkill


class OpportunitySkillInline(admin.TabularInline):
    model = OpportunitySkill
    extra = 1
    autocomplete_fields = ['skill']


@admin.register(Opportunity)
class OpportunityAdmin(admin.ModelAdmin):
    list_display = (
        'title',
        'company',
        'type',
        'mode',
        'location',
        'status',
        'deadline',
        'openings',
        'required_skills_count',
        'created_at',
    )
    list_filter = ('type', 'mode', 'status', 'company')
    search_fields = ('title', 'company__name', 'description', 'location')
    inlines = [OpportunitySkillInline]

    def required_skills_count(self, obj):
        return obj.required_skills.count()
    required_skills_count.short_description = 'Skills'
