from django import forms
from .models import GuestEntry, FollowUpReport
from django.core.exceptions import ValidationError
import datetime
from django.utils.timezone import localdate
from django.contrib.auth import get_user_model
from workforce.models import Team
from accounts.models import CustomUser as User, TeamMembership
from accounts.utils import is_project_admin, is_magnet_admin

User = get_user_model()

class GuestEntryForm(forms.ModelForm):
    assigned_to = forms.ModelChoiceField(
        queryset=User.objects.none(),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select bg-grey text-white border-0'})
    )

    date_of_birth = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'January 01 (Ignore Year)',
        }),
        help_text="Date of Birth."
    )

    date_of_visit = forms.DateField(
        widget=forms.DateInput(format='%Y-%m-%d', attrs={
            'type': 'date',
            'class': 'form-control',
            'autocomplete': 'off',
        }),
        help_text="Date of Visit.",
        input_formats=['%Y-%m-%d', '%d/%m/%Y'],  # support input formats for validation
        required=False,
    )

    class Meta:
        model = GuestEntry
        exclude = ['status', 'custom_id']
        widgets = {
            'picture': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'title': forms.Select(attrs={'class': 'form-select'}),
            'full_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'John Doe'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'johndoe@guest.gatewaynation.org'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '08123xxxx89'}),
            'date_of_birth': forms.TextInput(attrs={
                'type': 'text',
                'class': 'form-control',
                'placeholder': 'January 01 (Ignore Year)',
                'autocomplete': 'off'
            }),
            'age_range': forms.Select(attrs={'class': 'form-select'}),
            'marital_status': forms.Select(attrs={'class': 'form-select'}),
            'gender': forms.Select(attrs={'class': 'form-select', 'required': 'required'}),
            'occupation': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Manager'}),
            'home_address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': '3/4, Francis Aghedo Close, Off Isheri Road, Lagos'}),
            'date_of_visit': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date', 'class': 'form-control'}),
            'purpose_of_visit': forms.Select(attrs={'class': 'form-select'}),
            'channel_of_visit': forms.Select(attrs={'class': 'form-select'}),
            'service_attended': forms.Select(attrs={'class': 'form-select'}),
            'referrer_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Sis. Jane Doe'}),
            'referrer_phone_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '08123xxxx89'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'message': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Write any additional notes about the Guest here...'}),
            'assigned_to': forms.Select(attrs={'class': 'form-select'}),
        }
        
        
        labels = {
            'title': 'Title',
            'picture': 'Profile Picture',
            'full_name': 'Full Name',
            'phone_number': 'Phone Number',
            'email': 'Email Address',
            'date_of_birth': 'Date of Birth',
            'marital_status': 'Marital Status',
            'occupation': 'Occupation',
            'date_of_visit': 'Date of Visit',
            'purpose_of_visit': 'Purpose of Visit',
            'channel_of_visit': 'Channel of Visit',
            'service_attended': 'Service Attended',
            'referrer_name': 'Referrer Name',
            'referrer_phone_number': 'Referrer Phone Number',
            'message': 'Additional Notes',
            'assigned_to': 'Assign to Team Member',
        }
        

        help_texts = {
            'title': 'Title.',
            'picture': 'Guest\'s Picture.',
            'gender': 'Gender.',
            'full_name': 'Full Name.',
            'phone_number': 'Phone Number.',
            'email': 'Email Address.',
            'date_of_birth': 'Date of Birth.',
            'age_range': 'Select the Guest\'s Age Range.',
            'marital_status': 'Marital Status.',
            'home_address': 'Home Address.',
            'occupation': 'Occupation.',
            'date_of_visit': 'Date of Visit.',
            'purpose_of_visit': 'Purpose of Visit.',
            'channel_of_visit': 'How did the Guest found out about us?',
            'service_attended': 'What Service did the Guest Attend?',
            'referrer_name': 'Who referred the Guest?',
            'referrer_phone_number': 'Referrer\'s Phone Number.',
            'message': 'Additional Notes.',
            'assigned_to': 'Assign this Guest to a Team Member.',
        }


    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        # Only show 'assigned_to' for magnet admins or project admins
        if user and (is_project_admin(user) or is_magnet_admin(user, "Minister-in-Charge,Team Admin")):
            magnet_team = Team.objects.filter(name__iexact="magnet").first()

            if magnet_team:
                # Get IDs of all members in the Magnet team
                magnet_user_ids = TeamMembership.objects.filter(
                    team=magnet_team
                ).values_list("user_id", flat=True)

                # Filter only active users in Magnet team
                qs = User.objects.filter(
                    id__in=magnet_user_ids,
                    is_active=True
                ).exclude(is_superuser=True)

                # Exclude project admins (Pastor/Admin roles)
                qs = [u for u in qs if not is_project_admin(u)]

                # Convert back to QuerySet
                self.fields["assigned_to"].queryset = User.objects.filter(
                    id__in=[u.id for u in qs]
                ).order_by("full_name")

                self.fields["assigned_to"].required = True

                # Label: "Title Full Name"
                self.fields["assigned_to"].label_from_instance = (
                    lambda obj: f"{obj.title or ''} {obj.full_name}".strip()
                )
            else:
                self.fields.pop("assigned_to", None)
        else:
            self.fields.pop("assigned_to", None)


        # ---------------------------
        # Handle select fields to allow blank choices
        # ---------------------------
        select_fields = ['title', 'marital_status', 'gender', 'purpose_of_visit',
                        'channel_of_visit', 'service_attended', 'status', 'age_range', 'assigned_to']

        for field_name in select_fields:
            if field_name in self.fields:
                choices = list(self.fields[field_name].choices)
                if choices and choices[0][0] == '':
                    choices[0] = ("", "")
                else:
                    choices = [("", "")] + choices
                self.fields[field_name].choices = choices

        # ---------------------------
        # Format initial date_of_visit
        # ---------------------------
        if self.instance and self.instance.date_of_visit:
            self.fields['date_of_visit'].initial = self.instance.date_of_visit.strftime('%Y-%m-%d')

    def clean_phone_number(self):
        phone = self.cleaned_data.get('phone_number')
        if phone and not phone.isdigit():
            raise ValidationError("Phone number must contain only digits.")
        return phone

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email and '@' not in email:
            raise ValidationError("Enter a valid email address.")
        return email

    def clean_date_of_birth(self):
        dob_raw = self.cleaned_data.get('date_of_birth')
        if not dob_raw:
            return ""

        try:
            # Parse to ensure format is valid
            dob_parsed = datetime.datetime.strptime(dob_raw, "%B %d")
            # Return formatted string only (e.g. "April 01")
            return dob_parsed.strftime("%B %d")
        except ValueError:
            raise forms.ValidationError("Enter date in format: January 01")


