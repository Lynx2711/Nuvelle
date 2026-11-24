import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.urls import reverse

from accounts.models import User
from skills.models import RoleProfile, RoleSkill, Skill, SkillCategory, SkillLevel


@pytest.mark.django_db
class TestSkillTaxonomy:
    def test_skill_category_and_skill_creation(self):
        cat = SkillCategory.objects.create(name='Backend Development', description='Server-side tools')
        skill = Skill.objects.create(name='Python', category=cat)

        assert skill.category == cat
        assert skill.is_active is True
        assert str(skill) == 'Python (Backend Development)'

    def test_skill_case_insensitive_uniqueness(self):
        cat = SkillCategory.objects.create(name='Database', description='Data persistence')
        Skill.objects.create(name='PostgreSQL', category=cat)

        # Attempt to create duplicate with lowercase
        duplicate_skill = Skill(name='postgresql', category=cat)
        with pytest.raises((ValidationError, IntegrityError)):
            duplicate_skill.save()

    def test_role_profile_and_role_skill_constraints(self):
        cat = SkillCategory.objects.create(name='Frontend', description='UI tech')
        skill1 = Skill.objects.create(name='JavaScript', category=cat)
        skill2 = Skill.objects.create(name='CSS', category=cat)

        role = RoleProfile.objects.create(name='Frontend Engineer', description='Builds web interfaces')

        rs1 = RoleSkill.objects.create(
            role=role,
            skill=skill1,
            required_level=SkillLevel.ADVANCED,  # Level 3
            weight=4,
        )
        assert rs1.required_level == 3
        assert rs1.weight == 4

        # Disallow duplicate skill on same role profile
        with pytest.raises(IntegrityError):
            RoleSkill.objects.create(
                role=role,
                skill=skill1,
                required_level=SkillLevel.INTERMEDIATE,
                weight=2,
            )

        # Invalid weight (> 5)
        invalid_weight_rs = RoleSkill(role=role, skill=skill2, required_level=SkillLevel.BEGINNER, weight=6)
        with pytest.raises(ValidationError):
            invalid_weight_rs.save()

        # Invalid level (> 4)
        invalid_lvl_rs = RoleSkill(role=role, skill=skill2, required_level=5, weight=3)
        with pytest.raises(ValidationError):
            invalid_lvl_rs.save()

    def test_skills_htmx_search(self, client):
        user = User.objects.create_user(email='test_search@nuvelle.edu', password='Pass1234User')
        client.force_login(user)

        cat = SkillCategory.objects.create(name='Data Science', description='ML and analytics')
        Skill.objects.create(name='PyTorch', category=cat)
        Skill.objects.create(name='React', category=cat)

        # HTMX partial search request
        url = reverse('skills:skill_list') + '?q=Torch'
        resp = client.get(url, HTTP_HX_REQUEST='true')
        assert resp.status_code == 200
        content = resp.content.decode()
        assert 'PyTorch' in content
        assert 'React' not in content
