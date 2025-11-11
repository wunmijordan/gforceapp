from django.db import models
from django.conf import settings
from django.utils import timezone
from django.utils.timezone import now
from cloudinary.models import CloudinaryField
from guests.models import GuestEntry
from django.utils.functional import cached_property


CHURCH_COORDS = (6.641732871081892, 3.3706539797031843)  # (latitude, longitude)


class Team(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    color = models.CharField(max_length=20, default="#2e303e")  # dark grey theme default
    icon = models.CharField(max_length=50, blank=True, null=True)  # optional Tabler icon name
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Old ManyToMany (keep temporarily to preserve existing relationships)
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="teams",
        blank=True
    )
    admins = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="admin_teams",
        blank=True
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def member_count(self):
        return self.members.count()

    @property
    def users(self):
        """
        Return all CustomUsers linked through TeamMembership.
        (Overrides old alias but keeps same template usage.)
        """
        from accounts.models import CustomUser
        return CustomUser.objects.filter(team_memberships__team=self)
    
    @cached_property
    def color_class(self):
        """Return the Tabler CSS class version of the team's color."""
        from .consumers import get_team_color
        return get_team_color(self.id or self.name, variant="class")

    @cached_property
    def color_hex(self):
        """Return the HEX version of the team's color."""
        from .consumers import get_team_color
        return get_team_color(self.id or self.name, variant="hex")

    @cached_property
    def color(self):
        """Return both class and hex as a dict."""
        from .consumers import get_team_color
        return get_team_color(self.id or self.name, variant="both")


    

class ChatMessage(models.Model):
  """
  Shared chat model across all workforce teams (including Magnet).
  Supports message threads, guest cards, and pinned messages.
  """

  sender = models.ForeignKey(
      settings.AUTH_USER_MODEL,
      on_delete=models.CASCADE,
      related_name="sent_chats",
      db_index=True
  )

  team = models.ForeignKey(
      "workforce.Team",
      on_delete=models.CASCADE,
      related_name="messages",
      null=True,
      blank=True,
      db_index=True,
      help_text="Team room (null = central chat)"
  )

  parent = models.ForeignKey(
      "self",
      null=True,
      blank=True,
      on_delete=models.CASCADE,
      related_name="replies",
      db_index=True
  )

  message = models.TextField(blank=True, null=True)
  voice_note = models.FileField(upload_to="chat_voice/", blank=True, null=True)

  guest_card = models.ForeignKey(
      GuestEntry,
      null=True,
      blank=True,
      on_delete=models.SET_NULL,
      related_name="chat_messages",
      db_index=True
  )

  created_at = models.DateTimeField(auto_now_add=True, db_index=True)
  #edited = models.BooleanField(default=False)
  #edited_at = models.DateTimeField(null=True, blank=True)
  #deleted = models.BooleanField(default=False)
  seen_by = models.ManyToManyField(
      settings.AUTH_USER_MODEL,
      related_name="seen_messages",
      blank=True
  )

  # Attachments
  file = CloudinaryField("file", folder="chat/files", blank=True, null=True)
  file_type = models.CharField(max_length=100, blank=True, null=True)

  # Link preview
  link_url = models.URLField(max_length=500, blank=True, null=True)
  link_title = models.CharField(max_length=255, blank=True, null=True)
  link_description = models.TextField(blank=True, null=True)
  link_image = models.URLField(max_length=500, blank=True, null=True)

  # Pinning
  pinned = models.BooleanField(default=False, db_index=True)
  pinned_at = models.DateTimeField(null=True, blank=True, db_index=True)
  pinned_by = models.ForeignKey(
      settings.AUTH_USER_MODEL,
      null=True,
      blank=True,
      on_delete=models.SET_NULL,
      related_name="pinned_messages"
  )

  class Meta:
    db_table = 'accounts_chatmessage'  # old table name
    ordering = ['-created_at']

  class Meta:
      ordering = ["-created_at"]
      indexes = [
          models.Index(fields=["created_at"]),
          models.Index(fields=["sender", "created_at"]),
          models.Index(fields=["guest_card", "created_at"]),
          models.Index(fields=["team", "created_at"]),
      ]

  def __str__(self):
      return f"{self.sender} → {self.team or 'Central'}: {self.message[:30]}"

  @property
  def is_expired(self):
      if not self.pinned or not self.pinned_at:
          return False
      return (now() - self.pinned_at).days > 14

  def is_seen_by_all(self):
      from accounts.models import CustomUser
      total_users = CustomUser.objects.count()
      return self.seen_by.count() >= (total_users - 1)



