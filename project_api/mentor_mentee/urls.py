from django.urls import path
from . import views
from .views import view_proof, user_activity_heatmap

urlpatterns = [
    # Add the new proofs endpoint
    path('participants/proofs/<str:registration_no>/', views.get_participant_proofs, name='get_participant_proofs'),
    
    path('participant/<str:registration_no>/proof/<str:proof_type>/', view_proof, name='view_proof'),
    # Existing participant endpoints
    path('participants/create/', views.create_participant, name='create_participant'),
    path('participants/list/', views.list_participants, name='list_participants'),
    path('participants/delete-all/', views.delete_all_participants, name='delete_all_participants'),
    path('participants/profile/<str:registration_no>/', views.get_participant_profile, name='get_participant_profile'),
    
    # Admin approval endpoints
    path('admin/approvals/update/', views.update_participant_approval, name='update_participant_approval'),
    path('admin/approvals/pending/', views.list_pending_approvals, name='list_pending_approvals'),
    path('participants/approval-status/<str:registration_no>/', views.get_approval_status, name='get_approval_status'),
    
    # Profile status management
    path('participants/status/update/', views.update_participant_status, name='update_participant_status'),
    path('participants/status/list/<str:status_filter>/', views.list_participants_by_status, name='list_participants_by_status'),
    
    # Badge management
    path('badges/create/', views.create_badge, name='create_badge'),
    path('badges/list/', views.list_badges, name='list_badges'),
    path('badges/award/', views.award_badge, name='award_badge'),
    path('badges/claim/', views.claim_badge, name='claim_badge'),
    path('badges/unclaim/', views.unclaim_badge, name='unclaim_badge'),
    path('badges/delete/', views.delete_participant_badge, name='delete_participant_badge'),
    path('badges/delete-type/<int:badge_id>/', views.delete_badge_type, name='delete_badge_type'),
    path('participants/badges/<str:registration_no>/', views.get_participant_badges, name='get_participant_badges'),
    path('participants/leaderboard/update/', views.update_leaderboard_points, name='update_leaderboard_points'),
    
    # Leaderboard endpoints
    path('leaderboard/', views.get_leaderboard, name='get_leaderboard'),
    path('leaderboard/calculate/', views.calculate_leaderboard_points, name='calculate_leaderboard_points'),
    path('leaderboard/sync/', views.sync_leaderboard_points, name='sync_leaderboard_points'),
    
    # Mentor-mentee matching and relationship management
    path('match/', views.match_participants, name='match_participants'),
    path('delete_all/', views.delete_all_participants, name='delete_all_participants'),
    path('profile/<str:registration_no>/', views.get_participant_profile, name='get_participant_profile'),
    path('unmatched/', views.list_unmatched_participants, name='list_unmatched_participants'),
    path('relationships/list/', views.list_all_relationships, name='list_all_relationships'),
    path('relationships/create/', views.create_relationship, name='create_relationship'),
    path('relationships/update/<int:relationship_id>/', views.update_relationship, name='update_relationship'),
    path('relationships/delete/<int:relationship_id>/', views.delete_relationship, name='delete_relationship'),
    
    # LinkedIn integration
    path('linkedin/post/', views.linkedin_post, name='linkedin_post'),
    path('linkedin/preview/', views.generate_linkedin_preview, name='generate_linkedin_preview'),
    
    # Session management
    path('sessions/create/', views.create_session, name='create_session'),
    path('sessions/user/<str:registration_no>/', views.get_user_sessions, name='get_user_sessions'),
    path('sessions/details/<int:session_id>/', views.get_session_details, name='get_session_details'),
    path('sessions/delete/<int:session_id>/', views.delete_session, name='delete_session'),
    
    # Quiz management
    path('quiz/generate/', views.generate_quiz, name='generate_quiz'),
    path('quiz/submit/', views.submit_quiz_answers, name='submit_quiz_answers'),
    path('quiz/results/<str:registration_no>/', views.get_participant_quiz_results, name='get_participant_quiz_results'),
    path('quiz/details/<int:result_id>/', views.get_quiz_result_details, name='get_quiz_result_details'),
    path('quiz/pending/<str:registration_no>/', views.get_pending_quizzes, name='get_pending_quizzes'),
    path('quiz/delete/<int:quiz_id>/', views.delete_quiz, name='delete_quiz'),
    
    # Feedback management 
    path('feedback/settings/update/', views.update_feedback_settings, name='update_feedback_settings'),
    path('feedback/settings/', views.get_feedback_settings, name='get_feedback_settings'),
    path('feedback/eligibility/<str:registration_no>/', views.check_feedback_eligibility, name='check_feedback_eligibility'),
    path('feedback/mentor/submit/', views.submit_mentor_feedback, name='submit_mentor_feedback'),
    path('feedback/app/submit/', views.submit_app_feedback, name='submit_app_feedback'),
    path('feedback/mentor/<str:mentor_id>/', views.get_mentor_feedback, name='get_mentor_feedback'),
    path('feedback/app/summary/', views.get_app_feedback_summary, name='get_app_feedback_summary'),
    path('feedback/delete/', views.delete_feedback, name='delete_feedback'),
    path('feedback/send-reminders/', views.send_feedback_reminders, name='send_feedback_reminders'),
    path('user/activity/<str:registration_no>/', user_activity_heatmap, name='user-activity-heatmap'),
    
    # Semester archival and history endpoints
    path('admin/archive-semester/', views.archive_semester_data, name='archive_semester_data'),
    path('participants/history/<str:registration_no>/', views.get_participant_history, name='get_participant_history'),
]
