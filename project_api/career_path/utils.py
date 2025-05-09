import os
import json
import tempfile
import requests
from django.conf import settings
from django.core.files.base import ContentFile
import io
import logging
import base64
from django.template.loader import render_to_string
import random
# Import reportlab dependencies
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, ListFlowable, ListItem, PageBreak, Flowable
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

logger = logging.getLogger(__name__)

def generate_resume_pdf(resume_data, user):
    """
    Generate a PDF from resume data using reportlab
    
    Args:
        resume_data (dict): Resume data in JSON format
        user (User): User instance
        
    Returns:
        ContentFile: PDF file content
    """
    try:
        # Create a BytesIO buffer to receive PDF data
        buffer = io.BytesIO()
        
        # Create the PDF object using ReportLab
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=0.6*inch,
            leftMargin=0.6*inch,
            topMargin=0.6*inch,
            bottomMargin=0.6*inch
        )
        
        # Define styles
        styles = getSampleStyleSheet()
        
        # Custom styles that match the CSS
        title_style = ParagraphStyle(
            'Title',
            parent=styles['Heading1'],
            fontSize=18,
            fontName='Helvetica-Bold',
            alignment=1,  # Center alignment
            textColor=colors.HexColor('#2c3e50'),
            spaceAfter=2
        )
        
        contact_style = ParagraphStyle(
            'Contact',
            parent=styles['Normal'],
            fontSize=10,
            alignment=1,  # Center alignment
            spaceAfter=12
        )
        
        # Section title with horizontal line
        section_title_style = ParagraphStyle(
            'SectionTitle',
            parent=styles['Heading2'],
            fontSize=12,
            fontName='Helvetica-Bold',
            textColor=colors.HexColor('#2c3e50'),
            leftIndent=0,
            rightIndent=0,
            spaceBefore=10,
            spaceAfter=3,
            leading=14
        )
        
        item_title_style = ParagraphStyle(
            'ItemTitle',
            parent=styles['Normal'],
            fontSize=10,
            fontName='Helvetica-Bold',
            textColor=colors.black,
            spaceAfter=1,
            leading=12
        )
        
        item_subtitle_style = ParagraphStyle(
            'ItemSubtitle',
            parent=styles['Italic'],
            fontSize=9,
            fontName='Helvetica-Oblique',
            textColor=colors.HexColor('#555555'),
            spaceAfter=3,
            leading=11
        )
        
        normal_style = ParagraphStyle(
            'NormalText',
            parent=styles['Normal'],
            fontSize=9,
            fontName='Helvetica',
            textColor=colors.black,
            spaceAfter=3,
            leading=11
        )
        
        date_style = ParagraphStyle(
            'DateText',
            parent=styles['Normal'],
            fontSize=9,
            fontName='Helvetica',
            textColor=colors.HexColor('#555555'),
            alignment=2,  # Right alignment
            leading=12
        )
        
        location_style = ParagraphStyle(
            'LocationText',
            parent=styles['Normal'],
            fontSize=9,
            fontName='Helvetica',
            textColor=colors.HexColor('#555555'),
            alignment=2,  # Right alignment
            leading=11
        )
        
        bullet_style = ParagraphStyle(
            'BulletPoint',
            parent=styles['Normal'],
            fontSize=9,
            fontName='Helvetica',
            leftIndent=10,
            firstLineIndent=0,
            spaceBefore=0,
            spaceAfter=1,
            leading=11,
            bulletIndent=0,
            bulletFontSize=8
        )
        
        skill_title_style = ParagraphStyle(
            'SkillTitle',
            parent=styles['Normal'],
            fontSize=9,
            fontName='Helvetica-Bold',
            spaceAfter=2,
            leading=11
        )
        
        # Container for elements to add to PDF
        elements = []
        
        # Add name as title
        name = resume_data.get('basics', {}).get('name', f"{user.first_name} {user.last_name}")
        elements.append(Paragraph(name, title_style))
        
        # Add contact info
        contact_parts = []
        if resume_data.get('basics', {}).get('email'):
            contact_parts.append(resume_data['basics']['email'])
        if resume_data.get('basics', {}).get('phone'):
            contact_parts.append(resume_data['basics']['phone'])
        if resume_data.get('basics', {}).get('location'):
            contact_parts.append(resume_data['basics']['location'])
            
        if contact_parts:
            elements.append(Paragraph(" | ".join(contact_parts), contact_style))
            
        # Add horizontal line after header
        elements.append(HorizontalLine(0, 0.75))
        
        # Add summary if available
        if resume_data.get('basics', {}).get('summary'):
            elements.append(Paragraph("SUMMARY", section_title_style))
            elements.append(HorizontalLine(0.6, 0.25))
            elements.append(Paragraph(resume_data['basics']['summary'], normal_style))
        
        # Add experience
        if resume_data.get('experience'):
            elements.append(Paragraph("PROFESSIONAL EXPERIENCE", section_title_style))
            elements.append(HorizontalLine(0.6, 0.25))
            
            for exp in resume_data['experience']:
                # Job title and date in a table for alignment
                job_title = exp.get('position', 'Position')
                date_range = f"{exp.get('startDate', '')} - {exp.get('endDate', 'Present') if not exp.get('current', False) else 'Present'}"
                
                job_table_data = [[
                    Paragraph(job_title, item_title_style),
                    Paragraph(date_range, date_style)
                ]]
                
                job_table = Table(job_table_data, colWidths=[4.5*inch, 2.3*inch])
                job_table.setStyle(TableStyle([
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
                ]))
                elements.append(job_table)
                
                # Company and location in a table for alignment
                company = exp.get('company', '')
                location = exp.get('location', '')
                
                company_table_data = [[
                    Paragraph(company, item_subtitle_style),
                    Paragraph(location, location_style)
                ]]
                
                company_table = Table(company_table_data, colWidths=[4.5*inch, 2.3*inch])
                company_table.setStyle(TableStyle([
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
                    ('TOPPADDING', (0, 0), (-1, -1), 0),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
                ]))
                elements.append(company_table)
                
                # Description
                if exp.get('description'):
                    elements.append(Paragraph(exp['description'], normal_style))
                
                # Bullet points
                if exp.get('bullets'):
                    bullets = []
                    for bullet in exp['bullets']:
                        bullet_text = "• " + bullet
                        elements.append(Paragraph(bullet_text, bullet_style))
                
                elements.append(Spacer(1, 5))
        
        # Add education
        if resume_data.get('education'):
            elements.append(Paragraph("EDUCATION", section_title_style))
            elements.append(HorizontalLine(0.6, 0.25))
            
            for edu in resume_data['education']:
                # Degree and date in a table for alignment
                degree = f"{edu.get('degree', '')}"
                if edu.get('fieldOfStudy'):
                    degree += f", {edu.get('fieldOfStudy', '')}"
                date_range = f"{edu.get('startDate', '')} - {edu.get('endDate', '')}"
                
                edu_table_data = [[
                    Paragraph(degree, item_title_style),
                    Paragraph(date_range, date_style)
                ]]
                
                edu_table = Table(edu_table_data, colWidths=[4.5*inch, 2.3*inch])
                edu_table.setStyle(TableStyle([
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
                ]))
                elements.append(edu_table)
                
                # Institution and location in a table for alignment
                institution = edu.get('institution', '')
                location = edu.get('location', '')
                
                inst_table_data = [[
                    Paragraph(institution, item_subtitle_style),
                    Paragraph(location, location_style)
                ]]
                
                inst_table = Table(inst_table_data, colWidths=[4.5*inch, 2.3*inch])
                inst_table.setStyle(TableStyle([
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
                    ('TOPPADDING', (0, 0), (-1, -1), 0),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
                ]))
                elements.append(inst_table)
                
                # GPA if available
                if edu.get('gpa'):
                    elements.append(Paragraph(f"GPA: {edu.get('gpa')}", normal_style))
                
                # Description
                if edu.get('description'):
                    elements.append(Paragraph(edu['description'], normal_style))
                
                elements.append(Spacer(1, 5))
        
        # Add skills
        if resume_data.get('skills'):
            elements.append(Paragraph("SKILLS", section_title_style))
            elements.append(HorizontalLine(0.6, 0.25))
            
            skills_content = []
            
            # Technical skills
            if resume_data['skills'].get('technical'):
                skills_content.append([
                    Paragraph("Technical Skills:", skill_title_style),
                    Paragraph(", ".join(resume_data['skills']['technical']), normal_style)
                ])
            
            # Soft skills
            if resume_data['skills'].get('soft'):
                skills_content.append([
                    Paragraph("Soft Skills:", skill_title_style),
                    Paragraph(", ".join(resume_data['skills']['soft']), normal_style)
                ])
                
            if skills_content:
                skills_table = Table(skills_content, colWidths=[1.2*inch, 5.6*inch])
                skills_table.setStyle(TableStyle([
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ('ALIGN', (0, 0), (0, -1), 'LEFT'),
                    ('TOPPADDING', (0, 0), (-1, -1), 1),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
                ]))
                elements.append(skills_table)
        
        # Add projects
        if resume_data.get('projects'):
            elements.append(Paragraph("PROJECTS", section_title_style))
            elements.append(HorizontalLine(0.6, 0.25))
            
            for project in resume_data['projects']:
                # Project title and date in a table for alignment
                project_title = project.get('title', 'Project')
                date_info = ""
                if project.get('startDate'):
                    date_info = project['startDate']
                    if project.get('endDate'):
                        date_info += f" - {project['endDate']}"
                
                project_table_data = [[
                    Paragraph(project_title, item_title_style),
                    Paragraph(date_info, date_style)
                ]]
                
                project_table = Table(project_table_data, colWidths=[4.5*inch, 2.3*inch])
                project_table.setStyle(TableStyle([
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
                ]))
                elements.append(project_table)
                
                # Technologies
                if project.get('technologies'):
                    elements.append(Paragraph(f"Technologies: {project['technologies']}", item_subtitle_style))
                
                # Description
                if project.get('description'):
                    elements.append(Paragraph(project['description'], normal_style))
                
                # Link
                if project.get('link'):
                    elements.append(Paragraph(f"Link: {project['link']}", normal_style))
                
                elements.append(Spacer(1, 5))
        
        # Add certifications
        if resume_data.get('certifications'):
            elements.append(Paragraph("CERTIFICATIONS", section_title_style))
            elements.append(HorizontalLine(0.6, 0.25))
            
            for cert in resume_data['certifications']:
                # Certification title and date in a table for alignment
                cert_title = cert.get('name', 'Certification')
                cert_date = cert.get('date', '')
                
                cert_table_data = [[
                    Paragraph(cert_title, item_title_style),
                    Paragraph(cert_date, date_style)
                ]]
                
                cert_table = Table(cert_table_data, colWidths=[4.5*inch, 2.3*inch])
                cert_table.setStyle(TableStyle([
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
                ]))
                elements.append(cert_table)
                
                # Issuer
                if cert.get('issuer'):
                    elements.append(Paragraph(cert['issuer'], item_subtitle_style))
                
                # Link
                if cert.get('link'):
                    elements.append(Paragraph(f"Credential: {cert['link']}", normal_style))
                
                elements.append(Spacer(1, 5))
        
        # Add achievements
        if resume_data.get('achievements'):
            elements.append(Paragraph("ACHIEVEMENTS", section_title_style))
            elements.append(HorizontalLine(0.6, 0.25))
            
            for achievement in resume_data['achievements']:
                # Achievement title and date in a table for alignment
                achievement_title = achievement.get('title', 'Achievement')
                achievement_date = achievement.get('date', '')
                
                achievement_table_data = [[
                    Paragraph(achievement_title, item_title_style),
                    Paragraph(achievement_date, date_style)
                ]]
                
                achievement_table = Table(achievement_table_data, colWidths=[4.5*inch, 2.3*inch])
                achievement_table.setStyle(TableStyle([
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
                ]))
                elements.append(achievement_table)
                
                # Description
                if achievement.get('description'):
                    elements.append(Paragraph(achievement['description'], normal_style))
                
                elements.append(Spacer(1, 5))
        
        # Build the PDF
        doc.build(elements, onFirstPage=add_page_number, onLaterPages=add_page_number)
        
        # Get the value of the BytesIO buffer
        pdf_data = buffer.getvalue()
        buffer.close()
        
        # Create a Django-friendly ContentFile
        pdf_content = ContentFile(pdf_data, name='resume.pdf')
        
        return pdf_content
        
    except Exception as e:
        logger.error(f"Error generating PDF: {str(e)}")
        # Fallback to simple text file if PDF generation fails
        try:
            # Create a simple text version of the resume as fallback
            resume_text = f"""
RESUME: {resume_data.get('basics', {}).get('name', user.first_name + ' ' + user.last_name)}
--------------------------------------
Contact: {resume_data.get('basics', {}).get('email', user.email)}
{resume_data.get('basics', {}).get('phone', '')}
{resume_data.get('basics', {}).get('location', '')}

SUMMARY
-------
{resume_data.get('basics', {}).get('summary', '')}

EXPERIENCE
----------
"""
            # Add experience
            for exp in resume_data.get('experience', []):
                resume_text += f"""
{exp.get('position')} at {exp.get('company')}
{exp.get('startDate')} - {exp.get('endDate') if not exp.get('current', False) else 'Present'}
{exp.get('location', '')}
{exp.get('description', '')}
"""
                # Add bullets
                for bullet in exp.get('bullets', []):
                    resume_text += f"- {bullet}\n"
            
            # Add education
            resume_text += f"""
EDUCATION
---------
"""
            for edu in resume_data.get('education', []):
                resume_text += f"""
{edu.get('degree')}, {edu.get('fieldOfStudy')}
{edu.get('institution')}
{edu.get('startDate')} - {edu.get('endDate')}
{edu.get('location', '')}
{edu.get('description', '')}
"""
            
            # Add skills
            resume_text += f"""
SKILLS
------
"""
            skills = resume_data.get('skills', {})
            if skills.get('technical'):
                resume_text += "Technical: " + ", ".join(skills.get('technical', [])) + "\n"
            if skills.get('soft'):
                resume_text += "Soft: " + ", ".join(skills.get('soft', [])) + "\n"
            
            # Add projects
            if resume_data.get('projects'):
                resume_text += f"""
PROJECTS
--------
"""
                for project in resume_data.get('projects', []):
                    resume_text += f"""
{project.get('title')}
{project.get('startDate')} - {project.get('endDate', '')}
Technologies: {project.get('technologies', '')}
{project.get('description', '')}
"""
            
            # Add certifications
            if resume_data.get('certifications'):
                resume_text += f"""
CERTIFICATIONS
-------------
"""
                for cert in resume_data.get('certifications', []):
                    resume_text += f"""
{cert.get('name')} - {cert.get('issuer')}
{cert.get('date')}
"""
            
            # Add achievements
            if resume_data.get('achievements'):
                resume_text += f"""
ACHIEVEMENTS
-----------
"""
                for achievement in resume_data.get('achievements', []):
                    resume_text += f"""
{achievement.get('title')} ({achievement.get('date', '')})
{achievement.get('description', '')}
"""
            
            # Create a text file with .pdf extension as fallback
            fallback_file = io.BytesIO()
            fallback_file.write(resume_text.encode('utf-8'))
            fallback_file.seek(0)
            
            logger.warning("Falling back to text-based PDF due to error in PDF generation")
            return ContentFile(fallback_file.getvalue(), name='resume.pdf')
            
        except Exception as fallback_error:
            logger.error(f"Fallback error: {str(fallback_error)}")
            raise

