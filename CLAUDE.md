# SDG Progress Tracker: India

India's SDG indicator progress, from data held inline in the page. Single page, no build step, deployed on Netlify.

## Commands

```bash
python3 scripts/check.py        # static checks, run by CI
python3 -m http.server 8000     # then open http://localhost:8000
```

Note that a local server does **not** send the `netlify.toml` headers, so the
Content-Security-Policy you see locally is only the `<meta http-equiv>` one.

## The CSP is declared twice, and that is the thing to get right

`index.html` carries a `<meta http-equiv="Content-Security-Policy">` and
`netlify.toml` sets the same header. A browser enforces the **intersection**, so
whichever is tighter governs and the looser one is invisible.

They had drifted. The header was carried over verbatim when this site was split
out of the Experiments repository, which hosts many tools, so it allowed ten
origins this site never touches: unpkg, cdnjs, openlibrary.org, the three
open-meteo endpoints, api.dhsprogram.com, tessdata.projectnaptha.com,
basemaps.cartocdn.com and licensebuttons.net.

Nothing broke, and nothing would have. The meta policy was a strict subset of
the header for every directive, so the intersection already equalled the meta
policy. The hazard ran the other way: delete the meta tag believing the header
covered it, and the policy silently widens by ten origins.

The header is now the meta policy verbatim, plus `object-src`, `worker-src` and
`media-src`, which a meta tag has no reason to carry. `scripts/check.py` fails
if the two drift apart again.

## Watch out for

- **A CSP that is too tight fails silently.** The script does not load, the
  chart does not draw, and only the browser console says why. If you add a CDN,
  add it to **both** policies, and remember that `<iconify-icon>` fetches its
  icon data at runtime from `api.iconify.design`, with `api.simplesvg.com` and
  `api.unisvg.com` as fallbacks, so those belong in `connect-src` rather than
  `script-src`.
- **Inline event handlers work here only because `script-src` carries
  `'unsafe-inline'`.** Tighten that to a nonce or a hash and every one of them
  stops firing with nothing on the page to show it. A check pairs the two.
- **Google Fonts spans two directives.** The stylesheet comes from
  `fonts.googleapis.com` under `style-src`, the font files from
  `fonts.gstatic.com` under `font-src`. Putting both in one is a common way to
  end up with a page in a fallback typeface.

## Data

The figures are inline in `index.html`. There is no API call, so nothing rots on its own and nothing refreshes on its own either.

The page derives its most recent year from the clock rather than pinning one, so
it advances on its own. A check fails if a literal year is introduced, because
that is how a live explorer becomes quietly stale a year later without anything
erroring.

## Testing

`.github/workflows/ci.yml` runs `scripts/check.py` on every push and pull
request. Before 2026-09-22 there was no CI in this repository at all.
