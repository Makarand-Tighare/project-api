from django.contrib import admin
from .models import (
    CareerPath, 
    CareerSkill, 
    CareerMilestone, 
    IntermediateRole, 
    RecommendedProject,
    Resume,
    ResumePDF
)

class CareerSkillInline(admin.TabularInline):
    model = CareerSkill
    extra = 0

class CareerMilestoneInline(admin.TabularInline):
    model = CareerMilestone
    extra = 0
    
class IntermediateRoleInline(admin.TabularInline):
    model = IntermediateRole
    extra = 0
    
class RecommendedProjectInline(admin.TabularInline):
    model = RecommendedProject
    extra = 0

@admin.register(CareerPath)
class CareerPathAdmin(admin.ModelAdmin):
    list_display = ('user', 'current_role', 'target_role', 'timeline', 'created_at')
    search_fields = ('user__email', 'current_role', 'target_role')
    list_filter = ('created_at',)
    inlines = [
        CareerSkillInline,
        CareerMilestoneInline,
        IntermediateRoleInline,
        RecommendedProjectInline
    ]

@admin.register(CareerMilestone)
class CareerMilestoneAdmin(admin.ModelAdmin):
    list_display = ('title', 'career_path', 'status', 'deadline', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('title', 'description', 'career_path__user__email')
    readonly_fields = ('created_at', 'updated_at')

@admin.register(Resume)
class ResumeAdmin(admin.ModelAdmin):
    list_display = ('user', 'created_at', 'updated_at')
    search_fields = ('user__email',)
    list_filter = ('created_at', 'updated_at')

@admin.register(ResumePDF)
class ResumePDFAdmin(admin.ModelAdmin):
    list_display = ('user', 'created_at', 'file')
    search_fields = ('user__email',)
    list_filter = ('created_at',)
