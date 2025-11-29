from django import forms
from .models import Event, Team

class EventForm(forms.ModelForm):
    team = forms.ModelChoiceField(
        queryset=Team.objects.filter(is_active=True),
        required=False,
        empty_label="GForce",
        widget=forms.Select(attrs={"class": "form-select"})
    )
    class Meta:
        model = Event
        fields = [
            "event_image",
            "name",
            "event_type",
            "attendance_mode",
            "day_of_week",
            "postponed",
            "date",
            "duration_days",
            "end_date",
            "time",
            "team",
            "is_active",
            "is_recurring_weekly",
            "registrable",          
            "registration_link",
        ]
        widgets = {
            "event_image": forms.ClearableFileInput(attrs={"class": "form-control bg-gray text-light border-0"}),
            "day_of_week": forms.Select(attrs={"class": "form-select"}),
            "attendance_mode": forms.Select(attrs={"class": "form-select"}),
            "postponed": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "end_date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "time": forms.TimeInput(attrs={"type": "time", "class": "form-control"}),
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "event_type": forms.Select(attrs={"class": "form-select"}),
            "duration_days": forms.NumberInput(attrs={"class": "form-control"}),
            "is_recurring_weekly": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "registrable": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "registration_link": forms.URLInput(attrs={"class": "form-control bg-gray text-light border-0"}),
        }
        help_texts = {
            "duration_days": "Number of days this event lasts",
        }
        labels = {
            "event_image": "Event Banner/Poster",
            "is_recurring_weekly": "Recurring Weekly",
            "is_active": "Active Event",
            "registrable": "Open for Registration",
            "registration_link": "Registration Link",
            "attendance_mode": "Attendance Mode",
            "day_of_week": "Day of the Week",
            "event_type": "Event Type",
            "end_date": "End Date",
            "duration_days": "Duration (Days)",
            "postponed": "Postpone this Event",
        }


from django import forms
from .models import Song, TrackFile, Chart, RehearsalSession

class SongForm(forms.ModelForm):
    class Meta:
        model = Song
        fields = ["title", "subtitle", "composer", "bpm", "key", "notes"]

class TrackFileForm(forms.ModelForm):
    upload = forms.FileField(required=True)
    class Meta:
        model = TrackFile
        fields = ["song", "title", "file", "file_type", "track_type", "order"]

class ChartForm(forms.ModelForm):
    upload = forms.FileField(required=True)
    class Meta:
        model = Chart
        fields = ["song", "title", "file", "notes"]

class RehearsalSessionForm(forms.ModelForm):
    class Meta:
        model = RehearsalSession
        fields = ["team", "title", "songs", "date", "start_time", "end_time", "location", "notes"]
        widgets = {
            "songs": forms.SelectMultiple(attrs={"class":"form-control"}),
            "date": forms.DateInput(attrs={"type":"date","class":"form-control"}),
            "start_time": forms.TimeInput(attrs={"type":"time","class":"form-control"}),
            "end_time": forms.TimeInput(attrs={"type":"time","class":"form-control"}),
        }