# Class for creating horizontal lines
class HorizontalLine(Flowable):
    def __init__(self, offset=0, width=1, color=colors.black):
        self.offset = offset
        self.width = width
        self.color = color
        super().__init__()
    
    def wrap(self, *args):
        return (0, 6)
    
    def draw(self):
        self.canv.setStrokeColor(self.color)
        self.canv.setLineWidth(self.width)
        width, height = letter
        self.canv.line(self.offset*inch, 0, width-self.offset*inch, 0)

# Function to add page numbers
def add_page_number(canvas, doc):
    width, height = letter
    canvas.saveState()
    canvas.setFont('Helvetica', 8)
    canvas.setFillColor(colors.grey)
    canvas.drawRightString(width-30, 30, f"Page {doc.page}")
    canvas.restoreState()

def enhance_text_with_ai(text, context, target):
    """
    Use AI to enhance resume text
    
    Args:
        text (str): Text to enhance
        context (str): Context of the text (experience, education, etc.)
        target (str): Target section (bullet, description, etc.)
        
    Returns:
        str: Enhanced text
    """
    try:
        # Check if Gemini API key is configured
        api_key = getattr(settings, 'GEMINI_API_KEY', None)
        if not api_key:
            logger.warning("Gemini API key not configured. Using fallback enhancement.")
            # Return mildly enhanced text as fallback
            return enhance_text_fallback(text, context, target)
        
        # Gemini API endpoint
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
        
        # Create prompt based on context and target
        prompt = create_enhancement_prompt(text, context, target)
        
        # Request body
        data = {
            "contents": [{
                "parts": [{"text": prompt}]
            }],
            "generationConfig": {
                "temperature": 0.5,  # Lower temperature for more predictable output
                "topP": 0.8,
                "topK": 40,
                "maxOutputTokens": 1000
            }
        }
        
        # Send request to Gemini API
        headers = {'Content-Type': 'application/json'}
        response = requests.post(url, headers=headers, json=data, timeout=10)
        
        # Check response status
        if response.status_code == 200:
            # Parse response and extract generated text
            response_data = response.json()
            enhanced_text = response_data['candidates'][0]['content']['parts'][0]['text'].strip()
            
            # Clean up the response - remove any "Option X:" prefixes or explanations
            enhanced_text = clean_enhanced_text(enhanced_text, text)
            
            return enhanced_text
        else:
            logger.error(f"Gemini API error: {response.status_code}, {response.text}")
            return enhance_text_fallback(text, context, target)
        
    except Exception as e:
        logger.error(f"Error enhancing text with AI: {str(e)}")
        # Fallback to basic enhancement
        return enhance_text_fallback(text, context, target)

