from django import forms
from django.contrib.auth.forms import ReadOnlyPasswordHashField
from django.contrib.auth.hashers import make_password
from django.core.exceptions import ValidationError
from django.contrib.auth.models import Group
from .models import CustomUser, TeamMembership
from workforce.models import Team


PROJECT_LEVEL_GROUPS = ['Superuser', 'Pastor', 'Minister', 'Admin', 'Member']

class GroupedTeamChoiceField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, obj):
        return obj.name


class CustomUserCreationForm(forms.ModelForm):
    username = forms.CharField(
        label="Username",
        help_text="Username.",
        widget=forms.TextInput(attrs={'class': 'form-control', 'required': 'required', 'placeholder': 'Enter Username'})
    )

    password = forms.CharField(
        label='Password',
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Enter Password'}),
    )
    confirm_password = forms.CharField(
        label='Confirm Password',
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Confirm Password'}),
    )
    group = forms.ModelChoiceField(
        queryset=Group.objects.filter(name__in=PROJECT_LEVEL_GROUPS).order_by('name'),
        required=True,
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'id_group'}),
        label="Project Role",
        help_text="Select user’s project-level role."
    )
    teams = GroupedTeamChoiceField(
        queryset=Team.objects.all(),
        required=False,
        widget=forms.SelectMultiple(attrs={'class': 'form-select team-multiselect'}),
        label="Team Memberships",
        help_text="Assign this user to team(s) and specify team-level role.",
    )
    is_staff = forms.BooleanField(
        required=False,
        label="Staff Status",
    )
    is_active = forms.BooleanField(
        required=False,
        label="Staff Status",
    )
    is_superuser = forms.BooleanField(
        required=False,
        label="Staff Status",
    )

    class Meta:
        model = CustomUser
        fields = [
            'image', 'title', 'full_name', 'email', 'username',
            'password', 'confirm_password', 'phone_number', 'date_of_birth',
            'address', 'marital_status', 'department', 'group', 'teams', 'is_active', 'is_staff', 'is_superuser'
        ]

        widgets = {
            'image': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'title': forms.Select(attrs={'class': 'form-select'}),
            'full_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'John Doe'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'johndoe@magnet.gatewaynation'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '08123xxxx89'}),
            'date_of_birth': forms.DateInput(attrs={
                'type': 'text',
                'class': 'form-control',
                'placeholder': 'January 01 (Ignore Year)',
                'autocomplete': 'off'
            }),
            'marital_status': forms.Select(attrs={'class': 'form-select', 'required': 'required'}),
            'department': forms.Select(attrs={'class': 'form-select', 'placeholder': 'Crystal Sounds'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': '3/4, Francis Aghedo Close, Off Isheri Road, Lagos'}),
        }

        help_texts = {
            'title': 'Title.',
            'image': 'Profile Picture.',
            'full_name': 'Full Name.',
            'phone_number': 'Phone Number.',
            'email': 'Email Address.',
            'date_of_birth': 'Date of Birth.',
            'marital_status': 'Marital Status.',
            'address': 'Home Address.',
            'department': 'Department.',
        }

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        confirm_password = cleaned_data.get("confirm_password")
        if not password or not confirm_password:
            raise ValidationError("Both password fields are required.")
        if password != confirm_password:
            raise ValidationError("Passwords do not match.")
        return cleaned_data

    def save(self, commit=True):
        import re
        user = super().save(commit=False)
        user.password = make_password(self.cleaned_data["password"])

        if commit:
            user.save()

            # ✅ Assign project-level role (Group)
            group = self.cleaned_data.get("group")
            if group:
                user.groups.set([group])
            else:
                user.groups.clear()

            # ✅ Parse team-role pairs from hidden input (cleaner separate format)
            team_data_raw = self.data.get("teamsHiddenInput", "")
            if team_data_raw:
                TeamMembership.objects.filter(user=user).delete()  # clear old links

                pairs = [pair.strip() for pair in team_data_raw.split(",") if ":" in pair]
                for pair in pairs:
                    team_id, role = map(str.strip, pair.split(":", 1))
                    if team_id and role:
                        try:
                            team = Team.objects.get(id=int(team_id))
                            TeamMembership.objects.create(user=user, team=team, team_role=role)
                        except (Team.DoesNotExist, ValueError):
                            continue

        return user

            

    def __init__(self, *args, **kwargs):
        self.current_user = kwargs.pop('current_user', None)
        super().__init__(*args, **kwargs)

        # Hide sensitive fields for non-superusers
        if self.current_user and not self.current_user.is_superuser:
            for f in ['is_staff', 'is_superuser']:
                self.fields.pop(f, None)

        # --- Ensure core project roles exist ---
        project_roles = ["Pastor", "Minister", "Admin", "GForce Member"]
        for role_name in project_roles:
            Group.objects.get_or_create(name=role_name)

        # Only show project-level roles (exclude Superuser + legacy)
        self.fields['group'].queryset = Group.objects.filter(
            name__in=project_roles
        ).order_by('name')

        

        # --- Cosmetic cleanup for dropdown labels ---
        select_fields = ['title', 'marital_status', 'department']
        for field_name in select_fields:
            if field_name in self.fields:
                choices = list(self.fields[field_name].choices)
                if choices and choices[0][0] == '':
                    choices[0] = ("", "")
                else:
                    choices = [("", "")] + choices
                self.fields[field_name].choices = choices



class CustomUserChangeForm(forms.ModelForm):
    username = forms.CharField(
        label="Username",
        help_text="Username.",
        widget=forms.TextInput(attrs={'class': 'form-control', 'required': 'required', 'placeholder': 'Enter Username'})
    )

    password = forms.CharField(
        label='Password',
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Enter New Password'}),
        required=False
    )
    confirm_password = forms.CharField(
        label='Confirm Password',
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Confirm New Password'}),
        required=False
    )
    group = forms.ModelChoiceField(
        queryset=Group.objects.all().order_by('name'),
        required=True,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label="Project Role",
        help_text="Select user’s project-level role."
    )
    teams = GroupedTeamChoiceField(
        queryset=Team.objects.all(),
        required=False,
        widget=forms.SelectMultiple(attrs={'class': 'form-select team-multiselect'}),
        label="Team Memberships",
        help_text="Assign this user to team(s) and specify team-level role.",
    )
    # Add admin fields as checkboxes
    is_staff = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label="Staff Status"
    )
    is_active = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label="Active"
    )
    is_superuser = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label="Superuser"
    )

    class Meta:
        model = CustomUser
        fields = [
            'image', 'title', 'full_name', 'email', 'username', 'password', 'confirm_password',
            'phone_number', 'date_of_birth', 'address', 'marital_status', 'department',
            'group', 'teams', 'is_staff', 'is_active', 'is_superuser'
        ]

        widgets = {
            'image': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'title': forms.Select(attrs={'class': 'form-select'}),
            'full_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'John Doe'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'johndoe@magnet.gatewaynation'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '08123xxxx89'}),
            'date_of_birth': forms.DateInput(attrs={
                'type': 'text',
                'class': 'form-control',
                'placeholder': 'January 01 (Ignore Year)',
                'autocomplete': 'off'
            }),
            'marital_status': forms.Select(attrs={'class': 'form-select'}),
            'department': forms.Select(attrs={'class': 'form-select', 'placeholder': 'Crystal Sounds'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': '3/4, Francis Aghedo Close, Off Isheri Road, Lagos'}),
        }

        help_texts = {
            'title': 'Title.',
            'image': 'Profile Picture.',
            'full_name': 'Full Name.',
            'phone_number': 'Phone Number.',
            'email': 'Email Address.',
            'date_of_birth': 'Date of Birth.',
            'marital_status': 'Marital Status.',
            'address': 'Home Address.',
            'department': 'Department.',
        }

    def __init__(self, *args, **kwargs):
        self.current_user = kwargs.pop('current_user', None)
        self.edit_mode = kwargs.pop('edit_mode', False)
        super().__init__(*args, **kwargs)

        # --- Hide sensitive fields for non-superusers ---
        if self.current_user and not self.current_user.is_superuser:
            for f in ['is_staff', 'is_superuser']:
                self.fields.pop(f, None)

        # --- Ensure project-level roles exist ---
        project_roles = ["Pastor", "Minister", "Admin", "GForce Member"]
        for role_name in project_roles:
            Group.objects.get_or_create(name=role_name)

        # --- Limit group queryset to only those roles (exclude Superuser + legacy) ---
        self.fields['group'].queryset = Group.objects.filter(
            name__in=project_roles
        ).order_by('name')

        # --- Preselect current user's group ---
        if self.instance.pk:
            groups = self.instance.groups.all()
            if groups.exists():
                self.fields['group'].initial = groups.first().id

        # --- FRONTEND restrictions ---
        if self.edit_mode and self.current_user:
            if not self.current_user.is_superuser:
                # Non-superuser staff: hide / disable sensitive fields
                for f in ['is_staff', 'is_superuser']:
                    if f in self.fields:
                        self.fields.pop(f)

        

        # --- Make dropdowns look consistent ---
        select_fields = ['title', 'marital_status', 'department']
        for field_name in select_fields:
            if field_name in self.fields:
                choices = list(self.fields[field_name].choices)
                if choices and choices[0][0] == '':
                    choices[0] = ("", "")
                else:
                    choices = [("", "")] + choices
                self.fields[field_name].choices = choices


    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        confirm_password = cleaned_data.get("confirm_password")

        if password or confirm_password:
            if password != confirm_password:
                raise ValidationError("Passwords do not match.")
        return cleaned_data

    def save(self, commit=True):
        import re
        user = super().save(commit=False)
        password = self.cleaned_data.get("password")
        if password:
            user.password = make_password(password)
        else:
            user.password = CustomUser.objects.get(pk=self.instance.pk).password

        if commit:
            user.save()

            # ✅ Update project-level role
            group = self.cleaned_data.get("group")
            if group:
                user.groups.set([group])
            else:
                user.groups.clear()

            # ✅ Update team-role pairs
            team_data_raw = self.data.get("teamsHiddenInput", "")
            TeamMembership.objects.filter(user=user).delete()

            if team_data_raw:
                pairs = [pair.strip() for pair in team_data_raw.split(",") if ":" in pair]
                for pair in pairs:
                    team_id, role = map(str.strip, pair.split(":", 1))
                    if team_id and role:
                        try:
                            team = Team.objects.get(id=int(team_id))
                            TeamMembership.objects.create(user=user, team=team, team_role=role)
                        except (Team.DoesNotExist, ValueError):
                            continue

        return user




class GroupForm(forms.ModelForm):
    class Meta:
        model = Group
        fields = ['name']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter group name'
            })
        }


