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
tracker. In the course of working with you, I'll probably want a diagnostic
dump. As the dump will contain probably sensitvie information like MAC adresses,
serial numbers etc., I recommend not to attach this to the issue directly, get
in touch on the issue and I'll give you a filedrop hosted on a private server of
me.

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

- **Username:** Your E3DC portal user name
- **Password:** Your E3DC portal password
- **Hostname:** The Hostname or IP address of the E3/DC system
- **RSCP Password:** This is the encryption key used in RSCP communications. You
  have to set on the device under *Main Page -> Personalize -> User profile ->
  RSCP password.*

### RSCP configuration

Right now, the integration will use the default configuration provided by
pye3dc. Additional PVIs, powermeters or batteries not covered yet by an option
flow. You can find details about these options at the [pye3dc
readme](https://github.com/fsantini/python-e3dc#configuration). I will plan to
add options to configure this in the long run. Please file an issue if you need
changes here, as I will need ral life examples to get these things running.

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

## Upstream source

The extension is based on [Python E3DC
library](https://github.com/fsantini/python-e3dc) from @fsantini. The general considerations mentioned in his project do apply to this integration.

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
[forum]: https://community.home-assistant.io/
[hacs]: https://github.com/hacs/integration
[hacs-shield]: https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge&logo=homeassistantcommunitystore
[license-shield]: https://img.shields.io/github/license/torbennehmer/hacs-e3dc?style=for-the-badge&color=blue&logo=gnu
[maintainer]: https://img.shields.io/badge/Maintainer-Torben%20Nehmer-blue?style=for-the-badge&logo=github
[prereleases-shield]: https://img.shields.io/github/v/release/torbennehmer/hacs-e3dc?include_prereleases&style=for-the-badge&logo=git
[releases-shield]: https://img.shields.io/github/v/release/torbennehmer/hacs-e3dc?style=for-the-badge&logo=homeassistantcommunitystore
[releases]: https://github.com/torbennehmer/hacs-e3dc/releases
