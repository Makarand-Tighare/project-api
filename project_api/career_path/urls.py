from django.urls import path
from . import views

urlpatterns = [
    # Career Path endpoints
    path('path/', views.get_career_path, name='get_career_path'),
    path('path/create/', views.create_update_career_path, name='create_update_career_path'),
    path('path/generate/', views.generate_career_path, name='generate_career_path'),
    
    # Milestone endpoints
    path('milestones/', views.get_milestones, name='get_milestones'),
    path('milestones/add/', views.add_milestone, name='add_milestone'),
    path('milestones/<int:milestone_id>/', views.update_milestone_status, name='update_milestone_status'),
    
    # Resume endpoints
    path('resume/', views.get_resume, name='get_resume'),
    path('resume/save/', views.save_resume, name='save_resume'),
    path('resume/enhance-text/', views.enhance_text, name='enhance_text'),
] 