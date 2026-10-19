# How updates work

[Back to OmaPlugCtl](../README.md)

An update click authorizes a local scan and update of the running plugin checkout. Progress and the result stay in the menu; a terminal or agent review is not part of the update flow.

## Checking versus installing

**Check updates** fetches each installed source repository and caches its status, latest change date and recent commit subjects. It does not check out the fetched code. Opening the menu, refreshing the list and hovering a row read local state and cached results rather than fetching repositories.

A plugin needs its own Git checkout to be updated here. Shared built-in plugins remain managed by Omarchy’s system updater. A plugin installed through a symlink is resolved to the underlying repository.

## An ordinary update

The background worker locks the repository, fetches the current branch’s configured `origin` ref, and pins the exact fetched commit. With scanning enabled, it checks that commit before changing the checkout.

The worker rechecks repository identity, HEAD and local changes around these steps. It fast-forwards to the pinned commit, then verifies the resulting HEAD and working tree. Git hooks are disabled for the checkout-changing operation. Concurrent update workers cannot modify the same repository at once.

The worker survives a shell rescan and updates to OmaPlugCtl itself. After an update it requests a plugin rescan. Menu status polling reads local operation records; it does not repeatedly fetch upstream.

## When upstream history changes

A repository can appear divergent even when its installed changes already exist upstream under different commit IDs. OmaPlugCtl checks this case before asking the user to reconcile it.

Every installed-only commit must have a matching whitespace-preserving, verbatim patch ID upstream. Local-only merge commits, empty commits and incomplete patch coverage are rejected. Matching patch IDs permit adopting the new upstream history; unmatched local work stops the update.

Before a qualifying reconciliation, the updater creates and verifies a backup branch:

```text
backup/omaplugctl/<timestamp>-<old-commit>
```

It then uses a non-forced checkout to move the existing branch to the pinned upstream commit. Ignored files are protected from overwrite. It never stashes, rebases, creates a merge commit or hard-resets local work.

The backup keeps the old version addressable in Git. Backup branches are retained rather than automatically deleted.

## Local malware checks

ClamAV scanning defaults to enabled. The scanner reads every tracked blob at the pinned commit into an inert archive; it does not execute the plugin. Files marked `export-ignore` are included. Symlinks are scanned as their target text without following them.

FreshClam refreshes signatures when needed, at most once per day, and verifies them using its native signature checking. Plugin contents are not uploaded. Network access consists of Git fetches and ClamAV signature downloads.

Complete coverage is required. Updates stop for:

- A detection, encrypted archive, scan limit or scanner error.
- A failed signature refresh.
- Submodule contents or Git LFS payloads that cannot be fully scanned.
- Snapshots exceeding 10,000 tracked files or 128 MiB of tracked blob data.

A clean scan means **no threats detected**, not a security audit or proof of safety. The scanner also does not examine dependencies or downloads a plugin might obtain when it runs.

## Scanner installation and storage

Install the distribution’s `clamav` package to provide `clamscan` and `freshclam`. OmaPlugCtl maintains its own signature database; a separate ClamAV daemon is not required by this updater.

A user-local runtime is also supported at `$XDG_DATA_HOME/omaplugctl/scanner`, defaulting to `~/.local/share/omaplugctl/scanner`, with this layout:

```text
scanner/
  usr/bin/clamscan
  usr/bin/freshclam
  usr/lib/
  etc/clamav/certs/
```

Provide matching libraries and certificates from trusted packages. Installing this runtime is a separate setup step; OmaPlugCtl does not download or install the scanner for you.

Update cache, author cache, operation records, signatures and scanner logs live under `$XDG_STATE_HOME/omarchy/omaplugctl`, defaulting to `~/.local/state/omarchy/omaplugctl`. They are not stored in plugin source repositories.

## Understanding a stopped update

| Message or condition | Meaning and next step |
| --- | --- |
| Local changes | The checkout has edits or untracked files. Inspect and preserve them before trying again. |
| Local commits | The installed branch has commits ahead of upstream. Inspect that history before changing it. |
| Update needs reconciliation | Histories diverged. A click checks for equivalent rewritten history; unmatched local commits stop the update. |
| No update repository | OmaPlugCtl could not resolve an independent Git source. Use that plugin’s installation instructions. |
| Updated with Omarchy | Use Omarchy’s system updater for this built-in plugin. |
| Detached HEAD or no origin tracking | The checkout needs an ordinary branch tracking its intended `origin` branch. Inspect its Git configuration first. |
| ClamAV unavailable or signatures need downloading | Install the scanner and allow signature downloads. A failed refresh leaves the update unapplied. |
| Detection or incomplete scan | The update is blocked. Inspect the cause before deciding what to do. |

The Config scan toggle is an explicit preference. Disabling it skips future scans; it does not resolve local edits, divergent commits or other Git checks.
