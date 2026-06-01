"""
Cisco Switch Initial Configuration Generator

A Windows GUI application that generates initial configurations for Cisco
switches.  Users define switch models, interface roles, site profiles, and
base settings as reusable presets - then pick a model + profile, fill in a
handful of per-switch values, and click Generate.

All definitions are stored as JSON in the data/ directory and persist between
sessions.  No org-specific data is shipped - everything is user-defined.
"""

from netforge.app import App, main

__all__ = ["App", "main"]

if __name__ == "__main__":
    main()
