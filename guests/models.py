import re
from django.db import models
from django.conf import settings
from django.utils.timezone import localdate
from cloudinary.models import CloudinaryField


class GuestEntry(models.Model):
  TITLE_CHOICES = [
    ('Chief', 'Chief'), ('Dr.', 'Dr.'), ('Engr.', 'Engr.'),
    ('Mr.', 'Mr.'), ('Mrs.', 'Mrs.'), ('Ms.', 'Ms.'),
    ('Pastor', 'Pastor'), ('Prof.', 'Prof.'),
  ]
  GENDER_CHOICES = [('Male', 'Male'), ('Female', 'Female')]
  AGE_RANGE_CHOICES = [
    ("Under 18", "Under 18"),
    ("18–25", "18–25"),
    ("26–35", "26–35"),
    ("36–45", "36–45"),
    ("46 and Above", "46 and Above"),
  ]
  MARITAL_STATUS_CHOICES = [
    ('Single', 'Single'), ('Married', 'Married'),
  ]
  PURPOSE_CHOICES = [
    ('Home Church', 'Home Church'), ('Occasional Visit', 'Occasional Visit'),
    ('One-Time Visit', 'One-Time Visit'), ('Special Programme Visit', 'Special Programme Visit'),
  ]
  CHANNEL_CHOICES = [
    ('Billboard (Grammar School)', 'Billboard (Grammar School)'),
    ('Billboard (Kosoko)', 'Billboard (Kosoko)'),
    ('Billboard (Ojodu)', 'Billboard (Ojodu)'),
    ('Facebook', 'Facebook'), ('Family & Friends', 'Family & Friends'), ('Flyer', 'Flyer'), ('Instagram', 'Instagram'),
    ('Referral', 'Referral'), ('Self', 'Self'), ('Visit', 'Visit'),
    ('YouTube', 'YouTube'), ('Others', 'Others'),
  ]
  SERVICE_CHOICES = [
    ('Black Ball', 'Black Ball'), ('Breakthrough Campaign', 'Breakthrough Campaign'),
    ('Breakthrough Festival', 'Breakthrough Festival'), ('Code Red. Revival', 'Code Red. Revival'),
    ('Cross Over', 'Cross Over'), ('Deep Dive', 'Deep Dive'), ('Family Hangout', 'Family Hangout'),
    ('Forecasting', 'Forecasting'), ('Life Masterclass', 'Life Masterclass'), ('Love Lounge', 'Love Lounge'),
    ('Midweek Recharge', 'Midweek Recharge'), ('Midyear Praise Party', 'Midyear Praise Party'),
    ('Outreach', 'Outreach'), ('Praise Party', 'Praise Party'), ('Quantum Leap', 'Quantum Leap'),
    ('Recalibrate Marathon', 'Recalibrate Marathon'), ('Singles Connect', 'Singles Connect'),
    ('Supernatural Encounter', 'Supernatural Encounter'),
  ]
  STATUS_CHOICES = [
    ('Planted', 'Planted'),
    ('Planted Elsewhere', 'Planted Elsewhere'), ('Relocated', 'Relocated'),
    ('Work in Progress', 'Work in Progress'),
  ]

  picture = CloudinaryField('image', blank=True, null=True)
  custom_id = models.CharField(max_length=20, unique=True, blank=True, null=True, editable=False)
  title = models.CharField(max_length=20, choices=TITLE_CHOICES, blank=False)
  full_name = models.CharField(max_length=100)
  gender = models.CharField(max_length=10, choices=GENDER_CHOICES, blank=False)
  phone_number = models.CharField(max_length=20, blank=True, null=True)
  email = models.EmailField(blank=True)
  date_of_birth = models.CharField(blank=True, null=True)
  age_range = models.CharField(max_length=20, choices=AGE_RANGE_CHOICES, blank=True)
  marital_status = models.CharField(max_length=20, choices=MARITAL_STATUS_CHOICES, blank=True)
  home_address = models.TextField(blank=True)
  occupation = models.CharField(max_length=100, blank=True)
  date_of_visit = models.DateField(default=localdate)
  purpose_of_visit = models.CharField(max_length=30, choices=PURPOSE_CHOICES, blank=True)
  channel_of_visit = models.CharField(max_length=30, choices=CHANNEL_CHOICES, blank=True)
  service_attended = models.CharField(max_length=50, choices=SERVICE_CHOICES, blank=False)
  referrer_name = models.CharField(max_length=100, blank=True)
  referrer_phone_number = models.CharField(max_length=20, blank=True)
  message = models.TextField(blank=True)
  status = models.CharField(max_length=30, choices=STATUS_CHOICES)

  assigned_to = models.ForeignKey(
    settings.AUTH_USER_MODEL,
    null=True, blank=True,
    on_delete=models.SET_NULL,
    related_name='assigned_guests'
  )
  assigned_at = models.DateTimeField(null=True, blank=True, editable=False)


  def save(self, *args, **kwargs):
    if self.assigned_to and not self.assigned_at:
        from django.utils.timezone import now
        self.assigned_at = now()

    if not self.custom_id:
      prefix = 'GNG'
      last_guest = GuestEntry.objects.filter(custom_id__startswith=prefix).order_by('-custom_id').first()
      if last_guest and last_guest.custom_id:
        last_num = int(re.sub(r'^\D+', '', last_guest.custom_id))
        new_num = last_num + 1
      else:
        new_num = 1
      self.custom_id = f'{prefix}{new_num:06d}'
    super().save(*args, **kwargs)

  @property
  def initials(self):
    if self.full_name:
      return ''.join([n[0].upper() for n in self.full_name.split()[:2]])
    return 'G'

  def get_status_color(self):
    return {
      'Planted': 'success',
      'Planted Elsewhere': 'danger',
      'Relocated': 'primary',
      'Work in Progress': 'warning',
      'New Guest': 'gray-800',
    }.get(self.status, 'gray-800')

  def __str__(self):
    return f"{self.custom_id} - {self.full_name}"

