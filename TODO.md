# NetForge TODO

Feature ideas based on the current app structure and product scope.

## High Priority

- [ ] Add configuration validation before render
  Validate IP addresses, subnet masks, VLAN IDs, empty required fields, duplicate interface assignments, overlapping ranges, and roles that reference undefined variables.

- [ ] Add Jinja variable checking and preview helpers
  Show missing variables, unused variables, and a small rendered preview for role templates and custom base sections before the user generates a full config.

- [ ] Add model/profile compatibility checks
  Warn when a site profile assigns interfaces that do not exist on the selected model or stack size.

- [ ] Add batch generation from CSV
  Let users import a CSV of hostnames, management IPs, gateways, passwords, and profile selections to generate many switch configs in one pass.

- [ ] Add per-project settings snapshots
  Save timestamped backups of models, roles, profiles, and base settings so users can roll back bad edits without replacing everything from a ZIP import.

- [ ] Add a saveable generation session
  Save and reload the Step 1 to Step 3 wizard state for a switch that is in progress, including chosen model, profile, assignments, and switch details.

## Workflow Improvements

- [ ] Add clone/duplicate actions for models, roles, and profiles
  Most edits will be variants of an existing object. A duplicate action would be faster and safer than creating each item from scratch.

- [ ] Add search and filtering in the editor tabs
  Search boxes for models, roles, and profiles would keep the UI usable once teams build a larger library of templates.

- [ ] Add partial import/export
  Export or import a single model, role, or profile instead of only moving the full settings bundle.

- [ ] Add a config diff view
  Compare the newly generated config against a previously saved config or the current preview so engineers can see exactly what changed.

- [ ] Add output naming templates
  Support file naming patterns like `{{ hostname }}_{{ profile }}_{{ date }}` when saving generated configs or batch output.

- [ ] Add quick-copy actions for sections
  Copy only the management VLAN block, only interface configs, or only the base/global sections instead of always copying the full config.

## Data Model Enhancements

- [ ] Add structured role parameters
  Let a role define its own expected fields, defaults, and descriptions so the UI can prompt for role-specific inputs instead of relying only on freeform profile variables.

- [ ] Add model capability flags
  Track details like OOB port support, stack support, uplink types, and Layer 3 capability explicitly instead of inferring behavior only from interface names.

- [ ] Add interface tags or groups
  Support logical groups like `user-access`, `uplink`, `ap-ports`, or `camera-ports` so profiles can target groups instead of repeating raw interface ranges.

- [ ] Add profile inheritance
  Allow a site profile to extend a base profile and override only a few VLANs, variables, or port assignments.

- [ ] Add optional per-site custom sections
  Today custom sections are global. Site-specific custom sections would help with SNMP, logging, NTP, DHCP snooping, or ACL blocks that vary by location.

## Quality Of Life

- [ ] Add inline validation feedback in the UI
  Highlight invalid fields directly in the form instead of showing only message boxes after the user clicks save or generate.

- [ ] Add a dry-run summary panel
  Show a short summary before render: selected model, stack size, number of assigned ports, management VLAN, unresolved variables, and disabled-port coverage.

- [ ] Add recent files and recent profiles
  Keep a short history of recently opened settings ZIPs, recently used profiles, and recently generated configs.

- [ ] Add keyboard shortcuts
  Shortcuts for generate, copy, save, next/back step, and quick navigation between tabs would speed up daily use.

- [ ] Add dark/light theme polish and custom themes
  A simple theme editor or JSON-driven theme import would let teams standardize the UI without changing code.

## Longer-Term Ideas

- [ ] Add multi-vendor support behind a renderer abstraction
  Keep the current Cisco flow, but make room for separate renderers or template packs for other platforms later.

- [ ] Add syntax/test rules for generated configs
  Implement a lightweight rules engine that can flag likely IOS mistakes such as switchport commands on routed interfaces or missing dependencies between features.

- [ ] Add template packs and starter libraries
  Ship optional starter bundles for common campus, branch, and private VLAN use cases so first-time users can get productive faster.

- [ ] Add printable/exportable documentation for a profile
  Generate a human-readable profile summary showing VLANs, variables, interface roles, and custom sections for change review or peer approval.

## Suggested First Slice

- [ ] Build validation and compatibility warnings first
  This is the highest-leverage improvement because it reduces bad configs without changing the basic workflow.

- [ ] Add duplicate actions next
  This is a small implementation with immediate day-to-day value.

- [ ] Add batch generation after that
  This turns the tool from a single-switch helper into a stronger operational workflow tool.