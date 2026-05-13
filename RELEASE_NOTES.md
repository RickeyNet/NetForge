# NetForge v1.5.0 - Release Notes

## New Feature: Push Config to Switch (Console)

Step 3 of the Generate Config tab now has a **Push to Switch...** button that streams the generated config straight to a switch over its console port via a USB-to-serial adapter. No more copy/paste into PuTTY.

### How it works
- Pick the COM port (auto-detected from `pyserial`'s `list_ports`), baud rate (9600 default), and optional enable password.
- The dialog answers the day-0 setup-dialog prompt automatically (`Would you like to enter the initial configuration dialog?` -> no).
- Enters enable mode (handles the password prompt if you supplied one).
- Quiets the session with `terminal length 0` / `terminal width 511`.
- Sends the generated config **line by line**, waiting for the switch prompt between lines so a slow console doesn't drop characters. Falls back to a configurable inter-line delay if no echo arrives.
- Optional **Run 'write memory' when finished** checkbox saves to startup-config at the end.

### Transcript pane
- Everything the switch sends back is shown in a live scrollable transcript, so you can watch the push happen and spot errors immediately.
- Stop button halts the push mid-flight (the dialog warns if you try to close while one is still running).

### Requirements
- The `pyserial` package is now in `requirements.txt`. Install with `pip install -r requirements.txt` or `pip install pyserial`.
- If pyserial isn't installed, the button shows a friendly install-instructions dialog instead of crashing.

---

# NetForge v1.4.0 - Release Notes

## Major Feature: Layer 3 Support

NetForge now generates full Layer 3 configurations alongside the existing Layer 2 workflows. Site Profiles gain a new **Enable Layer 3** toggle that unlocks an L3 editor and tells the generator to emit routing-related blocks.

### Management Style
- Each Layer 3 profile picks how the switch's management IP is assigned:
  - **svi** - Management rides an SVI (same as L2). Emits `interface vlan<mgmt_vlan>` with the IP from Step 3.
  - **loopback** - Mgmt rides Loopback0. The wizard prompts for Loopback0 IP/Mask in Step 3.
  - **routed_uplink** - Mgmt rides one of the routed uplinks. No mgmt SVI is emitted.
- `ip default-gateway` is always emitted when a Default Gateway is set, regardless of mgmt_style.

### Routed Interfaces (Requires IP)
- Interface Roles now have a **Requires IP** checkbox - tick it for roles that turn an interface into an L3 routed port (no switchport).
- When a port is assigned to a Requires-IP role, the wizard's Step 3 grows an extra grid for per-switch IP/mask entry.
- Use `{{ ip }}` and `{{ mask }}` as placeholders in the role template.
- The Site Profile's new **Default Routed Mask** pre-fills the Mask column of every routed-interface row in Step 3 (useful for sites with uniform /30 point-to-points).

### SVIs
- Define VLANs that need an SVI on every switch at the site, with description and optional DHCP helper addresses.
- IPs and masks are entered per-switch in Generate Config Step 3 under **SVI IPs**.
- DHCP helpers render as `ip helper-address ...` lines.

### OSPF
- Per-profile OSPF block: process ID, passive-interface default toggle, passive interface list, and one or more `network ... area ...` statements.
- Router-ID is set per switch in Step 3 and defaults to the Loopback0 IP.

### BGP
- One or more BGP instances per profile, each rendering its own `router bgp <local_asn>` block.
- Each instance defines **Peer Slots** (remote ASN + description) that describe BGP neighbours present on every switch at the site.
- Per-switch values (neighbour IP, MD5 key, circuit ID) are filled in during Generate Config Step 3.

### Named Extended ACLs
- Profile-level structured ACL editor produces `ip access-list extended <name>` blocks.
- Each rule is either a remark (free-form comment) or a permit/deny with protocol, source + wildcard, destination + wildcard, and optional `log`.
- ACLs render in the post-interface section of the generated config.

### Static Routes + Auto Default Route
- Per-switch static routes are entered in Step 3 (prefix, mask, next-hop, optional description).
- When a Layer 3 device has a Default Gateway set and no user-supplied 0.0.0.0/0 entry, NetForge auto-emits `ip route 0.0.0.0 0.0.0.0 <gateway>`.

## New Feature: Multiple Base Settings Sets

- The Base Settings tab now supports multiple named sets, managed from a side-by-side list panel.
- Buttons: **+ Add**, **Duplicate**, **Set Default**, **Delete**.
- Each Site Profile picks one set via a **Base Settings** dropdown. If the named set is missing at generate time, the app falls back to the entry marked as default.
- Lets you keep different AAA / SSH / banner blocks per deployment type (corporate / lab / DMZ) and select the right one per profile.

## New Feature: Profile-Level Services (DNS, NTP, Clock)

Per-profile values render directly as IOS commands so different sites can point at different infrastructure without duplicating Base sets:

- **DNS Servers** - comma-separated name-server IPs, becomes `ip name-server ...` lines
- **NTP Servers** - comma-separated NTP server IPs, becomes `ntp server ...` lines
- **NTP Source Interface** - optional `ntp source <iface>`
- **NTP Auth Key ID + Key** - optional MD5 authenticated NTP
- **Clock Timezone** - free-form `clock timezone ...` value (e.g. `EST -5`)
- **Clock Summer-Time** - free-form `clock summer-time ...` value (e.g. `EDT recurring`)

## New Feature: Profile Credential Defaults

- Each Site Profile can carry optional defaults for **Local Username**, **Local User Password**, and **Enable Secret**.
- Selecting a profile pre-fills the matching fields in Generate Config Step 3.
- The wizard always lets you override per switch; per-switch edits are not written back to the profile.
- The renderer prefers per-switch `local_username` over the Base set's default.

## New Feature: Local Username Field in Step 3

- Step 3 (Switch Details) gains a **Local Username** field alongside Enable Secret / Admin Password so the active user is visible and editable per switch.

## New Theme: Voyager

- Deep navy-blue background with warm orange accents - inspired by a starry-sky aesthetic.

## Theme Refinement: Sandstone

- Sandstone has been darkened and rebalanced for a more cohesive look:
  - Deeper olive-drab background with progressively darker panels and inputs (proper recessed hierarchy)
  - Warm cream foreground with muted khaki hints
  - Warm terracotta orange accent (replaces the previous maroon/dusty rose)
  - Darker borders for crisp panel definition

## UI Improvements

- **Sticky Save Profile button** - the Save Profile button on the Site Profiles tab is now pinned as a footer so it stays visible as the Layer 3 body grows.
- **Header / row alignment** - column headers in BGP Peer Slots, SVIs, and OSPF Networks now line up with their entry rows; "+ Add" buttons moved to the section hint row so they no longer disrupt the column grid.
- **Section hint text** - relocated long format hints from field-label parentheticals into section hints so labels like Clock Timezone, Clock Summer-Time, and NTP Auth Key are no longer truncated.
- **Em-dash cleanup** - replaced all em-dash characters with hyphens across docs and source for consistent typography in environments without Unicode rendering.

## Bug Fixes

- **Default gateway on Layer 3 devices** - `ip default-gateway` is now emitted in all `mgmt_style` modes when a value is set (previously gated to L2 / mgmt_style=svi only).
- **Routed Uplink template** - fixed a mismatched-brace typo in the bundled Routed Uplink role so per-switch `{{ ip }}` / `{{ mask }}` substitutions actually land in the config.
- **Role-template errors surface** - if a role template fails to render, the interface block now contains an `! ERROR rendering role '<name>': <exc>` comment instead of silently emitting the unrendered template.

---

# NetForge v1.3.0 - Release Notes

## New Feature: Work Order Number Field

- Step 3 (Switch Details) now includes a **Work Order #** field
- When filled in, the work order number appears as a comment in the generated config header: `! Work Order: <number>`
- `{{ work_order }}` is now a supported variable in the output filename template (Base Settings -> Filename Template)
  - Example: `{{ hostname }}_{{ work_order }}` produces `SW-CORE-01_WO-12345.txt`

## New Feature: Output Filename Templates

- Generated config filenames are now driven by a customizable **Filename Template** in Base Settings
- Supported variables: `{{ hostname }}`, `{{ model }}`, `{{ profile }}`, `{{ date }}`, `{{ work_order }}`
- Default template: `{{ hostname }}_{{ profile }}_{{ model }}_{{ work_order }}`
- Invalid filename characters are automatically stripped from the result

## New Feature: Quick-Copy Section Toolbar

- The config preview pane now has a **Copy section** toolbar with one button per named config section
- Sections: **Global / Base**, **VLANs**, **Interfaces**, **Management**, **Line Config**, **Banner / End**
- Buttons are enabled only after a config is generated and disabled when the section is empty
- Clicking a section button copies only that block to the clipboard

## New Feature: Recent Files Menu

- The **File** menu now contains three **Recent** sub-menus: **Recent Profiles**, **Recent Settings ZIPs**, and **Recent Configs**
- Recently used profiles are remembered and can be selected directly from the menu to jump straight to the Generate tab
- Recently imported settings ZIPs can be re-imported from the menu
- Recently saved configs can be re-opened into the config preview pane
- Up to 10 recent items are tracked per category and persisted across sessions

## New Feature: Duplicate Action for Models, Roles, and Profiles

- Models, Roles, and Profiles tabs now each have a **Duplicate** button
- Duplicating an item creates a copy with a unique name (e.g., `My Profile (copy)`)
- The duplicate is immediately selected and ready to edit

## New Feature: Checkbox Multi-Select Delete

- The item lists in Models, Roles, and Profiles tabs now use a checkbox-based list (`_CheckList`)
- Check multiple items and click **Delete** to remove them all at once
- Single-item delete still works by selecting (clicking) an item without checking it

## New Feature: Select All Button

- Models, Roles, and Profiles tabs now each have a **Select All** button
- Clicking it checks all checkboxes at once; clicking again unchecks all (toggle behavior)
- Works together with the multi-select Delete to quickly remove an entire list

## New Feature: Custom Theme Editor

- A new **Edit Custom Themes…** option is available at the bottom of the **Theme** menu
- The editor lets you create, duplicate, and delete custom color themes without touching any code
- Each of the 12 palette colors has a labeled text field and a clickable swatch that opens the system color picker - swatches update live as you type hex values
- **Preview** applies your colors to the running app immediately without saving
- **Save Theme** persists the theme to `theme.json`; it appears instantly as a new entry in the Theme menu under a separator below the built-in themes
- Custom themes survive restarts and are included in settings export/import ZIP files

## New Feature: Light Theme

- A new built-in **Light** theme is now available in the Theme menu
- Off-white background with blue accent, suitable as a clean light-mode alternative to the existing dark themes

## UI Improvements

- **Read-only config preview** - the config preview pane is now read-only; it can no longer be accidentally edited
- **Themed dialogs** - all info, warning, and error message boxes replaced with fully themed custom dialogs that match the active theme
- **Config preview cleared on back** - navigating back from Step 3 to Step 2 now clears the preview pane and disables the section copy buttons
- **Responsive section copy toolbar** - the Copy section buttons now shrink and grow with the window instead of overflowing off-screen at smaller widths

---

# NetForge v1.2.2 - Release Notes

## Fix: OOB Management Port (GigabitEthernet0/0) on C9300

- The disabled port template (which contains `switchport` commands) is no longer applied to the OOB management port - GigabitEthernet0/0 is a routed interface that does not accept switchport commands
- The `mgmt_port` base setting now renders with the correct `interface GigabitEthernet0/0` header

## New Feature: OOB Management Port IP Assignment

- Step 3 (Switch Details) now shows optional **OOB IP Address** and **OOB Subnet Mask** fields when the selected model has a GigabitEthernet0/0 port
- If both fields are filled in, GigabitEthernet0/0 is configured with the specified IP address
- If left blank, the default `mgmt_port` base setting is used as a fallback
- If a role is assigned to GigabitEthernet0/0 in the Step 2 port assignment table, that role's commands take priority over both the OOB fields and the base setting

## Model Update: C9300 Port Groups

- Added `GigabitEthernet1/1/1-4` port group to all C9300 switch models

---

# NetForge v1.2.0 - Release Notes

## Bug Fix: Management Port on C9200 Models

- The `mgmt_port` base setting (GigabitEthernet0/0 config) was being included in every generated config, even for switch models that don't have that interface
- Config generation now checks the selected model's port groups and only includes the management port block when a GigabitEthernet0/ interface exists (e.g., C9300 models)
- C9200 models no longer generate invalid GigabitEthernet0/0 config lines

## New Feature: Right-Click Context Menu

- All text fields, text areas, and the config preview now support a right-click context menu
- Menu includes **Cut**, **Copy**, **Paste**, and **Select All** with keyboard shortcut hints
- Read-only widgets (config preview, guide code blocks) show only Copy and Select All
- Menu items are contextually enabled/disabled based on selection and clipboard state
- Styled to match the active theme

## New Theme: Sandstone

- Added a warm, light-mode theme with olive/sage backgrounds, cream input fields, and dusty rose accents

| Theme         | Description                                                         |
|---------------|---------------------------------------------------------------------|
| **Sandstone** | Warm olive-sage background with cream inputs and dusty rose accents |

## UI Improvements

- **Themed combo dropdowns** - combobox dropdown lists now match the active theme instead of showing a white system default
- **Themed menu bar** - replaced the native Windows menu bar with a custom frame-based menu bar that fully respects theme colors
- **Guide headings** - heading text in the How-To Guide now uses the theme accent color instead of hardcoded white, improving readability on light themes

## Wizard: Back Button Clears Preview

- Pressing the Back button on Step 3 (Switch Details) now clears the generated config preview
- All input fields (hostname, IP, passwords, etc.) are preserved when navigating back

---

# NetForge v1.1.0 - Release Notes

## New Feature: Theme Selector

- Added a **Theme** menu in the menu bar for switching between colour themes
- Themes apply instantly - all tabs, menus, and widgets update in place
- Selected theme is saved to `data/theme.json` and persists across sessions
- Theme preference is included in Settings Export/Import

### Included Themes

| Theme | Description |
|-------|-------------|
| **Default** | The original grey/black dark mode palette |
| **Coral** | A deep ocean-teal background with warm coral accents |

---

# NetForge v1.0.1 - Release Notes

## New Feature: Custom Config Sections in Base Settings

- Add your own IOS config sections (SNMP, NTP, QoS, DHCP Snooping, ACLs, etc.) directly in Base Settings
- Each custom section includes a name, position control (before or after interfaces), and a raw IOS command block
- Sections are included in every generated config
- Supports Jinja2 `{{ variable }}` placeholders - values are pulled from the Site Profile's Role Variables
- Add as many sections as needed using the "+ Add Section" button

---

# NetForge v1.0.0 - Release Notes

## Overview
NetForge is a standalone Windows desktop application for generating initial configurations for Cisco switches. It provides a dark-themed GUI wizard where network engineers define switch models, interface roles, site profiles, and base IOS settings as reusable presets - then generate complete, ready-to-paste configurations in seconds.

## Features

### Configuration Generator (3-Step Wizard)
- Select a switch model and site profile
- Review and customize port assignments per switch
- Enter per-switch details (hostname, credentials, IPs)
- Generate, copy to clipboard, or save config to file

### Switch Models
- Define any Cisco switch model with its port groups (prefix, start, end)
- Stack support - automatically replicates port groups across stack members (up to 4)
- Provision type for `switch X provision` commands

### Interface Roles
- Create reusable port configuration templates (access, trunk, private VLAN, etc.)
- Jinja2 variable support (`{{ description }}`, `{{ access_vlan }}`, etc.)

### Site Profiles
- Define VLAN configurations, role variables, and default port assignments per site
- Variables feed into role templates for site-specific values (VLAN IDs, allowed VLANs, etc.)

### Base Settings
- Global IOS command sections: services, VRF, logging, AAA, security, SSH/crypto, STP, line config, banner
- Disabled port template with variable support for security baseline
- Configurable port display mode (range vs. individual)

### Built-in How-To Guide
- Step-by-step setup instructions with IOS command examples embedded in the app

## Technical Details
- **Platform:** Windows (standalone .exe via PyInstaller)
- **Dependencies:** Python, Tkinter, Jinja2
- **Data storage:** Local JSON files in `data/` directory
- **Fully offline** - no network connections, no telemetry, no external services
- **Dark mode UI** with Segoe UI / Consolas fonts

## Pre-loaded Data
- 7 switch models (C9200CX, C9200L, C9300 with 1-4 stack variants)
- 5 interface roles (Private VLAN Promiscuous/Isolated, Trunk to Switch/Firewall, Access Port)
- Sample base settings with AAA, SSH, STP, and security defaults
