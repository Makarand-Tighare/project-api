import csv
import requests

# API request - using Django endpoint instead of Flask
url = 'http://127.0.0.1:8000/api/mentor_mentee/match/'
response = requests.get(url)
data = response.json()

# Check the structure of the API response
print(data)

# Reformat matches into mentor-mentee dictionary with their details
mentor_mentees = {}

for match in data['matches']:
    mentor_details = match['mentor']
    mentee_details = match['mentee']
    
    mentor_name = mentor_details['name']
    mentee_name = mentee_details['name']

    if mentor_name not in mentor_mentees:
        mentor_mentees[mentor_name] = {
            "mentorRegNo": mentor_details.get("registration_no", "Unknown"),
            "mentorSemester": mentor_details.get("semester", "Unknown"),
            "mentees": []
        }
    
    # Store only name, registration number, and semester for mentees
    mentor_mentees[mentor_name]["mentees"].append({
        "menteeName": mentee_name,
        "menteeRegNo": mentee_details.get("registration_no", "Unknown"),
        "menteeSemester": mentee_details.get("semester", "Unknown")
    })

# Write to CSV file
with open('mentor_mentee_matches.csv', mode='w', newline='') as file:
    writer = csv.writer(file)
    writer.writerow([
        'Mentor', 'Mentor Reg No', 'Mentor Semester',
        'Mentee', 'Mentee Reg No', 'Mentee Semester'
    ])  # Header
    
    for mentor_name, mentor_data in mentor_mentees.items():
        mentor_written = False
        
        for mentee in mentor_data["mentees"]:
            if not mentor_written:
                # Write mentor info with first mentee
                writer.writerow([
                    mentor_name, 
                    mentor_data['mentorRegNo'], 
                    mentor_data['mentorSemester'],
                    mentee['menteeName'], 
                    mentee['menteeRegNo'], 
                    mentee['menteeSemester']
                ])
                mentor_written = True
            else:
                # Write only mentee info for subsequent mentees
                writer.writerow([
                    "", "", "",  # Empty cells for mentor columns
                    mentee['menteeName'], 
                    mentee['menteeRegNo'], 
                    mentee['menteeSemester']
                ])
        
        # Add a blank row after each mentor's mentees
        writer.writerow(["", "", "", "", "", ""])

print("CSV file created successfully!")
