import json
import logging


class EventFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        event = {"level": record.levelname, "event": record.getMessage()}
        for name in (
            "run_id", "candidate_index", "company_name",
            "candidate_count", "selected_count", "discovered_count",
            "reason", "error_type", "status_code",
            "model", "duration_ms", "evidence_quality", "prospect_count",
            "analysis_count", "evidence_count", "signal_count", "provider",
            "contact_count",
        ):
            if hasattr(record, name):
                event[name] = getattr(record, name)
        return json.dumps(event)


def configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(EventFormatter())
    logging.basicConfig(level=logging.INFO, handlers=[handler])
