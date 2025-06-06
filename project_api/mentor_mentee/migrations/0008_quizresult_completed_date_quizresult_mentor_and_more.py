# Generated by Django 4.2.16 on 2025-04-29 19:30

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('mentor_mentee', '0007_quizresult'),
    ]

    operations = [
        migrations.AddField(
            model_name='quizresult',
            name='completed_date',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='quizresult',
            name='mentor',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='assigned_quizzes', to='mentor_mentee.participant'),
        ),
        migrations.AddField(
            model_name='quizresult',
            name='status',
            field=models.CharField(choices=[('pending', 'Pending'), ('completed', 'Completed'), ('expired', 'Expired')], default='pending', max_length=10),
        ),
    ]
