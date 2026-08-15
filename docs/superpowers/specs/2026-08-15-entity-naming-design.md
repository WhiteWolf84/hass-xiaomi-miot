# Entity Naming Design

## Summary

Home Assistant composes an entity's friendly name from two halves when `has_entity_name` is set: the device name it already holds, and the name the entity claims for itself. Xiaomi Miot used to compute that second half eagerly in every entity constructor and store it in `_attr_name`. Because `Entity._name_internal()` answers with `_attr_name` before it consults anything else, that single decision short-circuited the rest of Home Assistant's naming pipeline.

Two visible defects followed from it. An entity built from the service that *represents* the device claimed the device's own name back, so a dehumidifier rendered as "Deumidificatore Deumidificatore". And the `name` keys this integration ships in `translations/<lang>.json` were unreachable for every service, property and action entity, because `_attr_name` always won: six of the seventeen keys in `it.json` were dead.

This design replaces the eager assignment with a resolution order, introduces an explicit model of which service *is* the device, and moves the rule that strips a duplicated device name into one shared module used by both entity hierarchies.

The implementation requires Home Assistant 2026.1.0 or newer and is verified against 2026.8.

## Goals

- An entity that stands for the whole device carries no name of its own, so Home Assistant shows the device name alone.
- Entities that stand for a feature keep their name, unchanged, including properties of the main service.
- `translations/<lang>.json` becomes reachable for every entity, so a wrong name can be corrected with a translation instead of Python.
- One implementation of "remove the device name where it prefixes the entity name", shared by the converter based and the legacy entity hierarchies.
- The main service is a decision taken once, inspectable, and overridable per model where the spec is ambiguous.
- No entity changes its `unique_id` or its `entity_id`.

## Non-goals

- No migration of the legacy `MiotEntity` platforms (`vacuum`, `water_heater`, `media_player`, `remote`, `alarm_control_panel`, `device_tracker`) onto `XEntity`. They are reached by the shared naming rule instead.
- No change to how `entity_id` is generated. The integration keeps assigning it from model, MAC and spec description.
- No change to the built-in `TRANSLATION_LANGUAGES` dictionaries, which stay the fallback for the open-ended MIoT namespace.
- No change to `friendly_desc` or `short_desc` on spec objects, so names like "Environment Relative Humidity" keep their current wording.
- No automatic detection of a main service where the device type and the service names disagree. That case is data, not a heuristic.

## Existing Behavior Reused

- `has_entity_name = True` was already set on both hierarchies.
- `XEntity` already left `_attr_name` unset for `AttrConv` and `InfoConv` entities, which is why `button.info` and the `sensor.clean_area` family already took their names from `translations/<lang>.json`. This design generalises that path rather than inventing one.
- `conv.option['name']` already expressed a deliberate name chosen in `device_customizes`, and still outranks everything else.
- `MiotSpec.name` and `MiotService.name` already parse the fourth field of a MIoT URN, so the device type and a service name are directly comparable.
- `MiotSpec.services_count` already counted services sharing a name, which is what distinguishes a multi gang switch from a single one.

## Architecture

### Which service is the device

`Device.main_service` resolves it once, in this order:

1. `main_service` in the model customizes, naming the service explicitly.
2. The service whose name equals the device type name, provided it is the only one with that name.
3. Nothing.

The second rule is the common case: `urn:...:device:dehumidifier:...` exposing `urn:...:service:dehumidifier:...`. The uniqueness condition is what keeps a three gang switch safe — `lumi.switch.n3acn3` is a `device:switch` exposing `service:switch` three times, and no single gang is the device.

The first rule covers the disagreement case, where a heuristic would have to guess: `chuangmi.plug.212a01` declares `device:outlet` and exposes `service:switch`. Rather than mapping type aliases, the answer is written down:

```yaml
xiaomi_miot:
  device_customizes:
    chuangmi.plug.212a01:
      main_service: switch
```

The third rule is deliberate. Where nothing matches, every service keeps the name it describes itself with. A missing main service costs a redundant word; a wrongly guessed one costs a nameless entity.

### One naming rule

`core/naming.py` holds two pure functions, taking strings and spec objects, never `hass` and never an entity:

