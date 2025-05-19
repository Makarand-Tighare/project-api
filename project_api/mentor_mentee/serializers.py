from rest_framework import serializers
from django.core.exceptions import ValidationError
from .models import Participant, MentorMenteeRelationship, Session, QuizResult, Badge, ParticipantBadge, MentorFeedback, ApplicationFeedback, FeedbackSettings
from account.models import Department
from account.serializers import DepartmentSerializer

# Validator for file size
def validate_file_size(file):
    limit = 5 * 1024 * 1024  # 5 MB limit
    if file.size > limit:
        raise ValidationError('File size should not exceed 5 MB.')

class MentorInfoSerializer(serializers.ModelSerializer):
    """Serializer for basic mentor information"""
    mentee_count = serializers.SerializerMethodField()
    department_name = serializers.SerializerMethodField()
    
    def get_mentee_count(self, obj):
        return MentorMenteeRelationship.objects.filter(mentor=obj).count()
    
    def get_department_name(self, obj):
        return obj.department.name if obj.department else None
    
    class Meta:
        model = Participant
        fields = ['name', 'registration_no', 'semester', 'branch', 
                  'tech_stack', 'areas_of_interest', 'mentee_count',
                  'badges_earned', 'is_super_mentor', 'leaderboard_points', 'status',
                  'department', 'department_name']

class MenteeInfoSerializer(serializers.ModelSerializer):
    """Serializer for basic mentee information"""
    mentor = serializers.SerializerMethodField()
    department_name = serializers.SerializerMethodField()
    
    def get_mentor(self, obj):
        relationship = MentorMenteeRelationship.objects.filter(mentee=obj).first()
        if relationship:
            return {
                'name': relationship.mentor.name,
                'registration_no': relationship.mentor.registration_no
            }
        return None
    
    def get_department_name(self, obj):
        return obj.department.name if obj.department else None
    
    class Meta:
        model = Participant
        fields = ['name', 'registration_no', 'semester', 'branch', 
                  'tech_stack', 'areas_of_interest', 'mentor',
                  'badges_earned', 'leaderboard_points', 'status',
                  'department', 'department_name']