def create_enhancement_prompt(text, context, target):
    """
    Create prompt for AI text enhancement
    
    Args:
        text (str): Text to enhance
        context (str): Context of the text (experience, education, etc.)
        target (str): Target section (bullet, description, etc.)
        
    Returns:
        str: Prompt for AI
    """
    prompts = {
        'experience': {
            'bullet': f"Rewrite the following resume bullet point to be more impactful, quantifiable, and achievement-oriented. Focus on skills, impact, and results. Use strong action verbs and be concise. Return ONLY the enhanced text without explanations or options: \n\n{text}",
            'description': f"Enhance the following job description for a resume to highlight key responsibilities, achievements, and skills. Make it concise, professional, and impactful. Return ONLY the enhanced text without explanations or options: \n\n{text}"
        },
        'education': {
            'description': f"Improve the following education description for a resume. Highlight relevant coursework, achievements, and skills gained. Return ONLY the enhanced text without explanations or options: \n\n{text}"
        },
        'projects': {
            'description': f"Enhance the following project description for a resume. Focus on technologies used, your role, challenges solved, and outcomes. Return ONLY the enhanced text without explanations or options: \n\n{text}"
        },
        'achievements': {
            'description': f"Rewrite the following achievement for a resume to be more impactful and quantifiable. Highlight the significance of the achievement. Return ONLY the enhanced text without explanations or options: \n\n{text}"
        },
        'basics': {
            'summary': f"Improve the following professional summary for a resume. Make it concise, impactful, and tailored to highlight key strengths and career focus. Do not provide options or explanations - return ONLY the enhanced version of the text: \n\n{text}"
        }
    }
    
    # Get prompt based on context and target
    # If the target starts with 'bullet-', it's a bullet point
    if target.startswith('bullet-'):
        return prompts.get(context, {}).get('bullet', f"Enhance the following text to be more professional, concise, and impactful for a resume. Return ONLY the enhanced text without explanations or options: \n\n{text}")
    
    return prompts.get(context, {}).get(target, f"Enhance the following text to be more professional, concise, and impactful for a resume. Return ONLY the enhanced text without explanations or options: \n\n{text}")

