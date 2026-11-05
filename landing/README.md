# Landing page

Static single-page site. No build step, no dependencies.

## Publish with GitHub Pages (workflow)

The workflow at `.github/workflows/pages.yml` publishes this directory.

1. Push the files.
2. Repository → **Settings → Pages**.
3. **Source: GitHub Actions**.
4. Run the workflow (it triggers on push to `main` when `landing/**` changes,
   or manually from the Actions tab).
5. The URL appears in the Pages settings and in the workflow summary.

## Edit

Everything is in `index.html`. The only external reference is the
`mailto:` address, which must be replaced before publishing.

## Rules for this page

- Do not remove a `soon` badge until the corresponding route is mounted on the
  deployed host **and** smoke-tested in production.
- Do not add uptime or SLA wording until a status page exists and has 90 days of
  measured data.
- Do not describe world assets as hosting, transcoding, or streaming. It is a
  registry: path/URL plus structured facts.
