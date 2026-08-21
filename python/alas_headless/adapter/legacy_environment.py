"""One-way compatibility translation for the legacy semantic environment."""

from __future__ import annotations

import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping

try:
    from typing import Protocol
except ImportError:  # Python 3.7 in the pinned ALAS runtime
    from typing_extensions import Protocol

from ..semantic_oracle import SemanticGateClosed
from .policy import RunPolicy


LEGACY_SEMANTIC_ENVIRONMENT_VARIABLES = frozenset(
    {
        "ALAS_SEMANTIC_ADB",
        "ALAS_SEMANTIC_ADB_COMMAND_TIMEOUT_SECONDS",
        "ALAS_SEMANTIC_ALLOW_COMMISSION_REWARDS",
        "ALAS_SEMANTIC_ALLOW_MAIL_MUTATIONS",
        "ALAS_SEMANTIC_MAIL_MUTATION_BUDGET",
        "ALAS_SEMANTIC_META_ASSIST_BUDGET",
        "ALAS_SEMANTIC_MINIGAME_PLAY_BUDGET",
        "ALAS_SEMANTIC_OPSI_COORDINATE_CHECKOUT_BUDGET",
        "ALAS_SEMANTIC_OBSERVER_MAX_AGE_MS",
        "ALAS_SEMANTIC_ALLOW_MISSION_CLAIM_ONCE",
        "ALAS_SEMANTIC_ALLOW_TACTICAL_REWARDS",
        "ALAS_SEMANTIC_AWAKEN_BUDGET",
        "ALAS_SEMANTIC_BUILD_SUBMIT_BUDGET",
        "ALAS_SEMANTIC_CAMPAIGN_COMBAT_BUDGET",
        "ALAS_SEMANTIC_CAMPAIGN_FLEET_MUTATION_BUDGET",
        "ALAS_SEMANTIC_CAMPAIGN_SORTIE_BUDGET",
        "ALAS_SEMANTIC_CAMPAIGN_STAGE_ENTRY_BUDGET",
        "ALAS_SEMANTIC_CAMPAIGN_VIEWPORT_SWIPE_BUDGET",
        "ALAS_SEMANTIC_COMMISSION_REWARD_BUDGET",
        "ALAS_SEMANTIC_COMMISSION_START_BUDGET",
        "ALAS_SEMANTIC_DAILY_EXECUTE_BUDGET",
        "ALAS_SEMANTIC_EXERCISE_EXECUTE_BUDGET",
        "ALAS_SEMANTIC_EXERCISE_REFRESH_BUDGET",
        "ALAS_SEMANTIC_DORM_COLLECT_BUDGET",
        "ALAS_SEMANTIC_DORM_FEED_BUDGET",
        "ALAS_SEMANTIC_DRIVER_REVISION",
        "ALAS_SEMANTIC_ENHANCEMENT_BUDGET",
        "ALAS_SEMANTIC_GUILD_CLAIM_BUDGET",
        "ALAS_SEMANTIC_GUILD_DISPATCH_BUDGET",
        "ALAS_SEMANTIC_GUILD_EXCHANGE_BUDGET",
        "ALAS_SEMANTIC_MODE",
        "ALAS_SEMANTIC_RESEARCH_REWARD_BUDGET",
        "ALAS_SEMANTIC_RESEARCH_START_BUDGET",
        "ALAS_SEMANTIC_RETIREMENT_BUDGET",
        "ALAS_SEMANTIC_SHOP_PURCHASE_BUDGET",
        "ALAS_SEMANTIC_TACTICAL_ASSIGN_BUDGET",
    }
)

LEGACY_BOOLEAN_GRANTS: Mapping[str, str] = MappingProxyType(
    {
        "ALAS_SEMANTIC_ALLOW_MISSION_CLAIM_ONCE": "mission.claim",
        "ALAS_SEMANTIC_ALLOW_MAIL_MUTATIONS": "mail.mutation",
        "ALAS_SEMANTIC_ALLOW_TACTICAL_REWARDS": "tactical.reward",
    }
)

