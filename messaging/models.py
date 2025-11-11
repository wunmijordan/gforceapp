from django.db import models
from django.conf import settings
from django.utils.timezone import now
from guests.models import GuestEntry


class GuestMessage(models.Model):
  STATUS_CHOICES = [
      ('Pending', 'Pending'),
      ('Sent', 'Sent'),
      ('Failed', 'Failed'),
  ]

  sender = models.ForeignKey(
      settings.AUTH_USER_MODEL,
      on_delete=models.CASCADE,
      related_name='sent_guest_messages'
  )
  recipients = models.ManyToManyField(
      GuestEntry,
      related_name='received_messages'
  )
  subject = models.CharField(max_length=255, blank=True)
  body = models.TextField()
  status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
  sent_at = models.DateTimeField(blank=True, null=True)
  created_at = models.DateTimeField(auto_now_add=True)

  def __str__(self):
      return f"{self.sender.full_name or self.sender.username} - {self.subject or 'No Subject'}"

  def send(self):
      """Send message to all recipients and log each delivery."""
      self.sent_at = now()
      self.status = 'Sent'
      self.save()

      for guest in self.recipients.all():
          MessageLog.objects.create(
              message=self,
              guest=guest,
              status='Sent'
          )

  def get_available_recipients(self, user, status_filter=None):
      """Return recipients available to the user, optionally filtered by guest status."""
      if user.role in ['Superuser', 'Admin', 'Message Manager']:
          queryset = GuestEntry.objects.all()
      else:
          queryset = GuestEntry.objects.filter(assigned_to=user)

      if status_filter:
          queryset = queryset.filter(status=status_filter)
      return queryset


class MessageLog(models.Model):
  message = models.ForeignKey(GuestMessage, on_delete=models.CASCADE, related_name='logs')
  guest = models.ForeignKey(GuestEntry, on_delete=models.CASCADE)
  status = models.CharField(max_length=20, choices=GuestMessage.STATUS_CHOICES)
  timestamp = models.DateTimeField(auto_now_add=True)

  def __str__(self):
      return f"{self.guest.full_name} - {self.status}"