from enum import StrEnum


class Capability(StrEnum):
    ASK = "ask"
    INVESTIGATE = "investigate"
    WATCH = "watch"
    ACT = "act"


class CapabilityState(StrEnum):
    ACTIVE = "active"
    FOUNDATION = "foundation"
    INACTIVE = "inactive"


CAPABILITY_STATES: dict[Capability, CapabilityState] = {
    Capability.ASK: CapabilityState.ACTIVE,
    Capability.INVESTIGATE: CapabilityState.ACTIVE,
    Capability.WATCH: CapabilityState.INACTIVE,
    Capability.ACT: CapabilityState.INACTIVE,
}
