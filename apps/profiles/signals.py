from django.db.models.signals import pre_save
from django.dispatch import receiver

from .models import TechAnalysis


@receiver(pre_save, sender=TechAnalysis)
def add_aggregated_analysis(sender, **kwargs):
    aggregated_analysis = {"libs": {}, "tech": {}, "tags": {}}

    def get_initial_stats_unit():
        return {"insertions": 0, "deletions": 0}

    repos = sender.repos
    for repo in repos:
        for libs_tech_or_tags in {"libs", "tech", "tags"}:
            for (specific_cat, stats) in repo[libs_tech_or_tags].items():
                if specific_cat not in aggregated_analysis[libs_tech_or_tags]:
                    aggregated_analysis[libs_tech_or_tags][
                        specific_cat
                    ] = get_initial_stats_unit()

                aggregated_analysis[libs_tech_or_tags][specific_cat][
                    "insertions"
                ] += stats["insertions"]
                aggregated_analysis[libs_tech_or_tags][specific_cat][
                    "deletions"
                ] += stats["deletions"]

    sender.aggregated_analysis = aggregated_analysis