class FollowUpReportForm(forms.ModelForm):
    report_date = forms.DateField(
        widget=forms.DateInput(
            format='%Y-%m-%d',
            attrs={
                'type': 'date',
                'class': 'form-control bg-grey text-white border-0',
            }
        ),
        input_formats=['%Y-%m-%d', '%d/%m/%Y'],
        required=False,
    )

    class Meta:
        model = FollowUpReport
        exclude = ['guest', 'assigned_to', 'created_at']
        widgets = {
            'note': forms.Textarea(attrs={
                'class': 'form-control',
                'placeholder': 'Enter Report Here...',
                'rows': 6,
            }),
            'service_sunday': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'service_midweek': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'service_others': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        self.guest = kwargs.pop('guest', None)
        super().__init__(*args, **kwargs)

        if self.instance.pk:  # Editing existing report
            if self.instance.report_date:
                self.initial['report_date'] = self.instance.report_date.strftime('%Y-%m-%d')
            # Make report_date readonly + style
            self.fields['report_date'].widget.attrs.update({
                'readonly': True,
                'class': self.fields['report_date'].widget.attrs.get('class', '') + ' bg-secondary text-dark fw-bold'
            })
        else:  # New report
            if not self.initial.get('report_date'):
                today = localdate()
                self.initial['report_date'] = today.strftime('%Y-%m-%d')

    def clean(self):
        cleaned_data = super().clean()
        report_date = cleaned_data.get('report_date')

        if self.guest and FollowUpReport.objects.filter(guest=self.guest, report_date=report_date).exclude(pk=self.instance.pk).exists():
            raise ValidationError("You already submitted a report for this date.")

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.guest:
            instance.guest = self.guest
            instance.assigned_to = self.guest.assigned_to
        if commit:
            instance.save()
        return instance




    

