# Homeassistant E3DC Integration - Git Version

[![hacs][hacs-shield]][hacs]
[![GitHub Release][releases-shield]][releases]
[![GitHub Prerelease][prereleases-shield]][releases]

![Project Maintenance][maintainer]
[![GitHub Activity][commits-shield]][commits]
[![License][license-shield]](LICENSE)

<!-- [![BuyMeCoffee][buymecoffeebadge]][buymecoffee] -->
<!-- [![Discord][discord-shield]][discord] -->
[![Community Forum][forum-shield]][forum]

This integration will interface with the E3DC Storage systems supprting the RCSP
protocol. It is based on [python-e3dc](https://github.com/fsantini/python-e3dc).
This repository delivers the latest features via HACS. You can use it for
testing until I can get the integration accepted to HA core (no timeline for
that, sorry).

If you encounter problems, please file an issue at the integrations issue
tracker. If possible, add a diagnostics dump always. This is important also for
enhancements if they target new data or information to be retrieved from the
unit to see what it has to offer. Always check that dump if you want to further
redact information in it. The MACs and the units serial number are redacted
already, but check for yourself! If you find information in the dump that you
consider private, please file a bug request so that I can update the anonymizing
code.

- [Disclaimer](#disclaimer)
- [Installation](#installation)
  - [HACS Installation](#hacs-installation)
  - [Manual Installation](#manual-installation)
- [Configuration](#configuration)
  - [RSCP configuration](#rscp-configuration)
  - [Localization](#localization)
  - [Probable causes of connection problems](#probable-causes-of-connection-problems)
    - [Password limitations](#password-limitations)
    - [Network restriction](#network-restriction)
  - [Unsupported features configuration schemes](#unsupported-features-configuration-schemes)
- [Actions](#actions)
  - [Set power limits](#set-power-limits)
  - [Clear current power limits](#clear-current-power-limits)
  - [Initate manual battery charging](#initate-manual-battery-charging)
  - [Set maximum wallbox charging current](#set-maximum-wallbox-charging-current)
  - [Set power mode](#set-power-mode)
- [Optional Battery Pack and Module Devices](#optional-battery-pack-and-module-devices)
- [Upstream source](#upstream-source)

## Disclaimer

This integration is provided without any warranty or support by E3DC
(unfortunately). I do not take responsibility for any problems it may cause in
all cases. Use it at your own risk.

## Installation

The recommend way to install this extension is using HACS. If you want more
control, use the manual installation method.

### HACS Installation

1. Go to *HACS -> Integrations*
1. Click the Triple-Dot menu on the top right and select *Custom Repositories*
1. Set `https://github.com/torbennehmer/hacs-e3dc.git` as repository name for
   the category *Integrations*
1. Open the repository (it will be displayed by default), select *Download* and
   confirm it
1. Restart Home Assistant
1. In the HA UI go to *Configuration -> Integrations* click "+" and search for
   "E3DC Remote Storage Control Protocol (Git)"

### Manual Installation

1. Using the tool of choice open the directory (folder) for your HA
   configuration (where you find `configuration.yaml`).
1. If you do not have a `custom_components` directory (folder) there, you need
   to create it.
1. In the `custom_components` directory (folder) create a new folder called
   `e3dc_rscp`.
1. Download *all* the files from the `custom_components/e3dc_rscp/` directory
   (folder) in this repository.
1. Place the files you downloaded in the new directory (folder) you created.
1. Restart Home Assistant
1. In the HA UI go to *Configuration -> Integrations* click "+" and search for
   "E3DC Remote Storage Control Protocol (Git)"

## Configuration

Once you add the integration, you'll be asked to authenticate yourself for a
local connection to your E3DC.

E3DC can be auto-discovered by Home Assistant. If an instance was found, it
will be shown as discovered. You can then set it up right away. In that case no
hostname has to be provided.

- **Username:** Your E3DC portal user name
- **Password:** Your E3DC portal password
- **Hostname:** The Hostname or IP address of the E3/DC system
- **RSCP Password:** This is the encryption key used in RSCP communications. You
  have to set on the device under *Main Page -> Personalize -> User profile ->
  RSCP password.*

If you have multiple E3DC instances configured as a farm, the integration will detect
the farming controller after configuring the first child of the farm and add it to the
discovered devices. It's fully configured, so you just need to add it to your HA. It
doesn't make any difference which child is configured first.

### RSCP configuration

Right now, the integration will use the default configuration provided by
pye3dc. Additional PVIs, powermeters, wallboxes or batteries not covered yet by an option
flow. You can find details about these options at the [pye3dc
readme](https://github.com/fsantini/python-e3dc#configuration). I will plan to
add options to configure this in the long run. Please file an issue if you need
changes here, as I will need ral life examples to get these things running.

### Localization

This integration is available in multiple languages:
- **English** (en) - Default language
- **German** (de) - Deutsche Übersetzung

The integration will automatically use the language configured in your Home
Assistant instance. All entity names, configuration dialogs, and service
descriptions are translated. To change the language, adjust your Home Assistant
language settings under *Settings -> System -> General*.

### Probable causes of connection problems

Based from my current experience, there may be a various problems when
connecting to an E3DC unit. Please be aware that it is not an exthaustive list,
also different E3DC types may behave slightly differently. I'll try to collect
the information I can deduce here and - if possible - forward them to the pye3dc
base lib where sensible.

#### Password limitations

According to bug reports, the usable characters of an RSCP key seem to be
limited. A user had problems when using a dot as a key element. If you get
strange authentication problems, try to start with a simple alphanumeric ASCII
based RSCP key, this is known to work in all cases.

#### Network restriction

E3DC units seem to listen only for connections on the same TCP/IP subnet. Access
from the outside must be proxied by a host on the local net. Connections from
other IP addresses will be blocked, even if, for example, you connect through an
VPN coming from other private networks.

A temporary solution, e.g. for testing, could be a simple SSH forward. However,
if you need a permanent solution, I would recommend using a [Traefik Reverse
Proxy](https://traefik.io/traefik/) on the E3DC net to act as an intermediate.
It will allow for a more detailed security setup.

A sample setup for Traefik might look like this (without any warranty), I use
this for my VPN setup:

```yaml
# Static config
entryPoints:
  e3dc.rscp:
    # External Port reachable through Traefik
    address: "10.11.12.10:5033/tcp"

# Dynamic config
tcp:
  routers:
    e3dc.rscp:
      entrypoints:
        - e3dc.rscp
      service: e3dc.rscp
      rule: "ClientIP(`10.0.0.0/8`)"
  services:
    e3dc.rscp:
      loadbalancer:
        servers:
          # E3DC Target IP
          - address: "10.11.12.15:5033"
```

### Unsupported features configuration schemes

Currently, the following features of pye3dc are not supported:

- Web Connections
- Local connections when offline, using the backup user.

## Actions

The integration currently provides these actions to initiate more complex
commands to the E3DC unit:

### Set power limits

Use the action `set_power_limits` to limit the maximum charging or discharging
rates of the battery system. Both values can be controlled individually, each
call replaces the settings made by the last. It will not allow you to change the
system defined minimum discharge rate at the moment, as I am not sure if this is
actually a sensible thing to do.

### Clear current power limits

`clear_power_limits` will drop any active power limit. It will not emit an error
if none has been set. Prefer this to use `set_power_limits` and setting the
values to the system defined maximum.

### Initate manual battery charging

The action `manual_charge` will start charging the specified amount of energy
into the battery, taking it from the grid if neccessary. The idea behind this is
to take advantage of dynamic electricity providers like Tibber. Charge your
battery when electricity is cheap even if you have no solar power available, for
example in windy winter nights/days.

**Read the following before using this functionality on your own risk:**

- Calls to this operation are rate-limited, your E3DC probaby will not accept
  more than one call every few hours. One unit reported to me had a wait time of
  two hours, apparently. The website mentions that this operation can only be
  called once a day and limits the charge amount to 3 kWh. This, again, is
  unconfirmed, so your milage may vary.
- Important from a monetary point of view: You will have losses from two AC/DC
  conversions (load and unload), as opposed to one when charging from the PV. A
  single conversion will probably cost you 10-15% in stored power. So, charging
  10 kWh from the Grid will approximate only 7-8 kWh when using it. Also, the
  wear on the battery should be considered. Following that, you'll want
  significant savings, not just a few cents.
- Check if your local laws and regulations do allow you to charge your battery
  from the grid for consuming power later in the first place.
- Check the impact on any warranty from E3DC you may have.

To stress this once more: Use this feature at your own risk.

### Set maximum wallbox charging current

The action `set_wallbox_charging_current` will set the maximum charging current
of the given Wallbox in Amps. 16A is typical for a 11kW Wallbox, 32A is typical
for a 22kW Wallbox.

**Read the following before using this functionality on your own risk:**

- If values cannot be set, this may be due to the hard limits for your fuses
  configured during the installation of the Wallbox. Only a E3DC service
  technican can and should change these limits.
- In case your fuse settings are wrong (too low) and you set the charging
  current too high, you may blow your fuse or even damage your Wallbox.
- Check your local laws and regulations whether setting the Wallbox to a higher
  charging current requires approvals from your grid operator.

### Set power mode

The action `set_power_mode` will set the power mode of the E3DC system. There are 4
different modes available:
- `normal`: Normal operation mode, the system will charge and discharge the
  battery as needed.
- `idle`: Idle mode, the system will not charge or discharge the battery.
- `charge`: Charge mode, the system will charge but will not discharge the
  battery.
- `charge from grid`: Charge from grid mode, the system will charge the battery
  from the grid but will not discharge it.
- `discharge`: Discharge mode, the system will discharge but will not charge
  the battery.

Charge and discharge modes need `power` to be set in Watts.

## Optional Battery Pack and Module Devices

The integration offers an option to create devices for the battery packs and battery modules. When enabled in the integration settings, additional devices will be created for each detected battery pack and module. These devices provide detailed diagnostic information about the state and health of your E3DC battery system.
Notes:

- on some E3DCs some Names of Batteries and Serial Numbers are reported back as "TODO". This is not an error of the integration.

- The following battery pack sensors are calculated by this integration based on raw values from the E3DC energy management system:
  - **Design Energy**: Calculated as `(design capacity × (DCB count × design voltage)) / 1000` in kWh
  - **Full Energy**: Calculated as `(full charge capacity × (DCB count × design voltage)) / 1000` in kWh
  - **Remaining Energy**: Calculated as `(remaining capacity × module voltage) / 1000` in kWh
  - **Usable Remaining Energy**: Calculated as `(usable remaining capacity × module voltage) / 1000` in kWh
  - **State of Health**: Calculated as `(full charge capacity / design capacity) × 100` as percentage

- **Battery Module State of Health (SoH)**: The integration always calculates SoH from capacities using the formula `(full charge capacity / design capacity) × 100`. Some E3DC systems also report their own SoH value, which may differ from the calculated value. If your E3DC system provides device-reported SoH values, an additional diagnostic sensor "State of health (device-reported)" will be created (disabled by default) for comparison and debugging purposes. This sensor is only created for battery modules where the E3DC system actually provides a SoH value. The calculated SoH is used as the primary sensor for consistency and accuracy across all E3DC systems.

- due to the various possible configurations of batteries (different E3DC devices, different amount of battery packs and modules, farming setups, etc.), not all scenarios couldn't be tested. In case your setup is not represented correctly, open an issue including a diagnostic dump.

## Upstream source

The extension is based on [Python E3DC
library](https://github.com/fsantini/python-e3dc) from @fsantini. The general
considerations mentioned in his project do apply to this integration.

***

<!--
[buymecoffee]: https://www.buymeacoffee.com/ludeeus
[buymecoffeebadge]: https://img.shields.io/badge/buy%20me%20a%20coffee-donate-yellow.svg?style=for-the-badge
-->
[commits-shield]: https://img.shields.io/github/commit-activity/y/torbennehmer/hacs-e3dc?style=for-the-badge&logo=git
[commits]: https://github.com/torbennehmer/hacs-e3dc/commits/main
<!--
[discord]: https://discord.gg/Qa5fW2R
[discord-shield]: https://img.shields.io/discord/330944238910963714.svg?style=for-the-badge
-->
[forum-shield]: https://img.shields.io/badge/Community%20Forum-Home%20Assistant-blue?style=for-the-badge&logo=homeassistant
[forum]: https://community.home-assistant.io/t/e3dc-remote-storage-control-protocol-rscp/595280
[hacs]: https://github.com/hacs/integration
[hacs-shield]: https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge&logo=homeassistantcommunitystore
[license-shield]: https://img.shields.io/github/license/torbennehmer/hacs-e3dc?style=for-the-badge&color=blue&logo=gnu
[maintainer]: https://img.shields.io/badge/Maintainer-Torben%20Nehmer-blue?style=for-the-badge&logo=github
[prereleases-shield]: https://img.shields.io/github/v/release/torbennehmer/hacs-e3dc?include_prereleases&style=for-the-badge&logo=git
[releases-shield]: https://img.shields.io/github/v/release/torbennehmer/hacs-e3dc?style=for-the-badge&logo=homeassistantcommunitystore
[releases]: https://github.com/torbennehmer/hacs-e3dc/releases
