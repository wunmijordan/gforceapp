from django.contrib.auth.models import AbstractUser
from django.db import models
from cloudinary.models import CloudinaryField
from django.conf import settings
from django.utils.functional import cached_property


class CustomUser(AbstractUser):
    ROLE_CHOICES = [
        ('Superuser', 'Superuser'),
        ('Admin', 'Admin'),
        ('Pastor', 'Pastor'),
        ('Minister', 'Minister'),
        ('GForce Member', 'GForce Member'),
    ]

    TITLE_CHOICES = [
        ('Bro.', 'Bro.'), ('Min.', 'Min.'), ('Mr.', 'Mr.'),
        ('Mrs.', 'Mrs.'), ('Sis.', 'Sis.'),
    ]

    MARITAL_STATUS_CHOICES = [
        ('Married', 'Married'),
        ('Single', 'Single'),
    ]

    DEPARTMENT_CHOICES = [
        ('Crystal Sounds', 'Crystal Sounds'), ('Embassage', 'Embassage'),
        ('Expressions', 'Expressions'), ('Glitters', 'Glitters'),
        ('Green House', 'Green House'), ('Holy Police', 'Holy Police'),
        ('Magnet', 'Magnet'), ('Media', 'Media'), ('Royal Guards', 'Royal Guards'),
        ('Temple Keepers', 'Temple Keepers'),
    ]

    full_name = models.CharField(max_length=255, blank=True, null=True)
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    image = CloudinaryField('image', blank=True, null=True)
    title = models.CharField(max_length=50, choices=TITLE_CHOICES, blank=True, null=True)
    marital_status = models.CharField(max_length=20, choices=MARITAL_STATUS_CHOICES, blank=True, null=True)
    department = models.CharField(max_length=255, choices=DEPARTMENT_CHOICES, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    date_of_birth = models.CharField(max_length=50, blank=True, null=True)
    is_online = models.BooleanField(default=False)
    role = models.CharField(max_length=30, choices=ROLE_CHOICES, default='Team Member')
    last_active = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.full_name or f"User #{self.pk}"

    @property
    def initials(self):
        if self.full_name:
            return ''.join([name[0].upper() for name in self.full_name.split()[:2]])
        return self.username[0].upper() if self.username else "?"

    @property
    def guest_count(self):
        return self.assigned_guests.count() if hasattr(self, 'assigned_guests') else 0

    @property
    def teams(self):
        """Return all teams where this user has membership."""
        from workforce.models import Team
        return Team.objects.filter(memberships__user=self)
    
    @cached_property
    def color_class(self):
        """Tabler color class for use in UI elements."""
        from workforce.consumers import get_user_color
        return get_user_color(self.id, variant="class")

    @cached_property
    def color_hex(self):
        """Hex color version for canvas/JS/graphs."""
        from workforce.consumers import get_user_color
        return get_user_color(self.id, variant="hex")

    @cached_property
    def color(self):
        """Alias for hex — used in scripts like clock card."""
        return self.color_hex


class TeamMembership(models.Model):
    TEAM_ROLE_CHOICES = [
        ("Minister-in-Charge", "Minister-in-Charge"),
        ("Head of Unit", "Head of Unit"),
        ("Asst. Head of Unit", "Asst. Head of Unit"),
        ("Team Admin", "Team Admin"),
        ("Subleader", "Subleader"),
        ("Member", "Member"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="team_memberships"
    )
    team = models.ForeignKey(
        "workforce.Team",
        on_delete=models.CASCADE,
        related_name="memberships"
    )
    team_role = models.CharField(
        max_length=50,
        choices=TEAM_ROLE_CHOICES,
        default="Member"
    )

    class Meta:
        unique_together = ("user", "team")

    def __str__(self):
        return f"{self.user.full_name or self.user.username} → {self.team.name} ({self.team_role})"
