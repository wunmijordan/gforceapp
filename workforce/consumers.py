import json, re, urllib.parse, logging, hashlib
from datetime import timedelta
from django.utils.timezone import now
from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async
from django.conf import settings
from django.core.files.storage import default_storage
from django.utils import timezone


logger = logging.getLogger(__name__)

# =================== Helpers ===================
def get_user_color(user_id, variant="class"):
    """Return a user's color as a Tabler class, HEX, or both."""
    color_pairs = [
        ("bg-blue-lt text-white", "#3b82f6"),
        ("bg-green-lt text-white", "#22c55e"),
        ("bg-orange-lt text-white", "#fb923c"),
        ("bg-purple-lt text-white", "#8b5cf6"),
        ("bg-pink-lt text-white", "#ec4899"),
        ("bg-cyan-lt text-white", "#06b6d4"),
        ("bg-yellow-lt text-white", "#eab308"),
        ("bg-red-lt text-white", "#ef4444"),
        ("bg-indigo-lt text-white", "#6366f1"),
        ("bg-teal-lt text-white", "#14b8a6"),
        ("bg-lime-lt text-white", "#84cc16"),
        ("bg-amber-lt text-white", "#f59e0b"),
        ("bg-fuchsia-lt text-white", "#d946ef"),
        ("bg-emerald-lt text-white", "#10b981"),
        ("bg-violet-lt text-white", "#8b5cf6"),
        ("bg-rose-lt text-white", "#f43f5e"),
        ("bg-sky-lt text-white", "#0ea5e9"),
        ("bg-orange-200 text-white", "#fdba74"),
        ("bg-purple-200 text-white", "#c4b5fd"),
        ("bg-pink-200 text-white", "#f9a8d4"),
    ]

    color_class, hex_color = color_pairs[user_id % len(color_pairs)]

    if variant == "hex":
        return hex_color
    elif variant == "both":
        return {"class": color_class, "hex": hex_color}
    return color_class  # default (Tabler class)



import hashlib

def get_team_color(team_id=None, team_name=None, variant="class"):
    """
    Return a team's color in one of three variants:
      - 'class': Tabler color class (default)
      - 'hex': HEX color value
      - 'both': dict with {'class': <class>, 'hex': <hex>}

    Deterministic based on team_id or team_name.
    """

    color_pairs = [
        ("bg-blue-lt text-white", "#3b82f6"),
        ("bg-green-lt text-white", "#22c55e"),
        ("bg-orange-lt text-white", "#fb923c"),
        ("bg-purple-lt text-white", "#8b5cf6"),
        ("bg-pink-lt text-white", "#ec4899"),
        ("bg-cyan-lt text-white", "#06b6d4"),
        ("bg-yellow-lt text-white", "#eab308"),
        ("bg-red-lt text-white", "#ef4444"),
        ("bg-indigo-lt text-white", "#6366f1"),
        ("bg-teal-lt text-white", "#14b8a6"),
        ("bg-lime-lt text-white", "#84cc16"),
        ("bg-amber-lt text-white", "#f59e0b"),
        ("bg-fuchsia-lt text-white", "#d946ef"),
        ("bg-emerald-lt text-white", "#10b981"),
        ("bg-violet-lt text-white", "#8b5cf6"),
        ("bg-rose-lt text-white", "#f43f5e"),
        ("bg-sky-lt text-white", "#0ea5e9"),
        ("bg-orange-200 text-white", "#fdba74"),
        ("bg-purple-200 text-white", "#c4b5fd"),
        ("bg-pink-200 text-white", "#f9a8d4"),
    ]

    base = str(team_id or team_name or "")
    if not base:
        if variant == "hex":
            return "#0f172a"
        elif variant == "both":
            return {"class": "bg-dark text-white", "hex": "#0f172a"}
        return "bg-dark text-white"

    # Stable deterministic hash
    digest = hashlib.md5(base.encode("utf-8")).hexdigest()
    index = int(digest, 16) % len(color_pairs)
    color_class, hex_color = color_pairs[index]

    if variant == "hex":
        return hex_color
    elif variant == "both":
        return {"class": color_class, "hex": hex_color}
    return color_class  # default