def enhance_text_fallback(text, context, target):
    """
    Fallback method for text enhancement when AI is not available
    
    Args:
        text (str): Text to enhance
        context (str): Context of the text (experience, education, etc.)
        target (str): Target section (bullet, description, etc.)
        
    Returns:
        str: Enhanced text
    """
    # Simple enhancement rules
    enhanced = text
    
    # Replace weak verbs with strong action verbs
    weak_to_strong = {
        'worked on': 'developed',
        'helped': 'facilitated',
        'did': 'executed',
        'made': 'created',
        'responsible for': 'managed',
        'was tasked with': 'spearheaded',
        'got': 'achieved',
        'was part of': 'collaborated on',
    }
    
    for weak, strong in weak_to_strong.items():
        enhanced = enhanced.replace(weak, strong)
        enhanced = enhanced.replace(weak.capitalize(), strong.capitalize())
    
    # Ensure it starts with an action verb if it's a bullet point
    if target.startswith('bullet-') and context == 'experience':
        first_word = enhanced.split(' ')[0].lower()
        action_verbs = ['developed', 'implemented', 'created', 'designed', 'managed', 
                        'led', 'executed', 'coordinated', 'analyzed', 'achieved']
        
        if not any(enhanced.lower().startswith(verb) for verb in action_verbs):
            # Prepend a random action verb if it doesn't start with one
            enhanced = f"{random.choice(action_verbs).capitalize()} {enhanced}"
    
    return enhanced 