class ParticipantSerializer(serializers.ModelSerializer):
    # Add fields for mentor and mentees
    mentor = serializers.SerializerMethodField()
    mentees = serializers.SerializerMethodField()
    department_name = serializers.SerializerMethodField()
    department_details = serializers.SerializerMethodField()
    
    class Meta:
        model = Participant
        fields = '__all__'

    def get_mentor(self, obj):
        """Get the mentor for this participant (if they are a mentee)"""
        try:
            relationship = MentorMenteeRelationship.objects.filter(mentee=obj).first()
            if relationship:
                return MentorInfoSerializer(relationship.mentor).data
            return None
        except Exception:
            return None
    
    def get_mentees(self, obj):
        """Get the mentees for this participant (if they are a mentor)"""
        try:
            relationships = MentorMenteeRelationship.objects.filter(mentor=obj)
            if relationships:
                return MenteeInfoSerializer([rel.mentee for rel in relationships], many=True).data
            return []
        except Exception:
            return []
            
    def get_department_name(self, obj):
        return obj.department.name if obj.department else None
        
    def get_department_details(self, obj):
        if obj.department:
            return {
                'id': obj.department.id,
                'name': obj.department.name,
                'code': obj.department.code
            }
        return None

    def create(self, validated_data):
        # Check for department data
        department_id = self.initial_data.get('department_id')
        if department_id:
            try:
                department = Department.objects.get(id=department_id)
                validated_data['department'] = department
            except Department.DoesNotExist:
                pass
        
        # Validate and save 'proof_of_research_publications'
        if 'proof_of_research_publications' in self.initial_data:
            file = self.initial_data['proof_of_research_publications']
            validate_file_size(file)  # Validate file size
            validated_data['proof_of_research_publications'] = file.read()  # Store as binary

        # Validate and save 'proof_of_hackathon_participation'
        if 'proof_of_hackathon_participation' in self.initial_data:
            file = self.initial_data['proof_of_hackathon_participation']
            validate_file_size(file)  # Validate file size
            validated_data['proof_of_hackathon_participation'] = file.read()

        # Validate and save 'proof_of_coding_competitions'
        if 'proof_of_coding_competitions' in self.initial_data:
            file = self.initial_data['proof_of_coding_competitions']
            validate_file_size(file)  # Validate file size
            validated_data['proof_of_coding_competitions'] = file.read()

        # Validate and save 'proof_of_academic_performance'
        if 'proof_of_academic_performance' in self.initial_data:
            file = self.initial_data['proof_of_academic_performance']
            validate_file_size(file)  # Validate file size
            validated_data['proof_of_academic_performance'] = file.read()

        # Validate and save 'proof_of_internships'
        if 'proof_of_internships' in self.initial_data:
            file = self.initial_data['proof_of_internships']
            validate_file_size(file)  # Validate file size
            validated_data['proof_of_internships'] = file.read()

        # Validate and save 'proof_of_extracurricular_activities'
        if 'proof_of_extracurricular_activities' in self.initial_data:
            file = self.initial_data['proof_of_extracurricular_activities']
            validate_file_size(file)  # Validate file size
            validated_data['proof_of_extracurricular_activities'] = file.read()

        # Create the Participant instance with validated data
        return Participant.objects.create(**validated_data)

    def update(self, instance, validated_data):
        # Check for department data
        department_id = self.initial_data.get('department_id')
        if department_id:
            try:
                department = Department.objects.get(id=department_id)
                instance.department = department
            except Department.DoesNotExist:
                pass
                
        # Validate and update 'proof_of_research_publications'
        if 'proof_of_research_publications' in self.initial_data:
            file = self.initial_data['proof_of_research_publications']
            validate_file_size(file)  # Validate file size
            instance.proof_of_research_publications = file.read()

        # Validate and update 'proof_of_hackathon_participation'
        if 'proof_of_hackathon_participation' in self.initial_data:
            file = self.initial_data['proof_of_hackathon_participation']
            validate_file_size(file)  # Validate file size
            instance.proof_of_hackathon_participation = file.read()

        # Validate and update 'proof_of_coding_competitions'
        if 'proof_of_coding_competitions' in self.initial_data:
            file = self.initial_data['proof_of_coding_competitions']
            validate_file_size(file)  # Validate file size
            instance.proof_of_coding_competitions = file.read()

        # Validate and update 'proof_of_academic_performance'
        if 'proof_of_academic_performance' in self.initial_data:
            file = self.initial_data['proof_of_academic_performance']
            validate_file_size(file)  # Validate file size
            instance.proof_of_academic_performance = file.read()

        # Validate and update 'proof_of_internships'
        if 'proof_of_internships' in self.initial_data:
            file = self.initial_data['proof_of_internships']
            validate_file_size(file)  # Validate file size
            instance.proof_of_internships = file.read()

        # Validate and update 'proof_of_extracurricular_activities'
        if 'proof_of_extracurricular_activities' in self.initial_data:
            file = self.initial_data['proof_of_extracurricular_activities']
            validate_file_size(file)  # Validate file size
            instance.proof_of_extracurricular_activities = file.read()

        # Update the rest of the fields
        instance.name = validated_data.get('name', instance.name)
        instance.semester = validated_data.get('semester', instance.semester)
        instance.branch = validated_data.get('branch', instance.branch)
        instance.mentoring_preferences = validated_data.get('mentoring_preferences', instance.mentoring_preferences)
        instance.previous_mentoring_experience = validated_data.get('previous_mentoring_experience', instance.previous_mentoring_experience)
        instance.tech_stack = validated_data.get('tech_stack', instance.tech_stack)
        instance.areas_of_interest = validated_data.get('areas_of_interest', instance.areas_of_interest)
        instance.interest_preference1 = validated_data.get('interest_preference1', instance.interest_preference1)
        instance.interest_preference2 = validated_data.get('interest_preference2', instance.interest_preference2)
        instance.interest_preference3 = validated_data.get('interest_preference3', instance.interest_preference3)
        instance.published_research_papers = validated_data.get('published_research_papers', instance.published_research_papers)
        instance.hackathon_participation = validated_data.get('hackathon_participation', instance.hackathon_participation)
        instance.number_of_wins = validated_data.get('number_of_wins', instance.number_of_wins)
        instance.number_of_participations = validated_data.get('number_of_participations', instance.number_of_participations)
        instance.hackathon_role = validated_data.get('hackathon_role', instance.hackathon_role)
        instance.coding_competitions_participate = validated_data.get('coding_competitions_participate', instance.coding_competitions_participate)
        instance.level_of_competition = validated_data.get('level_of_competition', instance.level_of_competition)
        instance.number_of_coding_competitions = validated_data.get('number_of_coding_competitions', instance.number_of_coding_competitions)
        instance.cgpa = validated_data.get('cgpa', instance.cgpa)
        instance.sgpa = validated_data.get('sgpa', instance.sgpa)
        instance.internship_experience = validated_data.get('internship_experience', instance.internship_experience)
        instance.number_of_internships = validated_data.get('number_of_internships', instance.number_of_internships)
        instance.internship_description = validated_data.get('internship_description', instance.internship_description)
        instance.seminars_or_workshops_attended = validated_data.get('seminars_or_workshops_attended', instance.seminars_or_workshops_attended)
        instance.describe_seminars_or_workshops = validated_data.get('describe_seminars_or_workshops', instance.describe_seminars_or_workshops)
        instance.extracurricular_activities = validated_data.get('extracurricular_activities', instance.extracurricular_activities)
        instance.describe_extracurricular_activities = validated_data.get('describe_extracurricular_activities', instance.describe_extracurricular_activities)
        
        instance.save()
        return instance


