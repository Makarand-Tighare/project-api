from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError


class Participant(models.Model):
    SEMESTER_CHOICES = [(str(i), str(i)) for i in range(1, 9)]
    BRANCH_CHOICES = [('cse', 'CSE'), ('ct', 'CT'), ('aids', 'AIDS')]
    MENTORING_PREFERENCE_CHOICES = [('mentor', 'Mentor'), ('mentee', 'Mentee')]
    HACKATHON_ROLE_CHOICES = [('team leader', 'Team Leader'), ('member', 'Member')]
    YES_NO_CHOICES = [('yes', 'Yes'), ('no', 'No')]
    LEVEL_CHOICES = [('International', 'International'), ('National', 'National'), ('College', 'College'), ('Conferences', 'Conferences'), ('None', 'None')]

    # Personal Information
    name = models.CharField(max_length=100)
    registration_no = models.CharField(max_length=20, primary_key=True)  # Primary key
    semester = models.CharField(max_length=1, choices=SEMESTER_CHOICES)
    branch = models.CharField(max_length=10, choices=BRANCH_CHOICES)
    mentoring_preferences = models.CharField(max_length=10, choices=MENTORING_PREFERENCE_CHOICES)
    previous_mentoring_experience = models.TextField(blank=True, null=True)
    tech_stack = models.TextField()
    areas_of_interest = models.TextField()

    # Research
    published_research_papers = models.CharField(max_length=15, choices=LEVEL_CHOICES, default='None')
    proof_of_research_publications = models.BinaryField(blank=True, null=True)  # Store the file as a BLOB

    # Hackathon
    hackathon_participation = models.CharField(max_length=50, choices=LEVEL_CHOICES)
    number_of_wins = models.IntegerField(default=0, validators=[MinValueValidator(0)],blank=True, null=True)
    number_of_participations = models.IntegerField(default=0, validators=[MinValueValidator(0)],blank=True, null=True)
    hackathon_role = models.CharField(default=None,max_length=20, choices=HACKATHON_ROLE_CHOICES,blank=True, null=True)
    proof_of_hackathon_participation = models.BinaryField(blank=True, null=True)  # Store the file as a BLOB

    # Coding Competitions
    coding_competitions_participate = models.CharField(max_length=3, choices=YES_NO_CHOICES)
    level_of_competition = models.CharField(default=None,max_length=15, choices=LEVEL_CHOICES,blank=True, null=True)
    number_of_coding_competitions = models.IntegerField(default=0, validators=[MinValueValidator(0)],blank=True, null=True)
    proof_of_coding_competitions = models.BinaryField(blank=True, null=True)  # Store the file as a BLOB

    # Academic Performance
    cgpa = models.DecimalField(max_digits=4, decimal_places=2, validators=[MinValueValidator(0.0), MaxValueValidator(10.0)])
    sgpa = models.DecimalField(max_digits=4, decimal_places=2, validators=[MinValueValidator(0.0), MaxValueValidator(10.0)])
    proof_of_academic_performance = models.BinaryField(blank=True, null=True)  # Store the file as a BLOB

    # Internship
    internship_experience = models.CharField(max_length=3, choices=YES_NO_CHOICES)
    number_of_internships = models.IntegerField(default=0, validators=[MinValueValidator(0)],blank=True, null=True)
    internship_description = models.TextField(blank=True, null=True)
    proof_of_internships = models.BinaryField(blank=True, null=True)  # Store the file as a BLOB

    # Seminars & Workshops
    seminars_or_workshops_attended = models.CharField(default=None,max_length=3, choices=YES_NO_CHOICES,blank=True, null=True)
    describe_seminars_or_workshops = models.TextField(blank=True, null=True)

    # Extracurricular Activities
    extracurricular_activities = models.CharField(max_length=3, choices=YES_NO_CHOICES,blank=True, null=True)
    describe_extracurricular_activities = models.TextField(blank=True, null=True)
    proof_of_extracurricular_activities = models.BinaryField(blank=True, null=True)  # Store the file as a BLOB

    # Miscellaneous
    date = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.name} ({self.registration_no})'


class MentorMenteeRelationship(models.Model):
    """Model to track mentor-mentee relationships"""
    mentor = models.ForeignKey(Participant, related_name='mentees_relationship', on_delete=models.CASCADE)
    mentee = models.ForeignKey(Participant, related_name='mentor_relationship', on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ('mentor', 'mentee')  # Prevent duplicate relationships
        
    def __str__(self):
        return f'Mentor: {self.mentor.name} - Mentee: {self.mentee.name}'


class Session(models.Model):
    """Model to store mentoring sessions"""
    SESSION_TYPE_CHOICES = [
        ('virtual', 'Virtual'),
        ('physical', 'Physical'),
    ]
    
    session_id = models.AutoField(primary_key=True)
    mentor = models.ForeignKey(Participant, related_name='created_sessions', on_delete=models.CASCADE)
    session_type = models.CharField(max_length=10, choices=SESSION_TYPE_CHOICES)
    date_time = models.DateTimeField()
    meeting_link = models.URLField(blank=True, null=True)  # For virtual sessions
    location = models.TextField(blank=True, null=True)  # For physical sessions
    summary = models.TextField()
    participants = models.ManyToManyField(Participant, related_name='participating_sessions')
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f'Session by {self.mentor.name} on {self.date_time}'
        
    def clean(self):
        # Validate that either meeting_link or location is provided based on session_type
        if self.session_type == 'virtual' and not self.meeting_link:
            raise ValidationError("Meeting link is required for virtual sessions")
        if self.session_type == 'physical' and not self.location:
            raise ValidationError("Location is required for physical sessions")