class Event(models.Model):
  EVENT_TYPES = [
      ('Service', 'Service'),
      ('Followup', 'Guest Follow-up'),
      ('Meeting', 'Meeting'),
      ('Training', 'Training'),
      ('Other', 'Other'),
  ]

  ATTENDANCE_MODE_CHOICES = [
      ("Physical", "Physical"),
      ("Virtual", "Virtual"),
  ]

  name = models.CharField(max_length=255)
  event_type = models.CharField(max_length=50, choices=EVENT_TYPES)
  day_of_week = models.CharField(
      max_length=20,
      choices=[
          ('Sunday', 'Sunday'),
          ('Monday', 'Monday'),
          ('Tuesday', 'Tuesday'),
          ('Wednesday', 'Wednesday'),
          ('Thursday', 'Thursday'),
          ('Friday', 'Friday'),
          ('Saturday', 'Saturday'),
      ],
      null=True,
      blank=True
  )
  attendance_mode = models.CharField(
      max_length=10,
      choices=ATTENDANCE_MODE_CHOICES,
      default="physical"
  )
  date = models.DateField(null=True, blank=True)  # floating events
  end_date = models.DateField(null=True, blank=True)  # optional for multi-day
  time = models.TimeField(null=True, blank=True)
  duration_days = models.PositiveIntegerField(default=1, help_text="Number of days this event lasts")
  is_recurring_weekly = models.BooleanField(default=False)
  is_active = models.BooleanField(default=True)
  event_image = CloudinaryField("event_image", folder="events", blank=True, null=True)
  registrable = models.BooleanField(default=False, help_text="If True, allows users to register for this event")
  registration_link = models.URLField(max_length=500, blank=True, null=True, help_text="URL to the event registration page")
  postponed = models.BooleanField(default=False)
  created_by = models.ForeignKey(
      settings.AUTH_USER_MODEL,
      on_delete=models.SET_NULL,
      null=True,
      blank=True,
  )
  team = models.ForeignKey(
        "workforce.Team",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="events",
        help_text="Leave blank for general church-wide events",
    )
  
  class Meta:
      db_table = 'accounts_event'  # old table name
      ordering = ['date', 'day_of_week', 'time']

  class Meta:
      verbose_name = "Event"
      verbose_name_plural = "Events"
      ordering = ['date', 'day_of_week', 'time']

  def __str__(self):
      return f"{self.name} ({self.get_event_type_display()})"



class AttendanceRecord(models.Model):
  STATUS_CHOICES = [
      ('present', 'Present'),
      ('late', 'Late'),
      ('excused', 'Excused'),
      ('absent', 'Absent'),
  ]

  user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='attendance_records')
  event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='attendance_records')
  team = models.ForeignKey(
        "workforce.Team",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="attendance_records",
        help_text="If event is team-specific, store which team",
    )
  date = models.DateField(default=timezone.localdate)
  status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='absent')
  remarks = models.TextField(blank=True)
  timestamp = models.DateTimeField(auto_now_add=True)

  class Meta:
      db_table = 'accounts_attendancerecord'  # old table name
      ordering = ['-date']

  class Meta:
      unique_together = ('user', 'event', 'date')
      ordering = ['-date']

  def __str__(self):
      return f"{self.user} - {self.event.name} ({self.date})"
  


class ClockRecord(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="clock_records")
    team = models.ForeignKey(
        "workforce.Team",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="clock_records"
    )
    event = models.ForeignKey(
        Event,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="clock_records"
    )
    clock_in = models.DateTimeField(null=True, blank=True)
    clock_out = models.DateTimeField(null=True, blank=True)
    date = models.DateField(default=timezone.localdate)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ("user", "date", "event")
        ordering = ["-date"]

    @property
    def is_clocked_in(self):
        return bool(self.clock_in and not self.clock_out)

    def mark_clock_in(self):
        self.clock_in = timezone.now()
        self.is_active = True
        self.save()

    def mark_clock_out(self):
        self.clock_out = timezone.now()
        self.is_active = False
        self.save()



class PersonalReminder(models.Model):
  user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
  title = models.CharField(max_length=255)
  description = models.TextField(blank=True)
  date = models.DateField()
  time = models.TimeField(null=True, blank=True)
  is_done = models.BooleanField(default=False)

  class Meta:
      db_table = 'accounts_personalreminder'  # old table name
      ordering = ['date', 'time']

  class Meta:
      ordering = ['date', 'time']

  def __str__(self):
      return f"{self.user} - {self.title} ({self.date})"
  


class UserActivity(models.Model):
  ACTIVITY_TYPES = [
      ("followup", "Follow-up"),
      ("message", "Message Sent"),
      ("guest_view", "Viewed Guest"),
      ("call", "Called Guest"),
      ("report", "Submitted Report"),
      ("other", "Other"),
  ]

  user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="activities")
  activity_type = models.CharField(max_length=50, choices=ACTIVITY_TYPES)
  guest_id = models.CharField(max_length=50, blank=True, null=True)  # Optional
  description = models.TextField(blank=True, null=True)
  created_at = models.DateTimeField(default=timezone.now)

  class Meta:
      db_table = 'accounts_useractivity'  # old table name
      ordering = ['-created_at']

  class Meta:
      ordering = ["-created_at"]
      verbose_name_plural = "User Activities"

  def __str__(self):
      return f"{self.user} - {self.activity_type} ({self.created_at.strftime('%Y-%m-%d')})"