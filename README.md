# NetForge

A standalone Windows desktop application for generating initial configurations for Cisco Catalyst switches.

NetForge lets network engineers define switch models, interface roles, site profiles, and base IOS settings as reusable presets, then generate complete, ready-to-paste configurations through a 3-step wizard. Layer 2 access switches and Layer 3 distribution switches (Loopback0, routed uplinks, OSPF, SVIs) are both supported, and finished configs can be pasted manually or pushed directly over a USB-to-serial console cable.

## Features

### Config generation
- **3-step config wizard** - pick model + site, review/override port assignments, fill in per-switch details, generate.
- **Switch models** - hardware port-group definitions with stack support (up to 4 members) and OOB-port awareness.
- **Interface roles** - reusable per-port IOS command templates with Jinja2 variables, including `requires_ip` roles that prompt for per-port IP/mask in Step 3.
- **Site profiles** - VLAN definitions, role variables, default port assignments, SVIs, OSPF settings, NTP/DNS, ACLs, and L2/L3 mode selection per site.
- **Base settings** - global IOS commands shared across all switches, organized into spreadsheet-aligned sections (Basic Configuration, Services and Functions, IP Services, Snooping, HTTP Server, Mgmt VRF, AAA Password Policy / RADIUS / Local Account, SSH, Logging, Archive, VTY, Miscellaneous).
- **Custom config sections** - pre-interface and post-interface text blocks for things like management ACLs, DHCP/IGMP snooping, NTP, SNMPv3.
- **Disabled-port template** - automatic security baseline applied to every unassigned port.
- **Layer 3 support** - Loopback0, routed uplinks with per-switch IP/mask grid, OSPF (router-id, passive-interface, networks), SVIs with helper-addresses, static routes, `mgmt_style=loopback`.

### Delivery
- **Push to switch (serial console)** - stream a generated config to a switch over a USB-to-serial cable, with optional auto-save to startup-config and password redaction in the transcript. Requires `pyserial`.
- **Filename templates** - configurable output naming patterns (e.g. `{{ hostname }}_{{ profile }}`).
- **Quick-copy actions** - copy individual sections (management block, interfaces, base/global) instead of the full config.

### Workflow & UI
- **Template packs** - importable bundles that pre-populate a working L2 or L3 baseline (see `template_packs/`).
- **Import / Export Settings (ZIP)** - move or back up your full settings bundle.
- **Base Settings search** - case-insensitive substring search across every section with highlight and section-count summary.
- **Clone / duplicate** actions for models, roles, and profiles.
- **Recent files & recent profiles**, **keyboard shortcuts**, **custom themes**, **dark mode UI**.
- **Built-in How-To Guide** - in-app step-by-step setup tab.
- **Offline-only** - no network connections, no telemetry, no external services. (The optional console push is over a local serial cable, not a network.)

## Quick Start

### Option 1: Run the executable
Download `NetForge.exe` from the latest release and run it. No installation required.

### Option 2: Run from source
```bash
git clone https://github.com/RickeyNet/NetForge.git
cd NetForge

python -m venv venv
venv\Scripts\activate

pip install -r requirements.txt

python NetForge.py
```

## Getting Started

You have two on-ramps:

### Fast path: import a template pack
The repo ships two hardened baselines under `template_packs/`:

| Pack                  | Target                                                                       |
|-----------------------|------------------------------------------------------------------------------|
| `cisco_l2_baseline`   | Cisco 9300/9200 hardened Layer 2 access switch.                              |
| `cisco_l3_baseline`   | Cisco 9300 hardened Layer 3 distribution switch (Loopback0, OSPF, SVIs).     |

Use **Settings -> Import Settings** and point it at the pack's `.zip` (or the contained JSONs). See `template_packs/README.md` for what each pack covers and what placeholders you need to fill in per site.

### Manual path: build from scratch
Complete the setup tabs in this order (one-time):

1. **Base Settings** - global IOS commands shared by all switches.
2. **Switch Models** - hardware definitions (port groups, stack size, provision type, OOB port).
3. **Interface Roles** - reusable per-port command templates with `{{ variable }}` placeholders.
4. **Site Profiles** - VLANs, SVIs, OSPF, variable values, default port assignments.

Then use the **Generate Config** tab for daily use.

## The Generate Config Wizard

- **Step 1 - Model & Site.** Pick a switch model (and stack size) plus a site profile.
- **Step 2 - Port Assignments.** Profile defaults are pre-applied; override per-port roles as needed.
- **Step 3 - Per-switch Details.** Hostname, secret, admin password, domain, management VLAN / IP / gateway (L2) or Loopback0 IP, routed-uplink IP/mask grid, OSPF router-id, static routes (L3), OOB IP, plus any per-switch role variables.

Then **Preview** to render, copy/save, or **Push to Switch** to deliver.

## Data Storage

All configuration data is stored as JSON files in the `data/` directory:

| File                 | Contents                                                                                    |
|----------------------|---------------------------------------------------------------------------------------------|
| `models.json`        | Switch model definitions and port groups.                                                    |
| `roles.json`         | Interface role command templates.                                                           |
| `profiles.json`      | Site profiles with VLANs, SVIs, OSPF, variables, and port assignments.                       |
| `base_settings.json` | Global IOS settings shared across all configs.                                              |
| `recent.json`        | Recently used settings ZIPs, profiles, and generated configs.                                |
| `theme.json`         | Saved custom theme.                                                                         |
| `hidden.json`        | Per-user UI preferences (hidden items, etc.).                                               |

These files persist between sessions and can be backed up or shared with your team via **Export Settings**.

## Building the Executable

```bash
pip install pyinstaller
pyinstaller NetForge.spec --noconfirm --clean
```

Or simply run `build.bat`. The output will be at `dist/NetForge.exe`.

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
  you generate a config. Templates run in a sandboxed Jinja2 environment
  with Zip-Slip protection on import, but importing untrusted settings
  can still overwrite your data with bad configs.
- **Console push transcript redacts the enable password**, but the
  generated config file itself contains all secrets in cleartext - delete
  it once the switch is provisioned.

## Requirements

- Windows 10/11
- Python 3.8+ (if running from source)
- Dependencies listed in `requirements.txt` (`jinja2`, `pyserial`)

## License

Released under the [MIT License](LICENSE).
