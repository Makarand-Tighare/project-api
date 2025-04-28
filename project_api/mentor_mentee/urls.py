from django.urls import path
from . import views

urlpatterns = [
    path('create/', views.create_participant, name='create_participant'),
    path('list_participants/', views.list_participants, name='list_participants'),
    path('linkedin/post/', views.linkedin_post, name='linkedin_post'),
    path('match/', views.match_participants, name='match_participants'),
    path('delete_all/', views.delete_all_participants, name='delete_all_participants'),
    path('profile/<str:registration_no>/', views.get_participant_profile, name='get_participant_profile'),
    
    # Session management endpoints
    path('sessions/create/', views.create_session, name='create_session'),
    path('sessions/user/<str:registration_no>/', views.get_user_sessions, name='get_user_sessions'),
    path('sessions/<int:session_id>/', views.get_session_details, name='get_session_details'),
    path('sessions/delete/<int:session_id>/', views.delete_session, name='delete_session'),
]
