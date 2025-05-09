from django.db import models
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _

User = get_user_model()

class CareerPath(models.Model):
    """Model for storing user's career path information"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='career_path')
    current_role = models.CharField(max_length=100)
    target_role = models.CharField(max_length=100)
    timeline = models.CharField(max_length=50)  # e.g., "1-2 years"
    current_skills = models.TextField(blank=True, null=True)  # Stored as comma-separated values
    education = models.TextField(blank=True, null=True)
    description = models.TextField(blank=True, null=True)  # AI-generated career path description
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.user.email} - {self.current_role} to {self.target_role}"

class CareerSkill(models.Model):
    """Model for storing skills recommended for career development"""
    IMPORTANCE_CHOICES = [
        ('high', 'High'),
        ('medium', 'Medium'),
        ('low', 'Low'),
    ]
    
    career_path = models.ForeignKey(CareerPath, related_name='skills', on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    importance = models.CharField(max_length=20, choices=IMPORTANCE_CHOICES, default='medium')
    reason = models.TextField(blank=True, null=True)
    
    def __str__(self):
        return f"{self.name} - {self.importance}"
    
class CareerMilestone(models.Model):
    """Model for storing career milestones"""
    STATUS_CHOICES = [
        ('not_started', 'Not Started'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
    ]
    
    career_path = models.ForeignKey(CareerPath, related_name='milestones', on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    deadline = models.DateField(blank=True, null=True)
    estimated_timeline = models.CharField(max_length=100, blank=True, null=True)  # e.g., "3 months"
    skills_involved = models.TextField(blank=True, null=True)  # Stored as comma-separated values
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='not_started')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.title} - {self.get_status_display()}"
    
class IntermediateRole(models.Model):
    """Model for storing potential intermediate roles on the career path"""
    career_path = models.ForeignKey(CareerPath, related_name='intermediate_roles', on_delete=models.CASCADE)
    title = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    
    def __str__(self):
        return self.title

class RecommendedProject(models.Model):
    """Model for storing project recommendations"""
    career_path = models.ForeignKey(CareerPath, related_name='recommended_projects', on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    skills_demonstrated = models.TextField(blank=True, null=True)  # Stored as comma-separated values
    
    def __str__(self):
        return self.title

class Resume(models.Model):
    """Model for storing user's resume data"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='resume')
    data = models.JSONField(default=dict)  # Store the entire resume as JSON
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Resume for {self.user.email}"

class ResumePDF(models.Model):
    """Model for storing generated resume PDFs"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='resume_pdfs')
    file = models.FileField(upload_to='resumes/')
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Resume PDF for {self.user.email} created at {self.created_at}"
