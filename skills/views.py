from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from accounts.models import UserRole
from accounts.permissions import RoleRequiredMixin

from .forms import RoleProfileForm, RoleSkillForm, SkillCategoryForm, SkillForm
from .models import RoleProfile, RoleSkill, Skill, SkillCategory


class SkillListView(LoginRequiredMixin, ListView):
    model = Skill
    template_name = 'skills/skill_list.html'
    context_object_name = 'skills'
    paginate_by = 30

    def get_queryset(self):
        qs = Skill.objects.select_related('category').order_by('name')
        q = self.request.GET.get('q', '').strip()
        cat = self.request.GET.get('category', '').strip()
        status = self.request.GET.get('status', '').strip()

        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(category__name__icontains=q))
        if cat:
            qs = qs.filter(category_id=cat)
        if status == 'active':
            qs = qs.filter(is_active=True)
        elif status == 'inactive':
            qs = qs.filter(is_active=False)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['categories'] = SkillCategory.objects.annotate(skill_count=Count('skills')).order_by('name')
        ctx['selected_cat'] = self.request.GET.get('category', '')
        ctx['selected_status'] = self.request.GET.get('status', '')
        ctx['query'] = self.request.GET.get('q', '')
        ctx['can_edit'] = self.request.user.role in [UserRole.ADMIN, UserRole.OFFICER] or self.request.user.is_superuser
        return ctx

    def render_to_response(self, context, **response_kwargs):
        # HTMX partial support for live searching/filtering
        if self.request.headers.get('HX-Request'):
            return render(self.request, 'skills/partials/skill_table.html', context)
        return super().render_to_response(context, **response_kwargs)


class SkillCreateView(RoleRequiredMixin, CreateView):
    allowed_roles = [UserRole.ADMIN, UserRole.OFFICER]
    model = Skill
    form_class = SkillForm
    template_name = 'skills/skill_form.html'

    def get_success_url(self):
        messages.success(self.request, f"Skill '{self.object.name}' created.")
        return reverse('skills:skill_list')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['title'] = 'Create New Skill'
        return ctx


class SkillUpdateView(RoleRequiredMixin, UpdateView):
    allowed_roles = [UserRole.ADMIN, UserRole.OFFICER]
    model = Skill
    form_class = SkillForm
    template_name = 'skills/skill_form.html'

    def get_success_url(self):
        messages.success(self.request, f"Skill '{self.object.name}' updated.")
        return reverse('skills:skill_list')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['title'] = f"Edit Skill: {self.object.name}"
        return ctx


class SkillToggleActiveView(RoleRequiredMixin, View):
    allowed_roles = [UserRole.ADMIN, UserRole.OFFICER]

    def post(self, request, pk):
        skill = get_object_or_404(Skill, pk=pk)
        skill.is_active = not skill.is_active
        skill.save(update_fields=['is_active'])
        status_msg = "activated" if skill.is_active else "deactivated"
        messages.success(request, f"Skill '{skill.name}' {status_msg}.")
        return redirect('skills:skill_list')


# Categories
class SkillCategoryListView(LoginRequiredMixin, ListView):
    model = SkillCategory
    template_name = 'skills/category_list.html'
    context_object_name = 'categories'

    def get_queryset(self):
        return SkillCategory.objects.annotate(skill_count=Count('skills')).order_by('name')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['can_edit'] = self.request.user.role in [UserRole.ADMIN, UserRole.OFFICER] or self.request.user.is_superuser
        ctx['form'] = SkillCategoryForm()
        return ctx


class SkillCategoryCreateView(RoleRequiredMixin, CreateView):
    allowed_roles = [UserRole.ADMIN, UserRole.OFFICER]
    model = SkillCategory
    form_class = SkillCategoryForm
    template_name = 'skills/category_form.html'

    def get_success_url(self):
        messages.success(self.request, f"Category '{self.object.name}' created.")
        return reverse('skills:category_list')


class SkillCategoryUpdateView(RoleRequiredMixin, UpdateView):
    allowed_roles = [UserRole.ADMIN, UserRole.OFFICER]
    model = SkillCategory
    form_class = SkillCategoryForm
    template_name = 'skills/category_form.html'

    def get_success_url(self):
        messages.success(self.request, f"Category '{self.object.name}' updated.")
        return reverse('skills:category_list')


# Role Profiles
class RoleProfileListView(LoginRequiredMixin, ListView):
    model = RoleProfile
    template_name = 'skills/role_profile_list.html'
    context_object_name = 'role_profiles'

    def get_queryset(self):
        return RoleProfile.objects.annotate(skill_count=Count('role_skills')).order_by('name')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['can_edit'] = self.request.user.role in [UserRole.ADMIN, UserRole.OFFICER] or self.request.user.is_superuser
        return ctx


class RoleProfileDetailView(LoginRequiredMixin, DetailView):
    model = RoleProfile
    template_name = 'skills/role_profile_detail.html'
    context_object_name = 'role_profile'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['required_skills'] = self.object.role_skills.select_related('skill', 'skill__category').order_by('-weight', 'skill__name')
        ctx['can_edit'] = self.request.user.role in [UserRole.ADMIN, UserRole.OFFICER] or self.request.user.is_superuser
        if ctx['can_edit']:
            ctx['add_skill_form'] = RoleSkillForm(role=self.object)
        return ctx


class RoleProfileCreateView(RoleRequiredMixin, CreateView):
    allowed_roles = [UserRole.ADMIN, UserRole.OFFICER]
    model = RoleProfile
    form_class = RoleProfileForm
    template_name = 'skills/role_profile_form.html'

    def get_success_url(self):
        messages.success(self.request, f"Role profile '{self.object.name}' created. Now add required skills.")
        return reverse('skills:role_profile_detail', kwargs={'pk': self.object.pk})

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['title'] = 'Create Role Profile'
        return ctx


class RoleProfileUpdateView(RoleRequiredMixin, UpdateView):
    allowed_roles = [UserRole.ADMIN, UserRole.OFFICER]
    model = RoleProfile
    form_class = RoleProfileForm
    template_name = 'skills/role_profile_form.html'

    def get_success_url(self):
        messages.success(self.request, f"Role profile '{self.object.name}' updated.")
        return reverse('skills:role_profile_detail', kwargs={'pk': self.object.pk})

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['title'] = f"Edit Role Profile: {self.object.name}"
        return ctx


class RoleSkillAddView(RoleRequiredMixin, View):
    allowed_roles = [UserRole.ADMIN, UserRole.OFFICER]

    def post(self, request, pk):
        role_profile = get_object_or_404(RoleProfile, pk=pk)
        form = RoleSkillForm(request.POST, role=role_profile)
        if form.is_valid():
            role_skill = form.save(commit=False)
            role_skill.role = role_profile
            role_skill.save()
            messages.success(request, f"Skill '{role_skill.skill.name}' added to {role_profile.name}.")
        else:
            messages.error(request, "Failed to add skill. Please ensure all values are valid.")
        return redirect('skills:role_profile_detail', pk=pk)


class RoleSkillDeleteView(RoleRequiredMixin, View):
    allowed_roles = [UserRole.ADMIN, UserRole.OFFICER]

    def post(self, request, role_pk, pk):
        role_skill = get_object_or_404(RoleSkill, pk=pk, role_id=role_pk)
        skill_name = role_skill.skill.name
        role_skill.delete()
        messages.success(request, f"Skill '{skill_name}' removed from role profile.")
        return redirect('skills:role_profile_detail', pk=role_pk)
