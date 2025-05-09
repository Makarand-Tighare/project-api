from rest_framework import serializers
from .models import CareerPath, CareerSkill, CareerMilestone, IntermediateRole, RecommendedProject, Resume, ResumePDF

class CareerSkillSerializer(serializers.ModelSerializer):
    class Meta:
        model = CareerSkill
        fields = ['id', 'name', 'importance', 'reason']

class CareerMilestoneSerializer(serializers.ModelSerializer):
    class Meta:
        model = CareerMilestone
        fields = ['id', 'title', 'description', 'deadline', 'estimated_timeline', 
                 'skills_involved', 'status', 'created_at', 'updated_at']

class IntermediateRoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = IntermediateRole
        fields = ['id', 'title', 'description']

class RecommendedProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = RecommendedProject
        fields = ['id', 'title', 'description', 'skills_demonstrated']

class CareerPathSerializer(serializers.ModelSerializer):
    skills = CareerSkillSerializer(many=True, read_only=True)
    milestones = CareerMilestoneSerializer(many=True, read_only=True)
    intermediate_roles = IntermediateRoleSerializer(many=True, read_only=True)
    recommended_projects = RecommendedProjectSerializer(many=True, read_only=True)
    
    class Meta:
        model = CareerPath
        fields = [
            'id', 'current_role', 'target_role', 'timeline', 'current_skills', 
            'education', 'description', 'skills', 'milestones', 
            'intermediate_roles', 'recommended_projects'
        ]

# Input serializer for creating a career path
class CareerPathInputSerializer(serializers.ModelSerializer):
    class Meta:
        model = CareerPath
        fields = ['current_role', 'target_role', 'timeline', 'current_skills', 'education']

# Input serializer for generating AI recommendations
class GenerateCareerPathSerializer(serializers.Serializer):
    current_role = serializers.CharField(required=True)
    target_role = serializers.CharField(required=True)
    timeline = serializers.CharField(required=True)
    current_skills = serializers.CharField(required=True)
    education = serializers.CharField(required=True)

# Input serializer for creating a milestone
class MilestoneInputSerializer(serializers.ModelSerializer):
    class Meta:
        model = CareerMilestone
        fields = ['title', 'description', 'deadline', 'estimated_timeline', 'skills_involved']

class ResumeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Resume
        fields = ['data']
        
    def to_representation(self, instance):
        # Return the JSON data directly
        return instance.data

class EnhanceTextSerializer(serializers.Serializer):
    text = serializers.CharField(required=True)
    context = serializers.CharField(required=True)
    target = serializers.CharField(required=True)
    
    def validate_context(self, value):
        valid_contexts = ['experience', 'education', 'projects', 'achievements', 'basics']
        if value not in valid_contexts:
            raise serializers.ValidationError(f"Context must be one of: {', '.join(valid_contexts)}")
        return value

class ResumePDFSerializer(serializers.ModelSerializer):
    pdf_url = serializers.SerializerMethodField()
    
    class Meta:
        model = ResumePDF
        fields = ['id', 'pdf_url', 'created_at']
    
    def get_pdf_url(self, obj):
        request = self.context.get('request')
        if obj.file and hasattr(obj.file, 'url') and request is not None:
            return request.build_absolute_uri(obj.file.url)
        return None 