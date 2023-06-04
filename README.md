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

## Manual Installation

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

## HACS Installation

1. Go to *HACS -> Integrations*
1. Click the Triple-Dot menu on the top right and select *Custom Repositories*
1. Set `https://github.com/torbennehmer/hacs-e3dc.git` as repository name for
   the category *Integrations*
1. Open the repository (it will be displayed by default), select *Download* and
   confirm it
1. Restart Home Assistant
1. In the HA UI go to *Configuration -> Integrations* click "+" and search for
   "E3DC Remote Storage Control Protocol (Git)"

## Configuration is done in the UI

Right now, only local connections are supported by the integration, thus you'll need:

- Your user name
- Your password
- The Hostname or IP address of the E3/DC system
- The RSCP Password (encryption key), as set on the device under *Main Page ->
  Personalize -> User profile -> RSCP password*

**Not supported are:**

- Web Connections
- Local connections when offline, using the backup user.

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
