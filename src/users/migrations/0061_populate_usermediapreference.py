from django.db import migrations

MEDIA_TYPES = [
    "tv", "season", "movie", "anime", "manga",
    "game", "book", "comic", "boardgame",
]


def forward(apps, schema_editor):
    User = apps.get_model("users", "User")
    UserMediaPreference = apps.get_model("users", "UserMediaPreference")

    for user in User.objects.all():
        prefs = []
        for mt in MEDIA_TYPES:
            prefs.append(
                UserMediaPreference(
                    user=user,
                    media_type=mt,
                    enabled=getattr(user, f"{mt}_enabled"),
                    layout=getattr(user, f"{mt}_layout"),
                    sort=getattr(user, f"{mt}_sort"),
                    status_filter=getattr(user, f"{mt}_status"),
                )
            )
        UserMediaPreference.objects.bulk_create(prefs, ignore_conflicts=True)


def reverse(apps, schema_editor):
    User = apps.get_model("users", "User")
    UserMediaPreference = apps.get_model("users", "UserMediaPreference")

    for pref in UserMediaPreference.objects.select_related("user").all():
        user = pref.user
        setattr(user, f"{pref.media_type}_enabled", pref.enabled)
        setattr(user, f"{pref.media_type}_layout", pref.layout)
        setattr(user, f"{pref.media_type}_sort", pref.sort)
        setattr(user, f"{pref.media_type}_status", pref.status_filter)
        user.save()


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0060_create_usermediapreference"),
    ]

    operations = [
        migrations.RunPython(forward, reverse),
    ]
