from django.core.management.base import BaseCommand
import pandas as pd
import numpy as np
from mentor_mentee.models import Participant
import os

class Command(BaseCommand):
    help = 'Imports participant data from a CSV file into the database'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear existing participants before importing',
        )

    def handle(self, *args, **kwargs):
        # Clear existing participants if requested
        if kwargs['clear']:
            self.stdout.write(self.style.WARNING("Clearing existing participants..."))
            Participant.objects.all().delete()
            self.stdout.write(self.style.SUCCESS("Existing participants cleared!"))
        
        # Path to the CSV file
        script_dir = os.path.dirname(os.path.abspath(__file__))
        file_path = os.path.join(script_dir, 'mentor_mentee_test_data.csv')
        
        if not os.path.exists(file_path):
            self.stdout.write(self.style.ERROR(f"File not found: {file_path}"))
            self.stdout.write(self.style.WARNING("First run 'python -m project_api.mentor_mentee.management.commands.generate_test_data'"))
            return
        
        # Load the CSV data
        self.stdout.write(self.style.NOTICE(f"Loading data from {file_path}"))
        df = pd.read_csv(file_path)
        
        # Record counts
        total = len(df)
        successful = 0
        failed = 0
        
        for idx, row in df.iterrows():
            try:
                # Handle None/NaN values appropriately
                def safe_get(field, default=''):
                    if field in row and not pd.isna(row[field]) and row[field] != 'nan' and row[field] != 'None':
                        return row[field]
                    return default
                
                # Convert number fields
                def safe_num(field, default=0):
                    val = safe_get(field, default)
                    try:
                        if val == '':
                            return default
                        return int(float(val)) if val not in ('nan', 'None') else default
                    except:
                        return default
                
                participant = Participant(
                    name=safe_get('name'),
                    registration_no=safe_get('registration_no'),
                    semester=safe_get('semester'),
                    branch=safe_get('branch'),
                    mentoring_preferences=safe_get('mentoring_preferences'),
                    previous_mentoring_experience=safe_get('previous_mentoring_experience'),
                    tech_stack=safe_get('tech_stack'),
                    areas_of_interest=safe_get('areas_of_interest'),
                    published_research_papers=safe_get('published_research_papers'),
                    hackathon_participation=safe_get('hackathon_participation'),
                    number_of_wins=safe_num('number_of_wins'),
                    number_of_participations=safe_num('number_of_participations'),
                    hackathon_role=safe_get('hackathon_role'),
                    coding_competitions_participate=safe_get('coding_competitions_participate'),
                    level_of_competition=safe_get('level_of_competition'),
                    number_of_coding_competitions=safe_num('number_of_coding_competitions'),
                    cgpa=safe_get('cgpa'),
                    sgpa=safe_get('sgpa'),
                    internship_experience=safe_get('internship_experience'),
                    number_of_internships=safe_num('number_of_internships'),
                    internship_description=safe_get('internship_description'),
                    proof_of_internships=None,  # No files in test data
                    seminars_or_workshops_attended=safe_get('seminars_or_workshops_attended'),
                    describe_seminars_or_workshops=safe_get('describe_seminars_or_workshops'),
                    extracurricular_activities=safe_get('extracurricular_activities'),
                    describe_extracurricular_activities=safe_get('describe_extracurricular_activities'),
                    proof_of_extracurricular_activities=None,  # No files in test data
                    date=pd.to_datetime(row['date'])
                )
                
                # Save the participant to the database
                participant.save()
                successful += 1
                
            except Exception as e:
                failed += 1
                self.stdout.write(self.style.ERROR(f"Error importing participant {idx+1}: {str(e)}"))
        
        self.stdout.write(self.style.SUCCESS(f"Data import completed! Imported {successful} of {total} participants successfully. Failed: {failed}"))

        # Print mentor/mentee distribution
        mentor_count = Participant.objects.filter(mentoring_preferences='mentor').count()
        mentee_count = Participant.objects.filter(mentoring_preferences='mentee').count()
        self.stdout.write(self.style.SUCCESS(f"Distribution: {mentor_count} mentors, {mentee_count} mentees"))