import json

from django.core.management.base import BaseCommand, CommandError

from plane.services.jira_csv_import import import_jira_csv, read_jira_csv


class Command(BaseCommand):
    help = "Import a Jira CSV into a new project. Defaults to a read-only dry-run."

    def add_arguments(self, parser):
        parser.add_argument("csv_path")
        parser.add_argument("--workspace", required=True)
        parser.add_argument("--actor", required=True)
        parser.add_argument("--timezone", default="Asia/Bangkok")
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):
        try:
            data = read_jira_csv(options["csv_path"], options["timezone"])
            result = import_jira_csv(data, options["workspace"], options["actor"], apply=options["apply"])
        except (ValueError, OSError, LookupError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps(result, ensure_ascii=False))