- `entity_own_name(name, device_name)` removes the device name where it prefixes the entity name on a word boundary, and returns None when nothing is left. The boundary check is the fix for a latent defect: the previous `str.replace()` in `XEntity` matched anywhere in the string, and the previous `str.startswith()` in the legacy hierarchy matched mid-word, turning `Fantasy Mode` into `tasy Mode` on a device called `Fan`.
- `spec_entity_name(...)` picks the name source — property, then action, then service — and returns None for the service that is the device. A property of the main service is a feature and keeps its name, which is what leaves `Dehumidifier Device Fault` alone.

Both hierarchies call into this module: `XEntity.__init__`, `MiotEntity.name`, and `BaseEntity.entity_name_without_device` for the legacy sub entities.

### Resolution order

`XEntity` no longer assigns `_attr_name` from the spec. It stores the spec's answer in `_spec_name` and overrides `name`:

1. `_attr_name`, set only by `conv.option['name']` or by a platform that names an entity outright.
2. `translations/<lang>.json` for the platform, via `Entity.name`.
3. `_spec_name`, from the MIoT spec and the built-in dictionaries.
4. None — the entity is the device.

`Entity.name` cannot be consulted before an entity joins a platform: it dereferences platform data to build the translation key and raises `AttributeError` when a `translation_key` is set and platform data is not. The override therefore checks `platform_data` first and degrades to `_spec_name`, which is also what makes the entities constructible in tests.

The legacy hierarchy keeps `_name` as its source and only adds the main-service case, because `MiotEntity` builds `_name` as `"<device name> <service description>"` before Home Assistant is involved.

### Buttons per property value

`ButtonEntity.on_init` appends a value description to distinguish one button per enum value. That name is now set as `_attr_name` with the translation key cleared, because a translation keyed on the property would otherwise collapse every value button onto one name.

## Compatibility

`unique_id` is unaffected: it is built from `device.unique_id` and the converter's service iid, action or property unique name, none of which reads a name.

`entity_id` is unaffected twice over. The integration derives it from model, MAC and the spec's `desc_name`, never from `_attr_name`; and `entity_registry.async_get_or_create()` returns the existing entry for a known `unique_id`, updating `original_name` and leaving `entity_id` alone. Only an explicit `new_entity_id`, which is a user rename, changes it.

What does change is `original_name` in the registry and the rendered friendly name, for the main entity of every device that has one. An existing user rename in the entity registry keeps winning, since Home Assistant applies it above everything here.

`_unprefix_original_name()` in Home Assistant returns None as soon as `has_entity_name` is set, so no de-duplication arrives from Home Assistant's side. The integration has to be correct on its own.

## Testing Strategy

### Naming rules

`tests/test_entity_naming.py` covers the two pure functions against a table of prefixes, boundaries, empty values and missing device names, plus the legacy `MiotEntity.name` and the sub-entity round trip through a stubbed device. No fixtures, no `hass`.

### Naming by model

`tests/test_naming_by_model.py` runs real specs, saved verbatim from miot-spec.org, through converter creation and asserts the resulting entity table: domain, `entity_id`, `unique_id`, name and translation key.

- `xiaomi.derh.lite` — a `device:dehumidifier`, twelve entities, one of which is the device.
- `lumi.switch.n3acn3` — a `device:switch` with three `service:switch`; every gang keeps its name.
- `chuangmi.plug.212a01` — a `device:outlet` with a `service:switch`; no main service until the customize names one.
- `cnhdm.airrtc.wkq01` — a `device:thermostat` whose extra climate entities carry explicit names, checked in `tests/test_cnhdm_airrtc_wkq01.py`.

Three invariants sit alongside the tables:

- Every generated `entity_id` is valid and lives in its platform's domain, which Home Assistant turns into errors in 2027.2 and 2027.5.
- Every nameless entity is either the main entity or has a name in `en.json`.
- No translation file gives a `name` to a main-service translation key, which would put the duplication back.

## Acceptance Criteria

- A dehumidifier named "Deumidificatore" renders its main entity as "Deumidificatore", not "Deumidificatore Deumidificatore".
- The other eleven entities of `xiaomi.derh.lite` keep their names and their `unique_id`s.
- A three gang switch names all three gangs.
- A plug with `main_service: switch` renders its switch entity as the device name, and its indicator light as "<device> Indicator Light".
- A name in `translations/<lang>.json` overrides the MIoT spec for every entity kind.
- The full suite passes on Home Assistant 2026.8 under Python 3.14.
