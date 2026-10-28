from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("db", "0134_mcp_connection_portal")]

    operations = [
        migrations.AddField(
            model_name="mcpconnection",
            name="public_base_url",
            field=models.URLField(blank=True, max_length=500, null=True),
        ),
    ]
