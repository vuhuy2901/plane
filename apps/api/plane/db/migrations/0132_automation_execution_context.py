from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("db", "0131_automation_delivery_attempts")]
    operations = [
        migrations.AddField(
            model_name="projectautomationrule", name="schedule_cursor", field=models.JSONField(default=dict)
        ),
        migrations.AddField(
            model_name="projectautomationevent", name="before_snapshot", field=models.JSONField(null=True)
        ),
        migrations.AddField(model_name="projectautomationevent", name="context", field=models.JSONField(default=dict)),
        migrations.AddField(model_name="projectautomationevent", name="progress", field=models.JSONField(default=dict)),
        migrations.AddField(
            model_name="projectautomationevent",
            name="deduplication_key",
            field=models.CharField(max_length=255, null=True, unique=True),
        ),
    ]
