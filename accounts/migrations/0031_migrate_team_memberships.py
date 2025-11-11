from django.db import migrations


def migrate_team_memberships(apps, schema_editor):
    Team = apps.get_model("workforce", "Team")
    CustomUser = apps.get_model("accounts", "CustomUser")
    TeamMembership = apps.get_model("accounts", "TeamMembership")
    GuestEntry = apps.get_model("guests", "GuestEntry")

    print("\n🔄 Starting TeamMembership migration...")

    # Step 1: Ensure "Magnet" team exists
    magnet_team, created = Team.objects.get_or_create(
        name="Magnet",
        defaults={
            "description": "Guest Management Team",
            "color": "#2e303e",
            "is_active": True,
        },
    )
    if created:
        print("✅ Created 'Magnet' team.")
    else:
        print("ℹ️ 'Magnet' team already exists.")

    # Step 2: Convert old team.members to TeamMembership
    migrated_count = 0
    for team in Team.objects.all():
        for user in team.members.all():
            obj, created = TeamMembership.objects.get_or_create(
                user=user,
                team=team,
                defaults={"team_role": "Member"},
            )
            if created:
                migrated_count += 1

    print(f"✅ Migrated {migrated_count} existing team-member relationships.")

    # Step 3: Identify all users linked to guest entries
    guest_users = CustomUser.objects.filter(
        assigned_guests__isnull=False
    ).distinct()

    magnet_added = 0
    for user in guest_users:
        obj, created = TeamMembership.objects.get_or_create(
            user=user,
            team=magnet_team,
            defaults={"team_role": "Member"},
        )
        if created:
            magnet_added += 1

    print(f"✅ Added {magnet_added} users to the 'Magnet' team (via guest assignments).")

    # Step 4: Report any users linked to guests but not in Magnet
    missing_in_magnet = guest_users.exclude(team_memberships__team=magnet_team)
    if missing_in_magnet.exists():
        print("⚠️ Warning: Some guest-related users were not linked to the 'Magnet' team:")
        for u in missing_in_magnet:
            print(f"   - {u.full_name or u.username}")
    else:
        print("✅ All guest-related users correctly linked to 'Magnet'.")

    print("🎉 TeamMembership migration completed successfully!\n")


def reverse_migration(apps, schema_editor):
    TeamMembership = apps.get_model("accounts", "TeamMembership")
    for membership in TeamMembership.objects.all():
        membership.team.members.add(membership.user)


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0030_alter_customuser_role_teammembership"),  # replace with latest accounts migration
        ("workforce", "0002_alter_chatmessage_sender"),
        ("guests", "0015_guestentry_age_range_and_more"),
    ]

    operations = [
        migrations.RunPython(migrate_team_memberships, reverse_migration),
    ]
