from django.urls import path
from . import views

urlpatterns = [
    path('create/', views.create_participant, name='create_participant'),
    path('list_participants/', views.list_participants, name='list_participants'),
    path('linkedin/post/', views.linkedin_post, name='linkedin_post'),
    path('match/', views.match_participants, name='match_participants'),
    path('delete_all/', views.delete_all_participants, name='delete_all_participants'),
    path('profile/<str:registration_no>/', views.get_participant_profile, name='get_participant_profile'),
    path('unmatched/', views.list_unmatched_participants, name='list_unmatched_participants'),
    
    # Session management endpoints
    path('sessions/create/', views.create_session, name='create_session'),
    path('sessions/user/<str:registration_no>/', views.get_user_sessions, name='get_user_sessions'),
    path('sessions/<int:session_id>/', views.get_session_details, name='get_session_details'),
    path('sessions/delete/<int:session_id>/', views.delete_session, name='delete_session'),
    
    # Admin endpoints for managing mentor-mentee relationships
    path('relationships/', views.list_all_relationships, name='list_all_relationships'),
    path('relationships/create/', views.create_relationship, name='create_relationship'),
    path('relationships/update/<int:relationship_id>/', views.update_relationship, name='update_relationship'),
    path('relationships/delete/<int:relationship_id>/', views.delete_relationship, name='delete_relationship'),

    # Quiz endpoints
    path('generate-quiz/', views.generate_quiz, name='generate_quiz'),
    path('submit-quiz/', views.submit_quiz_answers, name='submit_quiz_answers'),
    path('quiz-results/<str:registration_no>/', views.get_participant_quiz_results, name='get_participant_quiz_results'),
    path('quiz-result/<int:result_id>/', views.get_quiz_result_details, name='get_quiz_result_details'),
    path('pending-quizzes/<str:registration_no>/', views.get_pending_quizzes, name='get_pending_quizzes'),
    path('delete-quiz/<int:quiz_id>/', views.delete_quiz, name='delete_quiz'),
]
