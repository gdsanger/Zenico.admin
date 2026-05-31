from django.contrib import admin

from crm.models import Contact, EducationRequest

# Register your models here.
@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = ('first_name', 'last_name', 'email', 'status', 'assigned_to')
    list_filter = ('status', 'source')
    search_fields = ('first_name', 'last_name', 'email', 'company')
    ordering = ('-id',)

@admin.register(EducationRequest)
class EducationRequestAdmin(admin.ModelAdmin):
    list_display = ('institution_name', 'institution_type', 'email', 'website', 'user_count', 'status')
    list_filter = ('institution_type', 'status','user_count')
    search_fields = ('institution_name', 'email', 'website', 'status')
    ordering = ('-id',)