def clean_enhanced_text(enhanced_text, original_text):
    """
    Clean up enhanced text from AI to ensure it's directly usable
    
    Args:
        enhanced_text (str): Text enhanced by AI
        original_text (str): Original text before enhancement
        
    Returns:
        str: Cleaned up enhanced text
    """
    # If the response contains multiple options (like "Option 1:", "Option 2:", etc.)
    if "Option 1:" in enhanced_text or "**Option 1" in enhanced_text:
        # Extract the first option
        option_match = None
        
        # Try different pattern matching approaches
        import re
        patterns = [
            r"(?:Option 1:|**Option 1)[:\s]*(.*?)(?:(?:Option \d+:|**Option \d+)|\Z)",
            r"(?:\*\*Option 1\*\*)[:\s]*(.*?)(?:(?:\*\*Option \d+\*\*)|\Z)"
        ]
        
        for pattern in patterns:
            match = re.search(pattern, enhanced_text, re.DOTALL)
            if match:
                option_match = match.group(1).strip()
                break
        
        if option_match:
            enhanced_text = option_match
    
    # Remove markdown formatting
    enhanced_text = enhanced_text.replace('*', '').replace('**', '').replace('#', '').replace('>', '')
    
    # Remove explanations after the enhanced text (often starts with phrases like "This improved version...")
    explanation_starters = [
        "This improved version", 
        "Key Improvements", 
        "Why this works", 
        "This summary", 
        "This version",
        "This enhancement",
        "This emphasizes"
    ]
    
    for starter in explanation_starters:
        if starter in enhanced_text:
            enhanced_text = enhanced_text.split(starter)[0].strip()
    
    # If the result seems too short or empty, return the original
    if len(enhanced_text) < 10:
        return original_text
    
    return enhanced_text 