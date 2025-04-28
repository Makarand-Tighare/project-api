from django.urls import path
from . import views

urlpatterns = [
    path('create/', views.create_participant, name='create_participant'),
    path('list_participants/', views.list_participants, name='list_participants'),
    path('linkedin/post/', views.linkedin_post, name='linkedin_post'),
    path('match/', views.match_participants, name='match_participants'),
    path('delete_all/', views.delete_all_participants, name='delete_all_participants'),
    path('profile/<str:registration_no>/', views.get_participant_profile, name='get_participant_profile'),
]
