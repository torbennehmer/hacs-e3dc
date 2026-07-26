---
description: "Use when adding or changing entities on any E3DC platform (sensor, binary_sensor, switch, button, number): entity descriptions, unique IDs, child/wallbox entities, action lambdas, icons."
applyTo: "custom_components/e3dc_rscp/{sensor,binary_sensor,switch,button,number}.py"
---

# Entity Platforms

All five platforms share one structure. Only the parts below differ per platform; everything else is
identical, so read the sibling platform file for a working example before inventing something new.

## Shared skeleton

```python
class E3DCSensor(CoordinatorEntity, SensorEntity):   # E3DCBinarySensor, E3DCSwitch, E3DCButton, E3DCNumber
    _attr_has_entity_name: bool = True

    def __init__(
        self,
        coordinator: E3DCCoordinator,
        description: E3DCSensorEntityDescription,   # per-platform subclass
        uid: str,
        device_info: DeviceInfo | None = None,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{uid}_{description.key}"
```

- `uid` is **passed in**; it is never read off the coordinator. Main-device entities get
  `entry.unique_id`, child entities get the child's uid (see below).
- `description.key` **is** the key into `coordinator.data`. There is no separate `data_key` field on
  any platform.
- `_attr_unique_id` is `f"{uid}_{description.key}"` on every platform. Never change an existing `key`.

## Per-platform entity description subclasses

Each platform declares its own frozen dataclass **in its own file** (not in `const.py`):

| File | Class | Extra fields |
| --- | --- | --- |
| `sensor.py` | `E3DCSensorEntityDescription(SensorEntityDescription)` | `icons: dict[str, str] = None` |
| `binary_sensor.py` | `E3DCBinarySensorEntityDescription(BinarySensorEntityDescription)` | `on_icon`, `off_icon` (`str \| None`) |
| `switch.py` | `E3DCSwitchEntityDescription(SwitchEntityDescription)` | `on_icon`, `off_icon`, `async_turn_on_action`, `async_turn_off_action` |
| `button.py` | `E3DCButtonEntityDescription(ButtonEntityDescription)` | `icon`, `async_press_action` |
| `number.py` | `E3DCNumberEntityDescription(NumberEntityDescription)` | `async_set_native_value_action` |

Action callable signatures — note `number` takes **three** arguments:

```python
# switch.py / button.py
Callable[[E3DCCoordinator], Coroutine[Any, Any, bool]] | None
# number.py
Callable[[E3DCCoordinator, float, int], Coroutine[Any, Any, bool]] | None
```

`sensor.py` uses `@dataclass(frozen=True)`; the other four use `@dataclass(slots=True, frozen=True)`.

## Reading state

| Platform | How state is read |
| --- | --- |
| `binary_sensor` | `is_on` property returns `self.coordinator.data.get(self.entity_description.key)` |
| `sensor` | `native_value` property reads from `coordinator.data` |
| `switch` | **not** a property — `_attr_is_on` is set in `__init__` and refreshed in `_handle_coordinator_update` |
| `number` | **not** a property — `native_value` returns `self._attr_value`, set in `__init__` and refreshed in the callback |
| `button` | stateless |

For `switch` and `number` a new value must be assigned to the `_attr_*` field inside
`_handle_coordinator_update()` followed by `self.async_write_ha_state()`; returning it from a property
is not enough.

## Child (wallbox / battery) entities

Child entities reuse the same entity class but receive the child's uid and `DeviceInfo`. The uid is dug
out of the device identifiers tuple:

```python
device_info = wallbox["deviceInfo"]
assert "identifiers" in device_info and device_info["identifiers"]
unique_id = list(device_info["identifiers"])[0][1]
```

Guard battery entities with `if coordinator.create_battery_devices:` before adding them.

## Action lambdas must capture the index as a default argument

Descriptions are built inside a `for wallbox in ...` loop, so the loop variable must be bound at
creation time via a default argument — otherwise every entity ends up pointing at the last wallbox:

```python
# switch.py
async_turn_on_action=lambda coordinator,
index=wallbox["index"]: coordinator.async_set_wallbox_sun_mode(True, index),

# number.py — value first, then the captured index
async_set_native_value_action=lambda coordinator,
value,
index=wallbox["index"]: coordinator.async_set_wallbox_max_charge_current(int(value), index),
```

`number.py` casts the incoming `float` to `int` before handing it to the coordinator.

## Optimistic writes

`switch.async_turn_on` / `async_turn_off` set `_attr_is_on` and call `async_write_ha_state()` **before**
awaiting the action, so the UI reacts immediately. If the device rejects the change the next coordinator
poll corrects it. Keep this ordering; it pairs with the coordinator's update guards.

## Icons

- `sensor.py` maps a state string to an icon through the `icons` dict on the description, falling back to
  `entity_description.icon`.
- `binary_sensor.py` / `switch.py` pick between `on_icon` and `off_icon` based on current state.
- Omit icons entirely when the `device_class` already implies a sensible one.

## Translations

Every `translation_key` needs an entry at `entity.{platform}.{translation_key}.name` in
[strings.json](custom_components/e3dc_rscp/strings.json) **before** it is referenced in code.

## Known violation — do not copy

[sensor.py](custom_components/e3dc_rscp/sensor.py#L6) does `from e3dc._rscpTags import PowermeterType`,
which breaks the rule that pye3dc is only imported in `e3dc_proxy.py`. Treat it as debt, not precedent.
