import json

from django.core.management.base import BaseCommand, CommandError

from plane.db.models import Project
from plane.services.jira_csv_import import read_jira_csv, verify_jira_csv_import


class Command(BaseCommand):
    help = "Read-only reconciliation of Jira CSV source columns and imported Plane records."

    def add_arguments(self, parser):
        parser.add_argument("csv_path")
        parser.add_argument("--workspace", required=True)
        parser.add_argument("--timezone", default="Asia/Bangkok")

    def handle(self, *args, **options):
        try:
            data = read_jira_csv(options["csv_path"], options["timezone"])
            project = Project.objects.get(workspace__slug=options["workspace"], identifier=data["project_key"])
            if (
                project.external_source != "jira_csv"
                or project.external_id != f"{data['project_key']}:{data['sha256']}"
            ):
                raise ValueError("The selected project does not match this source file.")
            result = verify_jira_csv_import(data, project)
        except (ValueError, OSError, LookupError, Project.DoesNotExist) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps(result, ensure_ascii=False))
