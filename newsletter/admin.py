from django.contrib import admin

from .models import Subscriber, Campaign

# Register your models here.
@admin.register(Subscriber)
class SubscriberAdmin(admin.ModelAdmin):
    list_display = ('first_name', 'last_name', 'email', 'status', 'source')
    list_filter = ('status', 'source')
    search_fields = ('first_name', 'last_name', 'email')
    ordering = ('-id',)

@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = ('name', 'subject', 'segment', 'status')
    list_filter = ('segment', 'status')
    search_fields = ('name', 'subject', 'segment', 'status')
    ordering = ('-id',)