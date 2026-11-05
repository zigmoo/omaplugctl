# Install from a repository or X post

Open OmaPlugCtl > Install. Type keywords to search the saved Omarchy marketplace by name, identifier, author, category, tags and description. The catalog loads when the tab opens; a cache older than one day refreshes once in the background. Refresh also works manually.

Hover a result for its full description, author, latest commit date and subject, commit author and hash, version, license, category, tags, stars and verification coverage where available. Latest commit metadata comes from the public GitHub API after a 400 ms hover, separately from the catalog, and is cached for an hour. GitHub rate limits and connection failures show Unavailable rather than inventing a date. Click a result name, Source, or Visit repository to open its GitHub page. Remote text renders literally.

Paste an HTTPS GitHub repository URL or X/Twitter post URL into the same field. Click Evaluate URL or press Enter. GitHub file and branch links resolve to the repository default branch. X discovery uses the official public syndication endpoint; it examines post text, expanded links, accessible quoted/parent content and explicitly linked thread posts, up to eight posts and five repositories. It cannot enumerate every reply or access protected/deleted posts. Paste the specific post containing the repository link, or GitHub directly, when discovery cannot find it.

Evaluation retrieves a checkout outside the active plugin directory, pins its commit, bounds the complete tree to 10,000 regular files and 128 MiB, rejects symlinks/submodules and unresolved LFS payloads, scans all blobs with local ClamAV, then runs omarchy-plugin-validate. Git hooks, user Git configuration and transport redirects are disabled for source retrieval. Evaluation executes no plugin code and uploads no plugin content. Local validation is not marketplace verification or a guarantee that code is safe.

Only passing results offer Install. Install revalidates and rescans the pinned checkout, refuses changed files or an existing destination, moves that exact checkout into the plugin directory, asks Omarchy to rescan, and confirms the plugin is installed disabled. Enable is a separate explicit action confirmed through native plugin state. No remote installer scripts run. Unsupported layouts stay blocked.

Evaluation stages expire after one day and are bounded to 16 retained stages. If a stage expires or disappears, evaluate again. Existing installed plugins remain intact. Failed post-install confirmation reports the failure so the Plugins tab can be inspected; it does not silently remove an installed checkout.

The PHP controller exposes source-check URL, source-install TOKEN, source-enable TOKEN, source-open URL and source-details URL. Source metadata remains optional runtime cache, not catalog verification authority. Test adapters use isolated home/state directories and do not install third-party plugins into the operator desktop.
