from rest_framework import serializers
from django.core.exceptions import ValidationError
from .models import Participant, MentorMenteeRelationship

# Validator for file size
def validate_file_size(file):
    limit = 5 * 1024 * 1024  # 5 MB limit
    if file.size > limit:
        raise ValidationError('File size should not exceed 5 MB.')

class MentorInfoSerializer(serializers.ModelSerializer):
    """Serializer for basic mentor information"""
    class Meta:
        model = Participant
        fields = ('name', 'registration_no', 'semester', 'branch', 'tech_stack')

class MenteeInfoSerializer(serializers.ModelSerializer):
    """Serializer for basic mentee information"""
    class Meta:
        model = Participant
        fields = ('name', 'registration_no', 'semester', 'branch', 'tech_stack')

class ParticipantSerializer(serializers.ModelSerializer):
    # Add fields for mentor and mentees
    mentor = serializers.SerializerMethodField()
    mentees = serializers.SerializerMethodField()
    
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

    def create(self, validated_data):
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
