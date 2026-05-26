# NetForge

A standalone Windows desktop application for generating initial configurations for Cisco switches.

NetForge lets network engineers define switch models, interface roles, site profiles, and base IOS settings as reusable presets - then generate complete, ready-to-paste configurations through a simple 3-step wizard.

## Features

- **3-Step Config Wizard** - Select model & site, review port assignments, enter switch details, generate
- **Switch Models** - Define hardware port groups with stack support (up to 4 members)
- **Interface Roles** - Reusable per-port IOS command templates with Jinja2 variables
- **Site Profiles** - VLAN definitions, role variables, and default port assignments per site
- **Base Settings** - Global IOS commands shared across all switches (AAA, SSH, STP, security, etc.)
- **Disabled Port Template** - Automatic security baseline applied to all unassigned ports
- **Built-in How-To Guide** - Step-by-step setup instructions with IOS command examples
- **Dark Mode UI** - Easy on the eyes during long configuration sessions
- **Fully Offline** - No network connections, no telemetry, no external services

## Quick Start

### Option 1: Run the Executable
Download `NetForge.exe` from the latest release and run it. No installation required.

### Option 2: Run from Source
```bash
# Clone the repository
git clone https://github.com/RickeyNet/NetForge.git
cd NetForge

# Create a virtual environment
python -m venv venv
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the app
python NetForge.py
```

## Building the Executable

```bash
# Install build dependencies
pip install pyinstaller jinja2

# Build using the spec file
pyinstaller NetForge.spec --noconfirm --clean
```

Or simply run `build.bat`. The output will be at `dist/NetForge.exe`.

## Setup Workflow

Complete the setup tabs in this order (one-time):

1. **Base Settings** - Global IOS commands shared by all switches
2. **Switch Models** - Hardware definitions (port groups, stack size, provision type)
3. **Interface Roles** - Reusable per-port command templates with `{{ variable }}` placeholders
4. **Site Profiles** - VLANs, variable values, and default port assignments

Then use the **Generate Config** tab for daily use.

## Pre-loaded Data

NetForge ships with sample data to get you started:

| Category        | Included                                                                 |
|-----------------|--------------------------------------------------------------------------|
| Switch Models   | C9200CX-12T-2X2G, C9200L-24T, C9200L-48T, C9300-24S (1-4 stack)          |
| Interface Roles | Private VLAN Promiscuous/Isolated, Trunk to Switch/Firewall, Access Port |
| Base Settings   | AAA, SSH/crypto, STP, security, disabled port template                   |

## Data Storage

All configuration data is stored as JSON files in the `data/` directory:

| File                 | Contents                                             |
|----------------------|------------------------------------------------------|
| `models.json`        | Switch model definitions and port groups             |
| `roles.json`         | Interface role command templates                     |
| `profiles.json`      | Site profiles with VLANs, variables, and assignments |
| `base_settings.json` | Global IOS settings shared across all configs        |

These files persist between sessions and can be backed up or shared with your team.

## Security Notes

NetForge is an offline staging tool. A few things to be aware of:

- **Credentials are stored and exported in plain text.** Enable secrets,
  local user passwords, SNMP communities, and NTP/BGP keys you enter into
  profiles or base settings are saved as-is in `profiles.json` /
  `base_settings.json`, and are included verbatim in any **Export Settings**
  ZIP and in every generated config file. Treat those files (and the ZIPs)
  as sensitive: don't commit them to source control or drop them in a
  shared/cloud-synced folder.
- **Generated `username ... secret <pw>` lines are type-0 (cleartext).**
  The switch re-hashes them on paste, so the running config is fine, but
  the saved `.txt` you paste *from* contains the cleartext password. Delete
  generated config files once the switch is provisioned. For stored
  credentials prefer `enable secret` (already used) over `enable password`.
- **Only import settings ZIPs you trust.** Imported `roles.json` /
  `profiles.json` supply Jinja2 command templates that are rendered when
  you generate a config. Templates run in a sandbox, but importing
  untrusted settings can still overwrite your data with bad configs.

## Requirements

- Windows 10/11
- Python 3.8+ (if running from source)
- Jinja2 (`pip install jinja2`)

## License

Released under the [MIT License](LICENSE).
