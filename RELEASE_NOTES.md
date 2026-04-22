# NetForge v1.3.0 — Release Notes

## New Feature: Work Order Number Field

- Step 3 (Switch Details) now includes a **Work Order #** field
- When filled in, the work order number appears as a comment in the generated config header: `! Work Order: <number>`
- `{{ work_order }}` is now a supported variable in the output filename template (Base Settings → Filename Template)
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

## UI Improvements

- **Read-only config preview** — the config preview pane is now read-only; it can no longer be accidentally edited
- **Themed dialogs** — all info, warning, and error message boxes replaced with fully themed custom dialogs (`_dialog` and `_ask`) that match the active theme
- **Config preview cleared on back** — navigating back from Step 3 to Step 2 now clears the preview pane and disables the section copy buttons

---

# NetForge v1.2.2 — Release Notes

## Fix: OOB Management Port (GigabitEthernet0/0) on C9300

- The disabled port template (which contains `switchport` commands) is no longer applied to the OOB management port — GigabitEthernet0/0 is a routed interface that does not accept switchport commands
- The `mgmt_port` base setting now renders with the correct `interface GigabitEthernet0/0` header

## New Feature: OOB Management Port IP Assignment

- Step 3 (Switch Details) now shows optional **OOB IP Address** and **OOB Subnet Mask** fields when the selected model has a GigabitEthernet0/0 port
- If both fields are filled in, GigabitEthernet0/0 is configured with the specified IP address
- If left blank, the default `mgmt_port` base setting is used as a fallback
- If a role is assigned to GigabitEthernet0/0 in the Step 2 port assignment table, that role's commands take priority over both the OOB fields and the base setting

## Model Update: C9300 Port Groups

- Added `GigabitEthernet1/1/1–4` port group to all C9300 switch models

---

# NetForge v1.2.0 — Release Notes

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

- **Themed combo dropdowns** — combobox dropdown lists now match the active theme instead of showing a white system default
- **Themed menu bar** — replaced the native Windows menu bar with a custom frame-based menu bar that fully respects theme colors
- **Guide headings** — heading text in the How-To Guide now uses the theme accent color instead of hardcoded white, improving readability on light themes

## Wizard: Back Button Clears Preview

- Pressing the Back button on Step 3 (Switch Details) now clears the generated config preview
- All input fields (hostname, IP, passwords, etc.) are preserved when navigating back

---

# NetForge v1.1.0 — Release Notes

## New Feature: Theme Selector

- Added a **Theme** menu in the menu bar for switching between colour themes
- Themes apply instantly — all tabs, menus, and widgets update in place
- Selected theme is saved to `data/theme.json` and persists across sessions
- Theme preference is included in Settings Export/Import

### Included Themes

| Theme | Description |
|-------|-------------|
| **Default** | The original grey/black dark mode palette |
| **Coral** | A deep ocean-teal background with warm coral accents |

---

# NetForge v1.0.1 — Release Notes

## New Feature: Custom Config Sections in Base Settings

- Add your own IOS config sections (SNMP, NTP, QoS, DHCP Snooping, ACLs, etc.) directly in Base Settings
- Each custom section includes a name, position control (before or after interfaces), and a raw IOS command block
- Sections are included in every generated config
- Supports Jinja2 `{{ variable }}` placeholders — values are pulled from the Site Profile's Role Variables
- Add as many sections as needed using the "+ Add Section" button

---

# NetForge v1.0.0 — Release Notes

## Overview
NetForge is a standalone Windows desktop application for generating initial configurations for Cisco switches. It provides a dark-themed GUI wizard where network engineers define switch models, interface roles, site profiles, and base IOS settings as reusable presets — then generate complete, ready-to-paste configurations in seconds.

## Features

### Configuration Generator (3-Step Wizard)
- Select a switch model and site profile
- Review and customize port assignments per switch
- Enter per-switch details (hostname, credentials, IPs)
- Generate, copy to clipboard, or save config to file

### Switch Models
- Define any Cisco switch model with its port groups (prefix, start, end)
- Stack support — automatically replicates port groups across stack members (up to 4)
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
- **Fully offline** — no network connections, no telemetry, no external services
- **Dark mode UI** with Segoe UI / Consolas fonts

## Pre-loaded Data
- 7 switch models (C9200CX, C9200L, C9300 with 1-4 stack variants)
- 5 interface roles (Private VLAN Promiscuous/Isolated, Trunk to Switch/Firewall, Access Port)
- Sample base settings with AAA, SSH, STP, and security defaults