class SocialMediaEntry(models.Model):
    SOCIAL_MEDIA_CHOICES = [
        ('whatsapp', 'WhatsApp'),
        ('instagram', 'Instagram'),
        ('twitter', 'Twitter'),
        ('linkedin', 'LinkedIn'),
        ('tiktok', 'Tiktok'),
    ]
    guest = models.ForeignKey(
        GuestEntry,
        on_delete=models.CASCADE,
        related_name='social_media_accounts'
    )
    platform = models.CharField(max_length=20, choices=SOCIAL_MEDIA_CHOICES)
    handle = models.CharField(max_length=255)

    def save(self, *args, **kwargs):
        base_urls = {
            'linkedin': 'https://www.linkedin.com/in/',
            'whatsapp': 'https://wa.me/',
            'instagram': 'https://www.instagram.com/',
            'twitter': 'https://twitter.com/',
            'tiktok': 'https://www.tiktok.com/@',
        }
        if self.platform in base_urls and not self.handle.startswith("http"):
            self.handle = base_urls[self.platform] + self.handle.lstrip("@")
        super().save(*args, **kwargs)


class FollowUpReport(models.Model):
    guest = models.ForeignKey(GuestEntry, on_delete=models.CASCADE, related_name='reports')
    report_date = models.DateField(default=localdate)
    note = models.TextField()
    service_sunday = models.BooleanField(default=False)
    service_midweek = models.BooleanField(default=False)
    service_others = models.BooleanField(default=False)
    reviewed = models.BooleanField(default=False)
    
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='assigned_reports'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-report_date']
        unique_together = ['guest', 'report_date']

    def __str__(self):
        return f"{self.guest.full_name} - {self.report_date}"


class Review(models.Model):
    guest = models.ForeignKey(GuestEntry, on_delete=models.CASCADE, related_name="reviews")
    reviewer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    role = models.CharField(
        max_length=20,
        choices=[("pastor", "Pastor"), ("team_lead", "Team Lead")]
    )
    comment = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.CASCADE, related_name="replies")
    is_read = models.BooleanField(default=False)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.role} review on {self.guest.full_name}"

    @property
    def has_unread_reviews(self):
        return self.reviews.filter(is_read=False).exists()