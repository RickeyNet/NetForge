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