# ---------- Helper ----------
def handle_file_upload(file_url):
    """
    Normalize file URLs for chat messages across dev/prod.
    Ensures no duplicate /media/ prefix and preserves Cloudinary URLs.
    """
    if not file_url:
        return None

    # Full Cloudinary or remote URL — leave untouched
    if file_url.startswith("http"):
        return file_url

    # Normalize redundant slashes and remove extra /media/
    cleaned = file_url.lstrip("/")
    if cleaned.startswith("media/"):
        cleaned = cleaned[len("media/"):]

    if settings.DEBUG:
        return f"/media/{cleaned}"

    # In production, stored Cloudinary path or S3 key
    return cleaned


# =================== Chat Consumer ===================
class ChatConsumer(AsyncWebsocketConsumer):

    # ---------- WebSocket Lifecycle ----------
    async def connect(self):
        from .models import Team
        # Parse team from querystring, default = central
        qs = self.scope.get("query_string", b"").decode()
        params = urllib.parse.parse_qs(qs)
        team_slug = params.get("team", [None])[0] or params.get("team_id", [None])[0]

        self.team = None
        self.room_group_name = "chat_central"

        if team_slug:
            # team provided could be id or slug/name — try id first
            team = None
            if team_slug.isdigit():
                team = await sync_to_async(Team.objects.filter(id=int(team_slug)).first)()
            if not team:
                team = await sync_to_async(Team.objects.filter(name__iexact=team_slug).first)()

            if team:
                self.team = team
                self.room_group_name = f"chat_team_{team.id}"

        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

        # ✅ Send latest pinned previews on connect
        recent = await self.get_recent_pinned(self.team)
        await self.send(text_data=json.dumps({
            "type": "pinned_preview",
            "messages": recent
        }))

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            if data.get("action"):
                await self.handle_action(data)
            else:
                # Always attach the current connection’s team
                team_id = self.team.id if self.team else None
                await self.handle_new_message({**data, "team_id": team_id})
        except Exception as e:
            logger.error(f"WebSocket receive error: {e}")

    # ---------- Action Handler ----------
    async def handle_action(self, data):
        action = data.get("action")
        sender_id = data.get("sender_id")

        if action == "pin":
            message_ids = data.get("message_ids", [])
            pinned_map = await self.handle_pin(message_ids, sender_id)

            # 🔹 Get sender info for pinned_by
            from .models import CustomUser
            try:
                pinner = await sync_to_async(CustomUser.objects.get)(id=sender_id)
                pinned_by_payload = {
                    "id": pinner.id,
                    "name": pinner.full_name or pinner.username,
                    "title": getattr(pinner, "title", "")
                }
            except Exception:
                pinned_by_payload = None

            # 🔹 1. Tell all clients to toggle bubble flags
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "message_pinned",
                    "message_ids": message_ids,
                    "pinned": pinned_map,
                    "pinned_by": pinned_by_payload,
                }
            )

            # 🔹 2. Broadcast updated pinned preview stack
            recent = await self.get_recent_pinned(self.team)
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "pinned_preview",
                    "messages": recent
                }
            )
            return

        elif action == "reply":
            # client handles reply preview
            return

        else:
            logger.debug("Unknown action received: %s", action)

    # ---------- New Message Handler ----------
    async def handle_new_message(self, data):
        sender_id = data.get("sender_id")
        message = data.get("message", "").rstrip()
        guest_id = data.get("guest_id")
        parent_id = data.get("reply_to_id")
        mentions_ids = data.get("mentions", [])
        file_data = data.get("file") or {} # expect dict {url,name,size,type}
        file_url = file_data.get("url") if file_data else None
        link_preview = data.get("link_preview")
        team_id = data.get("team_id")

        if not message.strip() and not guest_id and not file_url and not link_preview:
            return

        saved_message = await self.create_message(sender_id, message, guest_id, parent_id, mentions_ids, file_url, link_preview, team_id, file_data)
        payload = {**saved_message, "type": "chat_message", "color": get_user_color(sender_id)}
        await self.channel_layer.group_send(self.room_group_name, payload)

    # ---------- WebSocket Group Events ----------
    async def chat_message(self, event):
        await self.send(text_data=json.dumps(event))

    async def message_pinned(self, event):
        await self.send(text_data=json.dumps(event))

    async def pinned_preview(self, event):
        """Broadcast pinned preview list"""
        await self.send(text_data=json.dumps({
            "type": "pinned_preview",
            "messages": event["messages"]
        }))

    # =================== Database / Sync Handlers ===================
    @sync_to_async(thread_sensitive=False)
    def get_sender_name(self, sender_id):
        from .models import CustomUser
        user = CustomUser.objects.only('full_name', 'username').get(id=sender_id)
        return user.full_name or user.username

    @sync_to_async(thread_sensitive=False)
    def get_sender_image(self, sender_id):
        from .models import CustomUser
        user = CustomUser.objects.only('image').get(id=sender_id)
        return user.image.url if user.image else None

    @staticmethod
    def now_iso():
        return now().isoformat()

    @sync_to_async
    def get_guest_info(self, guest_id):
        from guests.models import GuestEntry
        g = GuestEntry.objects.get(id=guest_id)
        return {
            "id": g.id,
            "name": g.full_name,
            "custom_id": g.custom_id,
            "image": g.picture.url if g.picture else None,
            "title": g.title,
            "date_of_visit": g.date_of_visit.strftime("%Y-%m-%d") if g.date_of_visit else "",
        }

    @sync_to_async
    def get_parent_info(self, parent_id):
        from .models import ChatMessage
        p = ChatMessage.objects.select_related("sender", "guest_card").get(id=parent_id)
        parent_data = {
            "id": p.id,
            "sender_name": p.sender.full_name or p.sender.username,
            "sender_title": p.sender.title,
            "message": p.message[:50],
        }
        if p.guest_card:
            g = p.guest_card
            parent_data["guest"] = {
                "id": g.id,
                "name": g.full_name,
                "title": g.title,
                "image": g.picture.url if g.picture else None,
                "date_of_visit": g.date_of_visit.strftime("%Y-%m-%d") if g.date_of_visit else "",
            }
        return parent_data

    # ---------- Action Handlers ----------
    @sync_to_async
    def handle_pin(self, message_ids, sender_id):
        from .models import ChatMessage
        res = {}
        for mid in message_ids:
            try:
                m = ChatMessage.objects.filter(id=mid).first()
                if not m:
                    continue

                # Toggle pinned state
                if m.pinned:
                    m.pinned = False
                    m.pinned_at = None
                    m.pinned_by = None
                else:
                    m.pinned = True
                    m.pinned_at = now()
                    m.pinned_by_id = sender_id
                m.save(update_fields=["pinned", "pinned_at", "pinned_by_id"])
                res[str(mid)] = m.pinned
            except Exception:
                logger.exception("Failed to toggle pin %s", mid)
        return res

    # ---------- Helpers ----------
    @sync_to_async
    def get_recent_pinned(self, team=None):
        from .models import ChatMessage
        from .utils import serialize_message, build_mention_helpers
        cutoff = now() - timedelta(days=14)

        # Auto-unpin expired ones
        ChatMessage.objects.filter(pinned=True, pinned_at__lt=cutoff).update(
            pinned=False, pinned_at=None, pinned_by=None
        )

        qs = ChatMessage.objects.filter(pinned=True, pinned_at__gte=cutoff)
        if team:
            qs = qs.filter(team=team)
        else:
            qs = qs.filter(team__isnull=True)

        pinned = qs.select_related("pinned_by", "sender", "guest_card").order_by("-pinned_at")[:3]
        mention_map, mention_regex = build_mention_helpers()
        return [serialize_message(m, mention_map, mention_regex) for m in pinned]

    # ---------- Build Broadcast Payload ----------
    @sync_to_async
    def get_message_payload(self, message_id):
        from .models import ChatMessage, CustomUser
        from .utils import serialize_message, build_mention_helpers

        try:
            msg = ChatMessage.objects.select_related("sender", "guest_card", "parent__sender").get(id=message_id)
        except ChatMessage.DoesNotExist:
            return {}

        mention_map, mention_regex = build_mention_helpers()
        return serialize_message(msg, mention_map, mention_regex)

    # ---------- Create Message (Async DB) ----------
    @sync_to_async
    def create_message(
        self, sender_id, message,
        guest_id=None, parent_id=None, mentions_ids=None,
        file_url=None, link_preview=None, team_id=None, file_data=None
    ):
        from .models import ChatMessage, Team
        from accounts.models import CustomUser
        from guests.models import GuestEntry
        from .utils import serialize_message, build_mention_helpers, get_link_preview
        from django.core.files.storage import default_storage
        import os

        url_pattern = re.compile(r'(https?://[^\s]+)')
        mentions_ids = mentions_ids or []

        try:
            sender = CustomUser.objects.get(id=sender_id)
            team = Team.objects.filter(id=team_id).first() if team_id else None
            # enforce: guest_card only allowed for Magnet team
            guest_card = None
            if guest_id:
                candidate = GuestEntry.objects.filter(id=guest_id).first()
                if candidate:
                    if team and team.name.lower() == "magnet":
                        guest_card = candidate
                    else:
                        # do not attach guest card if team is not Magnet
                        guest_card = None
            parent = ChatMessage.objects.filter(id=parent_id).first() if parent_id else None

            # 🔎 detect link if not provided
            if link_preview:
                link_meta = link_preview
            else:
                link_meta = {}
                match = url_pattern.search(message or "")
                if match:
                    link_meta = get_link_preview(match.group(0))

            # ✅ Cloudinary / Local upload
            file_field = None
            file_type = None
            if file_data:
                file_type = file_data.get("type")
                if not settings.DEBUG:
                    # Cloudinary → MUST store public_id
                    file_field = file_data.get("public_id")
                else:
                    # Dev → MUST store relative path for FileField
                    file_field = file_data.get("path")

            # ✅ Save message with real FileField
            saved = ChatMessage.objects.create(
                sender=sender,
                team=team,
                message=message or "",
                guest_card=guest_card,
                parent=parent,
                file=file_field,   # 👈 this is now always a FileField
                file_type=file_type,
                link_url=link_meta.get("url"),
                link_title=link_meta.get("title"),
                link_description=link_meta.get("description"),
                link_image=link_meta.get("image"),
            )

            # ✅ Serialize
            mention_map, mention_regex = build_mention_helpers()
            return serialize_message(saved, mention_map, mention_regex)

        except Exception as e:
            import logging
            logging.exception("create_message failed: %s", e)
            return {}


