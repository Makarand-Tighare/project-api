# Generated by Django 4.2.16 on 2024-10-12 14:14

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('mentor_mentee', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='participant',
            name='extracurricular_activities',
            field=models.CharField(blank=True, choices=[('yes', 'Yes'), ('no', 'No')], max_length=3, null=True),
        ),
        migrations.AlterField(
            model_name='participant',
            name='hackathon_role',
            field=models.CharField(blank=True, choices=[('team leader', 'Team Leader'), ('member', 'Member')], max_length=20, null=True),
        ),
        migrations.AlterField(
            model_name='participant',
            name='level_of_competition',
            field=models.CharField(blank=True, choices=[('International', 'International'), ('National', 'National'), ('College', 'College'), ('Conferences', 'Conferences'), ('None', 'None')], max_length=15, null=True),
        ),
        migrations.AlterField(
            model_name='participant',
            name='number_of_coding_competitions',
            field=models.IntegerField(blank=True, default=0, null=True, validators=[django.core.validators.MinValueValidator(0)]),
        ),
        migrations.AlterField(
            model_name='participant',
            name='number_of_internships',
            field=models.IntegerField(blank=True, default=0, null=True, validators=[django.core.validators.MinValueValidator(0)]),
        ),
        migrations.AlterField(
            model_name='participant',
            name='number_of_participations',
            field=models.IntegerField(blank=True, default=0, null=True, validators=[django.core.validators.MinValueValidator(0)]),
        ),
        migrations.AlterField(
            model_name='participant',
            name='number_of_wins',
            field=models.IntegerField(blank=True, default=0, null=True, validators=[django.core.validators.MinValueValidator(0)]),
        ),
        migrations.AlterField(
            model_name='participant',
            name='seminars_or_workshops_attended',
            field=models.CharField(blank=True, choices=[('yes', 'Yes'), ('no', 'No')], max_length=3, null=True),
        ),
    ]