class ParticipantInfoSerializer(serializers.ModelSerializer):
    """Simple serializer for participant information in sessions"""
    department_name = serializers.SerializerMethodField()
    
    class Meta:
        model = Participant
        fields = ('name', 'registration_no', 'semester', 'branch', 'department', 'department_name')
        
    def get_department_name(self, obj):
        return obj.department.name if obj.department else None


class SessionSerializer(serializers.ModelSerializer):
    """Serializer for mentoring sessions"""
    # Add more detailed information about the mentor and participants
    mentor_details = ParticipantInfoSerializer(source='mentor', read_only=True)
    participant_details = ParticipantInfoSerializer(source='participants', many=True, read_only=True)
    
    class Meta:
        model = Session
        fields = ('session_id', 'mentor', 'mentor_details', 'session_type', 
                  'date_time', 'meeting_link', 'location', 'summary', 
                  'participants', 'participant_details', 'created_at')
        read_only_fields = ('session_id', 'created_at')
    
    def validate(self, data):
        """Validate that the correct session details are provided based on type"""
        session_type = data.get('session_type')
        meeting_link = data.get('meeting_link')
        location = data.get('location')
        
        if session_type == 'virtual' and not meeting_link:
            raise serializers.ValidationError("Meeting link is required for virtual sessions")
        if session_type == 'physical' and not location:
            raise serializers.ValidationError("Location is required for physical sessions")
        
        return data
    
    def create(self, validated_data):
        # Extract the participants data from the request
        participants_data = self.initial_data.get('participants', [])
        
        # Remove participants from validated_data as we'll handle it separately
        if 'participants' in validated_data:
            validated_data.pop('participants')
        
        # Create session without participants first
        session = Session.objects.create(**validated_data)
        
        # Add participants to the session
        if participants_data:
            for reg_no in participants_data:
                try:
                    participant = Participant.objects.get(registration_no=reg_no)
                    session.participants.add(participant)
                except Participant.DoesNotExist:
                    pass  # Skip if participant doesn't exist
        
        return session

class QuizResultSerializer(serializers.ModelSerializer):
    participant_name = serializers.SerializerMethodField()
    
    class Meta:
        model = QuizResult
        fields = ['id', 'participant', 'participant_name', 'quiz_topic', 'score', 'total_questions', 
                  'percentage', 'quiz_date', 'quiz_data', 'quiz_answers', 'result_details']
        read_only_fields = ['quiz_date']
    
    def get_participant_name(self, obj):
        return obj.participant.name if obj.participant else None

