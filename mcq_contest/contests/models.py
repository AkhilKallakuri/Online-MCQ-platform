from django.db import models
from django.contrib.auth.models import User

class Contest(models.Model):
    name = models.CharField(max_length=200)
    start_datetime = models.DateTimeField()
    end_datetime = models.DateTimeField()
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name

class Question(models.Model):
    contest = models.ForeignKey(Contest, on_delete=models.CASCADE)
    description = models.TextField()
    score = models.IntegerField(default=1)

    def __str__(self):
        return self.description

class Option(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    text = models.CharField(max_length=200)
    is_correct = models.BooleanField(default=False)

    def __str__(self):
        return self.text

class Attempt(models.Model):
    contest = models.ForeignKey(Contest, on_delete=models.CASCADE)
    student = models.ForeignKey(User, on_delete=models.CASCADE)
    total_score = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.student.username} - {self.contest.name} - {self.total_score}"
