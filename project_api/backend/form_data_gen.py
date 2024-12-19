import random
import numpy as np
import pandas as pd
import os

output_path = os.path.join('mentor_mentee_test_data.csv')

# Helper function to generate random Indian names
def generate_indian_name(gender="male"):
    male_names = ["Aarav", "Vivaan", "Aditya", "Karthik", "Rohan", "Kabir", "Rajesh", "Siddharth", "Anil", "Dev"]
    female_names = ["Ananya", "Priya", "Ishita", "Kavya", "Meera", "Radhika", "Sneha", "Pooja", "Nandini", "Aditi"]
    last_names = ["Sharma", "Verma", "Iyer", "Patel", "Joshi", "Rao", "Gupta", "Kapoor", "Mehta", "Deshmukh"]
    first_name = random.choice(male_names if gender == "male" else female_names)
    last_name = random.choice(last_names)
    return f"{first_name} {last_name}"

# Define columns for the dataset
columns = [
    "name", "registration_no", "semester", "branch", "mentoring_preferences", 
    "previous_mentoring_experience", "tech_stack", "areas_of_interest", 
    "published_research_papers", "hackathon_participation", "number_of_wins", 
    "number_of_participations", "hackathon_role", "coding_competitions_participate", 
    "number_of_coding_competitions", "cgpa", "sgpa", "internship_experience", 
    "number_of_internships", "internship_description", "proof_of_internships", 
    "seminars_or_workshops_attended", "describe_seminars_or_workshops", 
    "extracurricular_activities", "describe_extracurricular_activities", 
    "proof_of_extracurricular_activities", "short_term_goals", "long_term_goals", 
    "strengths_and_weaknesses", "preferred_learning_style", "areas_for_personal_growth", 
    "date"
]

# Generate 150 records
records = []
for _ in range(150):
    gender = random.choice(["male", "female"])
    record = {
        "name": generate_indian_name(gender),
        "registration_no": random.randint(2000000, 2800000),
        "semester": random.randint(1, 8),
        "branch": random.choice(["Computer Technology", "Artificial Intelligence and Data Science"]),
        "mentoring_preferences": random.choice(["mentor", "mentee"]),
        "previous_mentoring_experience": random.choice([
            "Mentored students on tech stack", "Guided juniors in hackathons", "None"
        ]),
        "tech_stack": random.choice([
            "Java, Spring Boot", "Python, React", "C++, OpenCV", "JavaScript, Node.js", 
            "PHP, Laravel", "Ruby on Rails", "Go, Kubernetes", "Swift, iOS Development", 
            "Flutter, Dart", "Rust, WebAssembly"
        ]),
        "areas_of_interest": random.choice([
            "Machine Learning, AI", "IoT, Embedded Systems", "Blockchain", "Web Development", 
            "Cloud Computing", "Cybersecurity", "Game Development", "Mobile App Development", 
            "Data Engineering", "DevOps"
        ]),
        "published_research_papers": "International" if random.random() < 0.1 else "None",
        "hackathon_participation": random.choice(["International", "National", "College", "None"]),
        "number_of_wins": random.randint(0, 5),
        "number_of_participations": random.randint(0, 10),
        "hackathon_role": random.choice(["Team Leader", "Participant", "None"]),
        "coding_competitions_participate": random.choice(["Yes", "No"]),
        "number_of_coding_competitions": random.randint(0, 5),
        "cgpa": round(random.uniform(6.0, 10.0), 2),
        "sgpa": round(random.uniform(6.0, 10.0), 2),
        "internship_experience": random.choice(["Yes", "No"]),
        "number_of_internships": np.random.choice([0, 1, 2, 3], p=[0.2, 0.5, 0.2, 0.1]),
        "internship_description": random.choice([
            "Worked on AI projects", "Developed web applications", "Analyzed data pipelines", "None"
        ]),
        "seminars_or_workshops_attended": random.choice(["Yes", "No"]),
        "describe_seminars_or_workshops": random.choice([
            "AI workshop", "Cloud computing seminar", "Leadership webinar", None
        ]),
        "extracurricular_activities": random.choice(["Yes", "No"]),
        "describe_extracurricular_activities": random.choice([
            "Chess Club member", "Volunteered at NGOs", "Participated in cultural fests", None
        ]),
        
        "short_term_goals": random.choice([
            "Get a research position in AI", "Lead a tech startup", "Pursue a career in Data Science", 
            "Develop an open-source project", "Become a tech lead", "Win a hackathon", 
            "Publish a research paper", "Master a new programming language"
        ]),
        "long_term_goals": random.choice([
            "Get a research position in AI", "Lead a tech startup", "Pursue a career in Data Science", 
            "Become a CTO", "Build a SaaS product", "Contribute to global tech policies", 
            "Work on space exploration tech", "Teach at a reputed university"
        ]),
        "strengths_and_weaknesses": random.choice([
            "Smart but Lazy", "Good at teamwork", "Overthinker", "Quick Learner", "Detail-oriented", 
            "Procrastinator", "Strong communicator", "Prefers working solo", "Handles pressure well", 
            "Needs better time management"
        ]),
        "preferred_learning_style": random.choice([
            "Project-based learning", "Discussion-oriented", "Self-paced learning", "Hands-on workshops", 
            "Video tutorials", "Reading documentation", "Group learning", "Mentorship-driven"
        ]),
        "areas_for_personal_growth": random.choice([
            "DSA", "Leadership", "Everything", "Public Speaking", "Networking", "Team Management", 
            "Critical Thinking", "Emotional Intelligence", "Time Management", "Coding Best Practices"
        ]),
        "date": pd.Timestamp.now().strftime("%Y-%m-%d"),
    }
    records.append(record)

# Convert records to a DataFrame
extended_data = pd.DataFrame(records)

# Save the dataset to a CSV file
extended_data.to_csv(output_path, index=False)
print(f"File saved at: {output_path}")