class MentorMenteeRelationshipSerializer(serializers.ModelSerializer):
    class Meta:
        model = MentorMenteeRelationship
        fields = '__all__'

class BadgeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Badge
        fields = '__all__'

class ParticipantBadgeSerializer(serializers.ModelSerializer):
    badge_details = serializers.SerializerMethodField()
    
    class Meta:
        model = ParticipantBadge
        fields = '__all__'
        
    def get_badge_details(self, obj):
        return BadgeSerializer(obj.badge).data

class MentorFeedbackSerializer(serializers.ModelSerializer):
    mentee_name = serializers.SerializerMethodField()
    mentor_name = serializers.SerializerMethodField()
    
    class Meta:
        model = MentorFeedback
        fields = '__all__'
        
    def get_mentee_name(self, obj):
        return obj.mentee.name if (obj.mentee and not obj.anonymous) else "Anonymous Mentee"
        
    def get_mentor_name(self, obj):
        return obj.mentor.name if obj.mentor else None

class ApplicationFeedbackSerializer(serializers.ModelSerializer):
    participant_name = serializers.SerializerMethodField()
    
    class Meta:
        model = ApplicationFeedback
        fields = '__all__'
        
    def get_participant_name(self, obj):
        return obj.participant.name if (obj.participant and not obj.anonymous) else "Anonymous User"

class FeedbackSettingsSerializer(serializers.ModelSerializer):
    department_name = serializers.SerializerMethodField()
    
    class Meta:
        model = FeedbackSettings
        fields = '__all__'
        
    def get_department_name(self, obj):
        return obj.department.name if obj.department else "Global Settings"

class ProfileSerializer(serializers.ModelSerializer):
    """Serializer for participant profile data, excluding binary proof fields"""
    mentor = serializers.SerializerMethodField()
    mentees = serializers.SerializerMethodField()
    department_name = serializers.SerializerMethodField()
    department_details = serializers.SerializerMethodField()
    
    class Meta:
        model = Participant
        exclude = [
            'proof_of_research_publications',
            'proof_of_hackathon_participation',
            'proof_of_coding_competitions',
            'proof_of_academic_performance',
            'proof_of_internships',
            'proof_of_extracurricular_activities'
        ]

    def get_mentor(self, obj):
        """Get the mentor for this participant (if they are a mentee)"""
        try:
            relationship = MentorMenteeRelationship.objects.filter(mentee=obj).first()
            if relationship:
                return MentorInfoSerializer(relationship.mentor).data
            return None
        except Exception:
            return None
    
    def get_mentees(self, obj):
        """Get the mentees for this participant (if they are a mentor)"""
        try:
            relationships = MentorMenteeRelationship.objects.filter(mentor=obj)
            if relationships:
                return MenteeInfoSerializer([rel.mentee for rel in relationships], many=True).data
            return []
        except Exception:
            return []
            
    def get_department_name(self, obj):
        return obj.department.name if obj.department else None
        
    def get_department_details(self, obj):
        if obj.department:
            return {
                'id': obj.department.id,
                'name': obj.department.name,
                'code': obj.department.code
            }
        return None

class ParticipantListSerializer(serializers.ModelSerializer):
    """Serializer for listing participants, excluding binary proof fields"""
    department_name = serializers.SerializerMethodField()
    department_details = serializers.SerializerMethodField()
    
    class Meta:
        model = Participant
        exclude = [
            'proof_of_research_publications',
            'proof_of_hackathon_participation',
            'proof_of_coding_competitions',
            'proof_of_academic_performance',
            'proof_of_internships',
            'proof_of_extracurricular_activities'
        ]
        
    def get_department_name(self, obj):
        return obj.department.name if obj.department else None
        
    def get_department_details(self, obj):
        if obj.department:
            return {
                'id': obj.department.id,
                'name': obj.department.name,
                'code': obj.department.code
            }
        return None