LEGACY_BUDGET_GRANTS: Mapping[str, tuple[str, str]] = MappingProxyType(
    {
        "ALAS_SEMANTIC_AWAKEN_BUDGET": (
            "awaken.execute",
            "awaken",
        ),
        "ALAS_SEMANTIC_MAIL_MUTATION_BUDGET": (
            "mail.mutation",
            "mail mutation",
        ),
        "ALAS_SEMANTIC_MINIGAME_PLAY_BUDGET": (
            "minigame.play",
            "minigame play",
        ),
        "ALAS_SEMANTIC_META_ASSIST_BUDGET": (
            "meta.assist",
            "META assist",
        ),
        "ALAS_SEMANTIC_OPSI_COORDINATE_CHECKOUT_BUDGET": (
            "operation_siren.coordinate_checkout",
            "Operation Siren coordinate checkout",
        ),
        "ALAS_SEMANTIC_TACTICAL_ASSIGN_BUDGET": (
            "tactical.assign",
            "tactical assign",
        ),
        "ALAS_SEMANTIC_COMMISSION_REWARD_BUDGET": (
            "commission.reward",
            "commission reward",
        ),
        "ALAS_SEMANTIC_COMMISSION_START_BUDGET": (
            "commission.start",
            "commission start",
        ),
        "ALAS_SEMANTIC_DAILY_EXECUTE_BUDGET": (
            "daily.execute",
            "daily execute",
        ),
        "ALAS_SEMANTIC_EXERCISE_EXECUTE_BUDGET": (
            "exercise.execute",
            "exercise execute",
        ),
        "ALAS_SEMANTIC_EXERCISE_REFRESH_BUDGET": (
            "exercise.refresh",
            "exercise refresh",
        ),
        "ALAS_SEMANTIC_RESEARCH_REWARD_BUDGET": (
            "research.reward",
            "research reward",
        ),
        "ALAS_SEMANTIC_RESEARCH_START_BUDGET": (
            "research.start",
            "research start",
        ),
        "ALAS_SEMANTIC_DORM_COLLECT_BUDGET": (
            "dorm.collect",
            "dorm collect",
        ),
        "ALAS_SEMANTIC_DORM_FEED_BUDGET": ("dorm.feed", "dorm feed"),
        "ALAS_SEMANTIC_ENHANCEMENT_BUDGET": (
            "enhancement.execute",
            "enhancement",
        ),
        "ALAS_SEMANTIC_GUILD_CLAIM_BUDGET": ("guild.claim", "guild claim"),
        "ALAS_SEMANTIC_GUILD_DISPATCH_BUDGET": (
            "guild.dispatch",
            "guild dispatch",
        ),
        "ALAS_SEMANTIC_GUILD_EXCHANGE_BUDGET": (
            "guild.exchange",
            "guild exchange",
        ),
        "ALAS_SEMANTIC_BUILD_SUBMIT_BUDGET": ("build.submit", "build submit"),
        "ALAS_SEMANTIC_RETIREMENT_BUDGET": (
            "retirement.execute",
            "retirement",
        ),
        "ALAS_SEMANTIC_SHOP_PURCHASE_BUDGET": ("shop.purchase", "shop purchase"),
        "ALAS_SEMANTIC_CAMPAIGN_STAGE_ENTRY_BUDGET": (
            "campaign.stage_entry",
            "campaign stage entry",
        ),
        "ALAS_SEMANTIC_CAMPAIGN_FLEET_MUTATION_BUDGET": (
            "campaign.fleet_mutation",
            "campaign fleet mutation",
        ),
        "ALAS_SEMANTIC_CAMPAIGN_SORTIE_BUDGET": (
            "campaign.sortie",
            "campaign sortie",
        ),
        "ALAS_SEMANTIC_CAMPAIGN_COMBAT_BUDGET": (
            "campaign.grid_click",
            "campaign combat",
        ),
        "ALAS_SEMANTIC_CAMPAIGN_VIEWPORT_SWIPE_BUDGET": (
            "campaign.viewport_swipe",
            "campaign viewport swipe",
        ),
    }
)

