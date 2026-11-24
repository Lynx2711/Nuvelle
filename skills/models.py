from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.functions import Lower


class SkillLevel(models.IntegerChoices):
    BEGINNER = 1, 'Beginner'
    INTERMEDIATE = 2, 'Intermediate'
    ADVANCED = 3, 'Advanced'
    EXPERT = 4, 'Expert'


class SkillCategory(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = 'Skill Categories'
        ordering = ['name']

    def __str__(self):
        return self.name


class Skill(models.Model):
    category = models.ForeignKey(SkillCategory, on_delete=models.CASCADE, related_name='skills')
    name = models.CharField(max_length=150)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                Lower('name'),
                name='unique_skill_name_case_insensitive',
            )
        ]
        ordering = ['name']

    def clean(self):
        # Case-insensitive duplicate check in python before database constraint
        if self.name:
            name_lower = self.name.strip().lower()
            existing = Skill.objects.annotate(name_lower=Lower('name')).filter(name_lower=name_lower)
            if self.pk:
                existing = existing.exclude(pk=self.pk)
            if existing.exists():
                raise ValidationError({'name': 'A skill with this name already exists (case-insensitive).'})

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.category.name})"


class RoleProfile(models.Model):
    name = models.CharField(max_length=150, unique=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class RoleSkill(models.Model):
    role = models.ForeignKey(RoleProfile, on_delete=models.CASCADE, related_name='role_skills')
    skill = models.ForeignKey(Skill, on_delete=models.CASCADE, related_name='role_requirements')
    required_level = models.PositiveSmallIntegerField(
        choices=SkillLevel.choices,
        default=SkillLevel.BEGINNER,
        help_text='Required proficiency level (1-4)',
    )
    weight = models.PositiveSmallIntegerField(
        default=1,
        help_text='Importance weight (1-5)',
    )

    class Meta:
        unique_together = ('role', 'skill')
        ordering = ['-weight', 'skill__name']

    def clean(self):
        if self.required_level not in [1, 2, 3, 4]:
            raise ValidationError({'required_level': 'Required level must be between 1 and 4.'})
        if not (1 <= self.weight <= 5):
            raise ValidationError({'weight': 'Weight must be between 1 and 5.'})

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.role.name} - {self.skill.name} (Lvl {self.required_level}, Wt {self.weight})"
