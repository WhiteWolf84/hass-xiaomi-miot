"""One place where an entity's own name is decided.

With `has_entity_name` set, Home Assistant builds a friendly name from two
halves: the device name it already knows, and whatever name the entity claims
for itself. An entity that hands back the device name again -- or a word that
means the same thing, `Dehumidifier` on a dehumidifier -- has it printed twice.
Returning None instead says the entity *is* the device, and the device name
alone becomes the whole friendly name.

The MIoT spec describes a device as a set of services, and one of them usually
carries the device's own name. That service is the device; every other service
and every property is a feature of it. Deciding which is which happens in
`Device.main_service`, and this module turns that answer into a name.

The functions here are pure. They take strings and spec objects, never `hass`
and never an entity, so the naming rules can be read in one screen and tested
without standing up an integration.
"""
import re
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .miot_spec import MiotService, MiotProperty, MiotAction

WORD_CHARACTER = re.compile(r'\w')


def entity_own_name(name, device_name=None) -> Optional[str]:
    """Return the entity's own half of `name`, or None when nothing is left.

    Several code paths build a name as "<device name> <what it does>", which
    duplicates the half Home Assistant adds back. The device name is dropped
    only where it prefixes a whole word: a device called `Fan` must not turn
    `Fantasy Mode` into `tasy Mode`.
    """
    nam = f'{name or ""}'.strip()
    dev = f'{device_name or ""}'.strip()
    if not nam or not dev:
        return nam or None
    if nam[:len(dev)].lower() != dev.lower():
        return nam
    rest = nam[len(dev):]
    if rest and WORD_CHARACTER.match(rest[0]):
        return nam  # the device name only looked like a prefix
    return rest.strip() or None


def spec_entity_name(
    device_name=None,
    main_service: Optional['MiotService'] = None,
    service: Optional['MiotService'] = None,
    prop: Optional['MiotProperty'] = None,
    action: Optional['MiotAction'] = None,
) -> Optional[str]:
    """Name an entity after the part of the MIoT spec it is bound to.

    Pass whichever of `service`, `prop` and `action` the entity takes its
    identity from; the most specific one wins, because a property of the main
    service -- `Device Fault` on a dehumidifier -- is a feature and keeps its
    name. None comes back only for the service that is the device itself.
    """
    if prop is not None:
        source = prop.friendly_desc
    elif action is not None:
        source = action.friendly_desc
    elif service is not None:
        if main_service is not None and service is main_service:
            return None
        source = service.friendly_desc
    else:
        return None
    return entity_own_name(source, device_name)