import json
from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async


import json
from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async


# consumers.py
import json
from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async


class AttendanceConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope["user"]

        if not self.user.is_authenticated:
            await self.close()
            return

        if not self.user.is_superuser:
            self.user_team_ids = await self.get_user_team_ids()
        else:
            self.user_team_ids = []

        # 👇 Group names renamed to avoid conflict
        await self.channel_layer.group_add("attendance", self.channel_name)
        await self.channel_layer.group_add(f"attendance_user_{self.user.id}", self.channel_name)

        await self.accept()
        print(f"✅ {self.user} connected to attendance groups")

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard("attendance", self.channel_name)
        await self.channel_layer.group_discard(f"attendance_user_{self.user.id}", self.channel_name)

    # -------------------------------------------------------
    # UTILITIES
    # -------------------------------------------------------
    @sync_to_async
    def get_user_team_ids(self):
        from accounts.models import TeamMembership
        return list(
            TeamMembership.objects.filter(user=self.user)
            .values_list("team_id", flat=True)
        )

    # -------------------------------------------------------
    # EVENT HANDLERS
    # -------------------------------------------------------
    async def send_event(self, event):
        """Handle attendance event updates (for the 'attendance' group)."""
        data = event.get("data", {})
        team_id = data.get("team_id")

        if (
            self.user.is_superuser
            or team_id is None
            or team_id in self.user_team_ids
        ):
            await self.send(text_data=json.dumps(data))

    async def send_summary(self, event):
        """Handles messages sent with type='send_summary'."""
        records = event.get("data", {}).get("records", [])

        # 🔹 Safely handle nested user dicts
        if not self.user.is_superuser:
            records = [
                r for r in records
                if (
                    (r["event"]["team"]["id"] in self.user_team_ids or r["event"]["team"]["id"] is None)
                    and not str(r.get("user", {}).get("full_name", "")).lower().startswith("superuser")
                )
            ]

        await self.send(text_data=json.dumps({
            "type": "send_summary",
            "records": records
        }))

    async def dashboard_summary(self, event):
        """Handles per-user dashboard summary updates."""
        data = event.get("data", {})
        user_id = data.get("user_id")

        if user_id == self.user.id:
            await self.send(text_data=json.dumps({
                "type": "dashboard_summary",
                "summary": data.get("summary"),
                "today": data.get("today"),
                "totals": data.get("totals"),
            }))
