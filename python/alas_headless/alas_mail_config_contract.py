"""Fail-closed configuration contract for ALAS white-mail selection."""

from __future__ import annotations

from dataclasses import dataclass

from .semantic_oracle import SemanticGateClosed


@dataclass(frozen=True)
class AlasMailConfigSnapshot:
    claim_merit: bool
    claim_maintenance: bool
    claim_trade_license: bool
    delete_collected: bool

    @property
    def has_claim_selection(self) -> bool:
        return self.claim_merit or self.claim_maintenance or self.claim_trade_license


def validate_alas_mail_config(
    *,
    claim_merit: object,
    claim_maintenance: object,
    claim_trade_license: object,
    delete_collected: object,
) -> AlasMailConfigSnapshot:
    """Classify the four original ALAS mail toggles without performing input."""

    values = {
        "Mail_ClaimMerit": claim_merit,
        "Mail_ClaimMaintenance": claim_maintenance,
        "Mail_ClaimTradeLicense": claim_trade_license,
        "Mail_DeleteCollected": delete_collected,
    }
    for name, value in values.items():
        if type(value) is not bool:
            raise SemanticGateClosed(f"{name} must be a bool")
    return AlasMailConfigSnapshot(
        claim_merit=claim_merit,
        claim_maintenance=claim_maintenance,
        claim_trade_license=claim_trade_license,
        delete_collected=delete_collected,
    )
