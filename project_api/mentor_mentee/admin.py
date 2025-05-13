from django.contrib import admin
from .models import Participant, MentorMenteeRelationship, Session, Badge, QuizResult, ParticipantBadge, MentorFeedback, ApplicationFeedback, FeedbackSettings

class ParticipantAdmin(admin.ModelAdmin):
    list_display = ('name', 'registration_no', 'branch', 'semester', 'department', 'approval_status', 'status')
    list_filter = ('branch', 'semester', 'approval_status', 'status', 'department', 'is_super_mentor')
    search_fields = ('name', 'registration_no', 'tech_stack')

class MentorMenteeRelationshipAdmin(admin.ModelAdmin):
    list_display = ('mentor', 'mentee', 'created_at', 'manually_created')
    list_filter = ('created_at', 'manually_created')
    search_fields = ('mentor__name', 'mentor__registration_no', 'mentee__name', 'mentee__registration_no')

class SessionAdmin(admin.ModelAdmin):
    list_display = ('session_id', 'mentor', 'session_type', 'date_time', 'created_at')
    search_fields = ('mentor__name', 'summary')
    list_filter = ('session_type', 'date_time')

class BadgeAdmin(admin.ModelAdmin):
    list_display = ('name', 'description', 'points_required')
    search_fields = ('name', 'description')
    list_filter = ('points_required',)

class QuizResultAdmin(admin.ModelAdmin):
    list_display = ('id', 'participant', 'quiz_topic', 'score', 'percentage', 'status', 'completed_date')
    search_fields = ('participant__name', 'quiz_topic')
    list_filter = ('status', 'completed_date')

class ParticipantBadgeAdmin(admin.ModelAdmin):
    list_display = ('participant', 'badge', 'earned_date', 'is_claimed', 'claimed_date', 'linkedin_shared')
    search_fields = ('participant__name', 'badge__name')
    list_filter = ('is_claimed', 'earned_date', 'claimed_date', 'linkedin_shared')

class MentorFeedbackAdmin(admin.ModelAdmin):
    list_display = ('mentor', 'mentee', 'overall_rating', 'anonymous', 'created_at')
    search_fields = ('mentor__name', 'mentee__name', 'strengths', 'areas_for_improvement')
    list_filter = ('anonymous', 'created_at', 'overall_rating')

class ApplicationFeedbackAdmin(admin.ModelAdmin):
    list_display = ('participant', 'overall_rating', 'nps_score', 'anonymous', 'created_at')
    search_fields = ('participant__name', 'what_you_like', 'what_to_improve', 'feature_requests')
    list_filter = ('anonymous', 'created_at', 'overall_rating', 'nps_score')

class FeedbackSettingsAdmin(admin.ModelAdmin):
    list_display = ('department', 'mentor_feedback_enabled', 'app_feedback_enabled', 'allow_anonymous_feedback', 'updated_at')
    list_filter = ('mentor_feedback_enabled', 'app_feedback_enabled', 'allow_anonymous_feedback')

admin.site.register(Participant, ParticipantAdmin)
admin.site.register(MentorMenteeRelationship, MentorMenteeRelationshipAdmin)
admin.site.register(Session, SessionAdmin)
admin.site.register(Badge, BadgeAdmin)
admin.site.register(QuizResult, QuizResultAdmin)
admin.site.register(ParticipantBadge, ParticipantBadgeAdmin)
admin.site.register(MentorFeedback, MentorFeedbackAdmin)
admin.site.register(ApplicationFeedback, ApplicationFeedbackAdmin)
admin.site.register(FeedbackSettings, FeedbackSettingsAdmin)
