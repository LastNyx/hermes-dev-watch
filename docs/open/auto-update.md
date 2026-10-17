# Design: self-update from GitHub Releases (0.3.6)

Status: grilled and built 2026-10-17 as 0.3.6. Measured on Windows: a local 0.3.6 build updated itself to a local
0.3.7 build from a fake release server (download, digest, swap, restart, `.old` deleted). The restart sets
`PYINSTALLER_RESET_ENVIRONMENT=1` so the new one-file binary unpacks its own `_MEI` folder. Linux binary not run.

## The problem

Every release means opening GitHub, downloading the binary and replacing the old one by hand, on two machines. The
method follows hermes-mobile-client's updater (latest GitHub release, asset by name, SHA-256 against the digest
GitHub reports), not its code.

## Decisions

1. **When.** One check at startup and a "Check for updates" button. `check_updates` in the config (default on) turns
   off the startup check only; the button always works. One unauthenticated `api.github.com` call per check
   (`/repos/LastNyx/hermes-dev-watch/releases/latest`; the limit is 60 an hour).
2. **What the user sees.** When a newer release exists, a banner with the version tag only: `v0.3.6 available - Update`.
   No release notes or CHANGELOG in the app. Nothing is downloaded or replaced until the user clicks Update.
3. **Repo link.** A GitHub logo in the header opens https://github.com/LastNyx/hermes-dev-watch in the default browser.
4. **Platforms.** Windows `.exe` and Linux binary, one code path. The asset is picked by the existing release names
   (`hermes-dev-watch-windows-x64.exe`, `hermes-dev-watch-linux-x64`). The Linux binary needs its own real-binary
   check before release.
5. **Trust.** The download's SHA-256 must equal the asset's `digest` (`sha256:...`) from the same API response; on a
   mismatch the file is deleted and nothing is replaced. Trust is the same as a manual download from GitHub. No code
   signing and no SHA256SUMS file.
6. **Swap.** Download to `<exe>.new` in the binary's own folder (same volume, so renames are atomic). Rename the running
   binary to `<exe>.old` (Windows allows renaming a running exe; it does not allow overwriting it), rename `.new` to the
   binary's name, `chmod +x` on Linux, start it with the same arguments, and quit. On start, a binary deletes its own
   `.old` if one is there.
7. **Failure.** No automatic rollback. If the new version never starts, `.old` stays, and the user renames it back by
   hand (README says how). A failed download or digest check leaves the current binary untouched. An offline startup
   check fails silently; the button shows the error.
8. **Running from source** (`python run.py`, not a PyInstaller binary: `sys.frozen` unset): the updater never replaces
   files. When a newer release exists, the banner says `v0.3.6 available - running from source: git pull`.
9. **Version compare.** The tag `vX.Y.Z` against `__version__`, compared as integer tuples. Newer only, never a
   downgrade. A tag that doesn't parse is ignored.
10. **Code and release.** New `hermes_dev_watch/update.py` (stdlib `urllib`, `hashlib`, no new dependency), bridge
    methods `check_update()` / `apply_update()` / `open_repo()` in `app.py`, the banner and logo in `static/index.html`.
    Tests: a fake releases server on 127.0.0.1 (newer, same, older, bad tag, digest mismatch, missing asset, offline)
    and the swap on a throwaway file pair. Ship as 0.3.6 with a tag, then run each real binary once: 0.3.5 -> 0.3.6 can't
    be shown (0.3.5 has no updater), so the first real update is 0.3.6 -> 0.3.7.

## Not covered

- A hijacked GitHub release or account: the digest comes from the same place as the file.
- An antivirus quarantining the new `.exe`: the update looks failed and `.old` is the way back.
