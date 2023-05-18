# Homeassistant E3DC Integration - Git Version

This integration will interface with the E3DC Storage systems supprting the RCSP
protocol. It is based on [python-e3dc](https://github.com/fsantini/python-e3dc).
This repository delivers the latest features via HACS. You can use it for
testing until I can get the integration accepted to HA core (no timeline for
that, sorry).

## Installation

1. Using the tool of choice open the directory (folder) for your HA
   configuration (where you find `configuration.yaml`).
1. If you do not have a `custom_components` directory (folder) there, you need
   to create it.
1. In the `custom_components` directory (folder) create a new folder called
   `e3dc`.
1. Download *all* the files from the `custom_components/e3dc/` directory
   (folder) in this repository.
1. Place the files you downloaded in the new directory (folder) you created.
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
