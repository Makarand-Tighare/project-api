import csv
import random
import datetime
import os

# Indian first names
indian_first_names = [
    "Aarav", "Aditya", "Arjun", "Arnav", "Aryan", "Ayush", "Dhruv", "Ishaan", "Kabir", "Karan",
    "Lakshya", "Mohit", "Nehal", "Pranav", "Rahul", "Raj", "Rohan", "Rudra", "Sameer", "Shaan",
    "Varun", "Vihaan", "Abhinav", "Gaurav", "Harsh", "Krish", "Nikhil", "Vivaan", "Yash", "Zain",
    "Aanya", "Aditi", "Aisha", "Ananya", "Avni", "Diya", "Ishita", "Kavya", "Kiara", "Kritika",
    "Maira", "Manvi", "Meera", "Nisha", "Pari", "Prisha", "Riya", "Saanvi", "Saisha", "Sana",
    "Tanvi", "Tiya", "Vanya", "Zara", "Aisha", "Divya", "Isha", "Khushi", "Naina", "Shreya"
]

# Indian last names
indian_last_names = [
    "Sharma", "Verma", "Patel", "Singh", "Kumar", "Joshi", "Gupta", "Shah", "Mehta", "Malhotra",
    "Bansal", "Desai", "Chopra", "Bhatia", "Kapoor", "Khanna", "Agarwal", "Reddy", "Iyer", "Nair",
    "Rao", "Choudhary", "Das", "Mukherjee", "Chatterjee", "Sengupta", "Dutta", "Roy", "Biswas", "Ghosh",
    "Chakraborty", "Goswami", "Jain", "Saxena", "Mittal", "Arora", "Kaur", "Gandhi", "Tiwari", "Mishra",
    "Trivedi", "Pandey", "Dubey", "Ahuja", "Chawla", "Menon", "Pillai", "Chandra", "Kohli", "Bose"
]

# Tech stacks
tech_stacks = [
    "Python, Django", "JavaScript, React", "Java, Spring Boot", "C++, OpenCV", 
    "PHP, Laravel", "Ruby, Rails", "Rust, WebAssembly", "Go, Docker", 
    "Kotlin, Android", "Swift, iOS", "JavaScript, Node.js", "Python, Flask",
    "C#, .NET", "TypeScript, Angular", "JavaScript, Vue.js", "R, Shiny",
    "Python, TensorFlow", "Java, Android", "MATLAB, Simulink", "C, Embedded Systems"
]

# Areas of interest
areas_of_interest = [
    "Machine Learning, AI", "Web Development", "Mobile Apps", "Data Science",
    "Cloud Computing", "Blockchain", "DevOps", "Game Development",
    "IoT", "Cybersecurity", "UI/UX Design", "Augmented Reality",
    "Robotics", "Computer Vision", "Natural Language Processing", "Quantum Computing",
    "FinTech", "EdTech", "HealthTech", "Big Data"
]

# Generate mentoring preferences
def get_mentoring_preference(semester):
    if semester >= 6:
        return random.choice(["mentor"] * 3 + ["mentee"])  # 75% chance for mentor
    else:
        return random.choice(["mentee"] * 3 + ["mentor"])  # 75% chance for mentee

# Generate previous experience
def get_previous_experience(preference, semester):
    if preference == "mentor" and semester >= 6:
        return random.choice([
            "Guided juniors in hackathons", 
            "Mentored students on tech stack", 
            "Conducted workshops for juniors", 
            "Tutored programming to freshers",
            "nan" if random.random() < 0.3 else "Peer mentoring in college projects"
        ])
    return "nan"

# Generate unique registration numbers
def generate_unique_reg_numbers(count):
    reg_numbers = set()
    while len(reg_numbers) < count:
        reg_no = str(random.randint(22000000, 23500000))
        reg_numbers.add(reg_no)
    return list(reg_numbers)

# Generate hackathon details
def generate_hackathon_details():
    participation = random.choice(["International", "National", "College", "nan"])
    if participation == "nan":
        return {
            "participation": participation,
            "wins": 0,
            "participations": 0,
            "role": "nan"
        }
    
    wins = random.randint(0, 5)
    participations = wins + random.randint(0, 5)
    role = random.choice(["Team Leader", "Participant", "nan"])
    
    return {
        "participation": participation,
        "wins": wins,
        "participations": participations,
        "role": role
    }

# Generate coding competitions details
def generate_coding_competitions():
    participates = random.choice(["Yes", "No"])
    if participates == "No":
        return {
            "participates": participates,
            "level": None,
            "count": random.randint(0, 2)  # Some might have done a few but currently don't participate
        }
    
    return {
        "participates": participates,
        "level": random.choice([None, "National", "International", "College"]),
        "count": random.randint(1, 10)
    }

# Generate academic performance
def generate_academic_performance():
    cgpa = round(random.uniform(6.0, 10.0), 2)
    sgpa = round(random.uniform(6.0, 10.0), 2)
    
    return {
        "cgpa": cgpa,
        "sgpa": sgpa
    }

# Generate internship details
def generate_internship_details(semester):
    has_internship = random.choice(["Yes", "No"])
    if has_internship == "No" or semester <= 3:  # Lower semesters less likely to have internships
        return {
            "has_internship": "No",
            "count": 0,
            "description": "nan"
        }
    
    count = random.randint(1, 3)
    descriptions = [
        "Developed web applications",
        "Worked on AI projects",
        "Created mobile applications",
        "Analyzed data pipelines",
        "nan"
    ]
    
    return {
        "has_internship": "Yes",
        "count": count,
        "description": random.choice(descriptions)
    }

