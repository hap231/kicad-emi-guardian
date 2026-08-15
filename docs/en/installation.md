# Installation, update, and uninstall

## Supported environment

- KiCad 10.0.5 or later
- Python 3.9 or later
- Windows, macOS, or Linux
- A board open in PCB Editor

KiCad 9 and earlier are not supported. Close every KiCad process before changing the installation.

## Recommended platform installers

### Windows

Extract `emi-guardian-0.0.2-windows-installer.zip` and run `Install-or-Update.cmd`. Use the same launcher for updates. Run `Uninstall.cmd` to remove it.

Default location:

```text
<Documents>\KiCad\10.0\plugins\emi-guardian\plugin.json
```

### macOS

Extract `emi-guardian-0.0.2-macos-installer.zip` and run `install-or-update.command`. If required:

```bash
chmod +x install-or-update.command uninstall.command
./install-or-update.command
```

Run `./uninstall.command` to remove it.

Default location:

```text
~/Documents/KiCad/10.0/plugins/emi-guardian/plugin.json
```

### Linux

```bash
chmod +x install-or-update.sh uninstall.sh
./install-or-update.sh
```

Run `./uninstall.sh` to remove it.

Default location:

```text
~/.local/share/KiCad/10.0/plugins/emi-guardian/plugin.json
```

## Installer behavior

The scripts install for the current user and create no backup copy of the previous plugin, including in the operating-system temporary directory. The new payload is staged and checked first; the existing destination is then removed and replaced. If final placement fails, the incomplete destination is deleted and the installer must be run again because automatic rollback is intentionally disabled. Legacy `_emi-guardian-backups` and stale staging directories are removed automatically. The KiCad-managed Python environment is removed so it is recreated on the next launch. Normal uninstall preserves settings and reports. Administrator privileges are not normally required.

## Manual installation

Extract the `emi-guardian` directory from `emi-guardian-0.0.2-manual-install.zip` into the platform `plugins` directory.

Correct structure:

```text
plugins/
└── emi-guardian/
    ├── plugin.json
    ├── requirements.txt
    ├── open_dashboard.py
    ├── quick_scan.py
    └── emi_guardian/
```

Do not leave `plugin.json` one directory deeper.

## KiCad configuration and launch

Open the KiCad-wide page:

```text
Preferences → Preferences... → Plugins
```

Enable the KiCad API, confirm the Python interpreter, fully restart KiCad, and open a board. Launch from:

```text
Tools → External Plugins → Open EMI Guardian
```

The first discovery can take time while KiCad creates the managed environment. Actions may not appear until environment creation succeeds.

## Update and uninstall

Run the platform Install-or-Update launcher without manually deleting the old version. Force-refresh the browser if old web assets remain. Use the platform Uninstall launcher to remove the plugin and managed environment; user data remains unless an explicit cleanup option is selected.

## Troubleshooting discovery

Verify `plugins/emi-guardian/plugin.json`, the KiCad-wide API setting, Python 3.9+, a full KiCad restart, and the plugin warnings at the lower right of PCB Editor. Re-running the installer is the safest way to rebuild the environment.

See the [user manual](user-manual.md) and [acceptance test](acceptance-test.md) for complete checks.
