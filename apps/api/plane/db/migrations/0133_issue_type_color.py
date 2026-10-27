from django.db import migrations, models


def assign_colors(apps, schema_editor):
    issue_types = apps.get_model("db", "IssueType")
    palette = ["#3E63DD", "#DC2626", "#059669", "#9333EA", "#D97706", "#0891B2", "#DB2777", "#4F46E5"]
    counts = {}
    for item in issue_types.objects.using(schema_editor.connection.alias).order_by("workspace_id", "id").iterator():
        index = counts.get(item.workspace_id, 0)
        issue_types.objects.using(schema_editor.connection.alias).filter(pk=item.pk).update(
            color=palette[index % len(palette)]
        )
        counts[item.workspace_id] = index + 1


class Migration(migrations.Migration):
    dependencies = [("db", "0132_automation_execution_context")]
    operations = [
        migrations.AddField(
            model_name="issuetype", name="color", field=models.CharField(default="#3E63DD", max_length=7)
        ),
        migrations.RunPython(assign_colors, migrations.RunPython.noop),
    ]
