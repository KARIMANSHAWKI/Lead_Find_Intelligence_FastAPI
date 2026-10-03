from pydantic import BaseModel, ConfigDict

from app.domain.models.buying_signal import BuyingSignal
from app.domain.models.company_research import ResearchEvidence
from app.domain.models.types import NonEmptyString, QualificationLevel


class ProspectAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    icp_fit: QualificationLevel
    product_relevance: QualificationLevel
    why_now: NonEmptyString
    buying_signals: list[BuyingSignal]
    evidence_quality: QualificationLevel

    def validate_evidence(self, evidence: list[ResearchEvidence]) -> None:
        """Require exact supplied quotes and matching sources for every signal."""
        if not evidence and (self.buying_signals or self.evidence_quality != "low"):
            raise ValueError("Without evidence, signals must be empty and evidence quality low.")
        supplied = {(item.text, item.source_url) for item in evidence}
        if any((signal.evidence, signal.source_url) not in supplied for signal in self.buying_signals):
            raise ValueError("Buying signals must quote supplied evidence with its matching source.")