# Generate seminars/workshops
def generate_seminars():
    attended = random.choice(["Yes", "No"])
    if attended == "No":
        return {
            "attended": "No",
            "description": "nan"
        }
    
    descriptions = [
        "AI workshop",
        "Leadership webinar",
        "Technical symposium",
        "Cloud computing seminar",
        "nan"
    ]
    
    return {
        "attended": "Yes",
        "description": random.choice(descriptions)
    }

# Generate extracurricular
def generate_extracurricular():
    has_activities = random.choice(["Yes", "No"])
    if has_activities == "No":
        return {
            "has_activities": "No",
            "description": "nan"
        }
    
    descriptions = [
        "College sports team",
        "Cultural club member",
        "Volunteered at NGOs",
        "Chess Club member",
        "Participated in cultural fests",
        "nan"
    ]
    
    return {
        "has_activities": "Yes",
        "description": random.choice(descriptions)
    }

# Generate research papers
def generate_research_papers(semester):
    if semester >= 5 and random.random() < 0.3:  # 30% chance for higher semester students
        return random.randint(1, 3)
    return "nan"

# Generate participants data
def generate_participants(count=150):
    participants = []
    reg_numbers = generate_unique_reg_numbers(count)
    
    for i in range(count):
        # Basic info
        first_name = random.choice(indian_first_names)
        last_name = random.choice(indian_last_names)
        name = f"{first_name} {last_name}"
        registration_no = reg_numbers[i]
        semester = random.randint(1, 8)
        branch = random.choice([
            "Computer Technology", 
            "Information Technology", 
            "Computer Science", 
            "Artificial Intelligence and Data Science",
            "Electronics and Communication"
        ])
        
        # Mentoring preferences
        mentoring_preferences = get_mentoring_preference(semester)
        previous_experience = get_previous_experience(mentoring_preferences, semester)
        
        # Technical skills
        tech_stack = random.choice(tech_stacks)
        interest = random.choice(areas_of_interest)
        research_papers = generate_research_papers(semester)
        
        # Competitions
        hackathon = generate_hackathon_details()
        coding = generate_coding_competitions()
        
        # Academics and experience
        academics = generate_academic_performance()
        internship = generate_internship_details(semester)
        seminars = generate_seminars()
        extracurricular = generate_extracurricular()
        
        # Date - random time in last month
        date = datetime.datetime.now() - datetime.timedelta(days=random.randint(0, 30))
        date_str = date.strftime("%Y-%m-%d %H:%M:%S")
        
        # Create participant object
        participant = {
            "name": name,
            "registration_no": registration_no,
            "semester": str(semester),
            "branch": branch,
            "mentoring_preferences": mentoring_preferences,
            "previous_mentoring_experience": previous_experience,
            "tech_stack": tech_stack,
            "areas_of_interest": interest,
            "published_research_papers": research_papers,
            "proof_of_research_publications": None,
            "hackathon_participation": hackathon["participation"],
            "number_of_wins": hackathon["wins"],
            "number_of_participations": hackathon["participations"],
            "hackathon_role": hackathon["role"],
            "proof_of_hackathon_participation": None,
            "coding_competitions_participate": coding["participates"],
            "level_of_competition": coding["level"],
            "number_of_coding_competitions": coding["count"],
            "proof_of_coding_competitions": None,
            "cgpa": str(academics["cgpa"]),
            "sgpa": str(academics["sgpa"]),
            "proof_of_academic_performance": None,
            "internship_experience": internship["has_internship"],
            "number_of_internships": internship["count"],
            "internship_description": internship["description"],
            "proof_of_internships": None,
            "seminars_or_workshops_attended": seminars["attended"],
            "describe_seminars_or_workshops": seminars["description"],
            "extracurricular_activities": extracurricular["has_activities"],
            "describe_extracurricular_activities": extracurricular["description"],
            "proof_of_extracurricular_activities": None,
            "date": date_str
        }
        
        participants.append(participant)
    
    return participants

def save_to_csv(participants, filename="mentor_mentee_test_data.csv"):
    # Get the script directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(script_dir, filename)
    
    # Extract fields from first participant
    fieldnames = list(participants[0].keys())
    
    # Write to CSV
    with open(file_path, "w", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(participants)
    
    print(f"Data saved to {file_path}")
    return file_path

if __name__ == "__main__":
    # Generate 150 participants
    participants = generate_participants(150)
    
    # Save to CSV
    file_path = save_to_csv(participants)
    
    # Print distribution statistics
    mentor_count = sum(1 for p in participants if p["mentoring_preferences"] == "mentor")
    mentee_count = sum(1 for p in participants if p["mentoring_preferences"] == "mentee")
    
    print(f"Generated {len(participants)} participants:")
    print(f"  - Mentors: {mentor_count}")
    print(f"  - Mentees: {mentee_count}")
    
    # Count by semester
    semester_counts = {}
    for p in participants:
        sem = p["semester"]
        semester_counts[sem] = semester_counts.get(sem, 0) + 1
    
    print("\nDistribution by semester:")
    for sem in sorted(semester_counts.keys()):
        print(f"  - Semester {sem}: {semester_counts[sem]}") 