# EMI Guardian installers

These scripts install, update, or uninstall the KiCad 10 IPC plugin in the current user's data directory. Administrator privileges are not required.

## Before running an installer

1. Save every open board in KiCad and PCB Editor.
2. Fully close KiCad and PCB Editor.
3. Extract the complete ZIP. Do not run a script from inside the archive viewer.

## Windows

- Install or update: double-click `Install-or-Update.cmd`.
- Uninstall: double-click `Uninstall.cmd`.
- To select another KiCad version directory:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install-or-update.ps1 -KiCadVersion 10.0
```

## macOS

Double-click `install-or-update.command`. If macOS blocks first execution, run:

```bash
chmod +x install-or-update.command uninstall.command
./install-or-update.command
```

Use `uninstall.command` to remove the plugin.

## Linux

```bash
chmod +x install-or-update.sh uninstall.sh
./install-or-update.sh
```

Uninstall with:

```bash
./uninstall.sh
```

## Update behavior

The installer creates **no backup copy** of the previous plugin, including outside KiCad's `plugins` path. It first stages and checks the new payload in the operating-system temporary directory, then removes the old destination and installs the staged payload. If final placement fails, the incomplete destination is removed and the installer must be run again; automatic rollback is intentionally unavailable. Legacy `_emi-guardian-backups` and stale `emi-guardian.installing-*` directories are removed because KiCad may scan child directories as plugins. The KiCad-managed plugin Python environment is removed so KiCad recreates it on the next launch. Normal uninstall preserves persistent settings and exported reports.

## Launch

1. In the KiCad project manager, enable `Preferences > Preferences... > Plugins > Enable KiCad API`.
2. Confirm that a Python 3.9 or later interpreter is selected.
3. Restart KiCad and open a board in PCB Editor.
4. Select `Tools > External Plugins > Open EMI Guardian`.

If the action is missing, inspect the warning indicator in the lower-right corner of PCB Editor, the plugin directory, and Python environment creation errors.

## Install locations

- Windows: `%USERPROFILE%\Documents\KiCad\10.0\plugins\emi-guardian`
- macOS: `~/Documents/KiCad/10.0/plugins/emi-guardian`
- Linux: `${XDG_DATA_HOME:-~/.local/share}/KiCad/10.0/plugins/emi-guardian`

## Caution

The scripts only modify the current user's KiCad 10 data area. Use `--force` or `-Force` only when KiCad cannot be closed and every board has been saved. Updating while a plugin process is active can leave the running process inconsistent with the installed files.
