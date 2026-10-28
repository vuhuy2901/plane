from django.db import migrations, models
from django.utils import timezone


def archive_active_self_relations(apps, schema_editor):
    IssueRelation = apps.get_model("db", "IssueRelation")
    IssueRelation.objects.filter(
        deleted_at__isnull=True,
        issue_id=models.F("related_issue_id"),
    ).update(deleted_at=timezone.now())


class Migration(migrations.Migration):
    dependencies = [("db", "0135_mcp_connection_public_base_url")]

    operations = [
        migrations.AddField(
            model_name="project",
            name="prevent_blocked_issue_completion",
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(archive_active_self_relations, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="issuerelation",
            constraint=models.CheckConstraint(
                condition=models.Q(deleted_at__isnull=False)
                | ~models.Q(issue=models.F("related_issue")),
                name="issue_relation_active_not_self_referential",
            ),
        ),
    ]
