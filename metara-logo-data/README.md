# metara-logo-data

Supporting data for METARA's SVG logo system. Sits alongside `metara-website` and `metara-contact-form` as its own top-level folder in the repo.

## Files

- **logo-registry.json** — the logo database: every known logo (hero emblem, nav mark, and the five venture marks pulled from `logo-metara-v3.ai`), tagged with its layer (0 = universal, 1 = category family, 2 = venture), status, and where it currently lives on the site. Update this whenever a logo is added, renamed, or its category is confirmed.
- **core-cosmic-egg.svg** — standalone copy of the hero emblem (also embedded inline in `metara-website/index.html`).
- **nav-metara-mark.svg** — standalone copy of the nav-bar mark (also embedded inline in `metara-website/index.html`).
- **rotation-frames.json** — the precomputed hidden-line-removal keyframes driving the Platonic solids' rotation in the hero emblem (24 steps per solid, synchronized). Also embedded inline in the site's `<script>`; kept here separately so it can be handed to a developer or reused elsewhere without digging through the HTML.

## Still open

- Category (Nonprofit / Commercial / Social Enterprise / Cooperative) hasn't been assigned yet for the five venture logos in the registry — flagged as `"category unassigned"` until confirmed.
- The Galaxy Logo reference image is logged as reference-only (AI-generated, watermarked) and isn't production-usable as-is.