_CANONICAL_NON_NEGATIVE_INTEGER = re.compile(r"0|[1-9][0-9]*")
_PINNED_REVISION = re.compile(r"[0-9a-f]{40}")


class _TracePort(Protocol):
    def emit(
        self,
        event: str,
        outcome: str = "ok",
        duration_ns: int | None = None,
        fields: Mapping[str, Any] | None = None,
    ) -> bool: ...


@dataclass(frozen=True)
class LegacyEnvironmentTranslation:
    """Validated legacy configuration plus its effective policy grants."""

    driver_revision: str
    adb: str
    adb_command_timeout_seconds: int
    observer_max_age_ms: int
    grants: Mapping[str, int]
    explicit_policy: RunPolicy | None
    legacy_grant_variables_present: int
    nondefault_legacy_grants: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "grants", MappingProxyType(dict(self.grants)))

    def grant(self, capability: str) -> int:
        return self.grants.get(capability, 0)

    @property
    def session_arguments(self) -> Mapping[str, Any]:
        return MappingProxyType(
            {
                "driver_revision": self.driver_revision,
                "adb": self.adb,
                "allow_mission_claim_once": self.grant("mission.claim") > 0,
                "allow_mail_mutations": self.grant("mail.mutation") > 0,
                "mail_mutation_budget": self.grant("mail.mutation"),
                "minigame_play_budget": self.grant("minigame.play"),
                "meta_assist_budget": self.grant("meta.assist"),
                "operation_siren_coordinate_checkout_budget": self.grant(
                    "operation_siren.coordinate_checkout"
                ),
                "allow_tactical_rewards": self.grant("tactical.reward") > 0,
                "tactical_assign_budget": self.grant("tactical.assign"),
                "commission_reward_budget": self.grant("commission.reward"),
                "commission_start_budget": self.grant("commission.start"),
                "daily_execute_budget": self.grant("daily.execute"),
                "exercise_execute_budget": self.grant("exercise.execute"),
                "exercise_refresh_budget": self.grant("exercise.refresh"),
                "research_reward_budget": self.grant("research.reward"),
                "research_start_budget": self.grant("research.start"),
                "dorm_collect_budget": self.grant("dorm.collect"),
                "dorm_feed_budget": self.grant("dorm.feed"),
                "awaken_budget": self.grant("awaken.execute"),
                "enhancement_budget": self.grant("enhancement.execute"),
                "build_submit_budget": self.grant("build.submit"),
                "retirement_budget": self.grant("retirement.execute"),
                "shop_purchase_budget": self.grant("shop.purchase"),
                "campaign_stage_entry_budget": self.grant("campaign.stage_entry"),
                "campaign_fleet_mutation_budget": self.grant("campaign.fleet_mutation"),
                "campaign_sortie_budget": self.grant("campaign.sortie"),
                "campaign_combat_budget": self.grant("campaign.grid_click"),
                "campaign_viewport_swipe_budget": self.grant("campaign.viewport_swipe"),
                "adb_command_timeout_seconds": self.adb_command_timeout_seconds,
                "observer_max_age_ms": self.observer_max_age_ms,
            }
        )


def _canonical_integer(name: str, label: str, environment: Mapping[str, str]) -> int:
    value = environment.get(name, "0")
    if (
        not isinstance(value, str)
        or _CANONICAL_NON_NEGATIVE_INTEGER.fullmatch(value) is None
    ):
        raise SemanticGateClosed(
            "{0} budget must be a canonical non-negative integer".format(label)
        )
    return int(value)


