from django.contrib import admin
from .models import Contest, Question, Option, Attempt

admin.site.register(Contest)
admin.site.register(Question)
admin.site.register(Option)
admin.site.register(Attempt)
