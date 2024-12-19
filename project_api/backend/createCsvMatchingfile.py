import csv
import requests

# API request (replace with actual API URL)
url = 'http://127.0.0.1:5000/match'  # Replace with your API URL
response = requests.get(url)
data = response.json()

# Check the structure of the API response
print(data)

# Reformat matches into mentor-mentee dictionary with their details
mentor_mentees = {}

for match in data['matches']:
    mentor, mentee = match
    
    # Fetch mentor details
    mentor_details = next((item for item in data['matches'] if item['name'] == mentor), None)
    mentee_details = next((item for item in data['matches'] if item['name'] == mentee), None)
    
    if mentor not in mentor_mentees:
        mentor_mentees[mentor] = []
    
    # Store the details of mentor and mentee
    mentor_mentees[mentor].append({
        "mentee": mentee,
        "mentorRegNo": mentor_details.get("registration_no", "Unknown"),
        "mentorSemester": mentor_details.get("semester", "Unknown"),
        "mentorTechStack": mentor_details.get("tech_stack", "Unknown"),
        "mentorCGPA": mentor_details.get("cgpa", "Unknown"),
        "menteeRegNo": mentee_details.get("registration_no", "Unknown"),
        "menteeSemester": mentee_details.get("semester", "Unknown"),
        "menteeTechStack": mentee_details.get("tech_stack", "Unknown"),
        "menteeCGPA": mentee_details.get("cgpa", "Unknown")
    })

# Write to CSV file
with open('mentor_mentee_matches.csv', mode='w', newline='') as file:
    writer = csv.writer(file)
    writer.writerow([
        'Mentor', 'Mentor Reg No', 'Mentor Semester', 'Mentor Tech Stack', 'Mentor CGPA',
        'Mentee', 'Mentee Reg No', 'Mentee Semester', 'Mentee Tech Stack', 'Mentee CGPA'
    ])  # Header
    
    for mentor, mentees in mentor_mentees.items():
        for mentee in mentees:
            writer.writerow([
                mentor, 
                mentee['mentorRegNo'], 
                mentee['mentorSemester'], 
                mentee['mentorTechStack'], 
                mentee['mentorCGPA'],
                mentee['mentee'], 
                mentee['menteeRegNo'], 
                mentee['menteeSemester'], 
                mentee['menteeTechStack'], 
                mentee['menteeCGPA']
            ])

print("CSV file created successfully!")