def translate_legacy_semantic_environment(
    environment: Mapping[str, str],
    *,
    explicit_policy: RunPolicy | None = None,
    trace: _TracePort | None = None,
) -> LegacyEnvironmentTranslation:
    """Parse the complete A01 environment surface into effective grants once."""

    if not isinstance(environment, Mapping):
        raise TypeError("semantic environment must be a mapping")
    if explicit_policy is not None and not isinstance(explicit_policy, RunPolicy):
        raise TypeError("explicit policy must be a RunPolicy")
    if environment.get("ALAS_SEMANTIC_MODE") != "1":
        raise SemanticGateClosed("ALAS semantic mode is not explicitly enabled")
    if "ALAS_SEMANTIC_ALLOW_COMMISSION_REWARDS" in environment:
        raise SemanticGateClosed(
            "boolean commission reward opt-in was removed; use the integer budget"
        )

    raw_timeout = environment.get("ALAS_SEMANTIC_ADB_COMMAND_TIMEOUT_SECONDS", "10")
    if (
        not isinstance(raw_timeout, str)
        or _CANONICAL_NON_NEGATIVE_INTEGER.fullmatch(raw_timeout) is None
    ):
        raise SemanticGateClosed(
            "ADB command timeout budget must be a canonical non-negative integer"
        )
    timeout = int(raw_timeout)
    if not 1 <= timeout <= 120:
        raise SemanticGateClosed("semantic ALAS ADB timeout must be in [1, 120]")

    raw_max_age = environment.get("ALAS_SEMANTIC_OBSERVER_MAX_AGE_MS", "10000")
    if (
        not isinstance(raw_max_age, str)
        or _CANONICAL_NON_NEGATIVE_INTEGER.fullmatch(raw_max_age) is None
    ):
        raise SemanticGateClosed(
            "observer maximum age must be a canonical non-negative integer"
        )
    max_age = int(raw_max_age)
    if not 1 <= max_age <= 300000:
        raise SemanticGateClosed(
            "semantic ALAS observer maximum age must be in [1, 300000]"
        )

    revision = environment.get("ALAS_SEMANTIC_DRIVER_REVISION", "").lower()
    if _PINNED_REVISION.fullmatch(revision) is None:
        raise SemanticGateClosed("semantic ALAS mode requires a pinned ANGLE revision")

    legacy_grants: dict[str, int] = {}
    for variable, capability in LEGACY_BOOLEAN_GRANTS.items():
        legacy_grants[capability] = 1 if environment.get(variable) == "1" else 0
    for variable, (capability, label) in LEGACY_BUDGET_GRANTS.items():
        budget = _canonical_integer(variable, label, environment)
        legacy_grants[capability] = max(legacy_grants.get(capability, 0), budget)

    nondefault = sum(value > 0 for value in legacy_grants.values())
    if explicit_policy is not None and nondefault:
        raise SemanticGateClosed(
            "explicit run policy conflicts with nondefault legacy grants"
        )
    grants = explicit_policy.grants if explicit_policy is not None else legacy_grants
    present = sum(
        name in environment for name in (*LEGACY_BOOLEAN_GRANTS, *LEGACY_BUDGET_GRANTS)
    )
    translation = LegacyEnvironmentTranslation(
        driver_revision=revision,
        adb=environment.get("ALAS_SEMANTIC_ADB", "adb"),
        adb_command_timeout_seconds=timeout,
        observer_max_age_ms=max_age,
        grants=grants,
        explicit_policy=explicit_policy,
        legacy_grant_variables_present=present,
        nondefault_legacy_grants=nondefault,
    )
    if trace is not None:
        trace.emit(
            "semantic.policy.environment-translation",
            fields={
                "source": (
                    "explicit-policy"
                    if explicit_policy is not None
                    else "legacy-environment"
                ),
                "legacy_grant_variables_present": present,
                "nondefault_legacy_grants": nondefault,
                "effective_nonzero_grants": sum(
                    value > 0 for value in translation.grants.values()
                ),
            },
        )
    return translation
