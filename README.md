# michaelhv.no

Personal site of Michael Herland Valen. Hand-made HTML, CSS and a little JavaScript. No framework, no build step, no tracking.
The design is the "Sjokart" sea chart.

## Structure

```
site/                 the web root, deployed as is to GitHub Pages
  index.html          the page
  404.html            "off the chart" page, uses absolute paths
  style.css           all CSS, light and dark tokens, print styles
  theme.js            sets the saved theme before first paint, nothing else
  main.js             theme toggle, weather, clock, herring, jump menu
  fonts/              self-hosted woff2 (latin and latin-ext) and the OFL licences
  images/             portrait, Fernly screenshots, Nott, og.jpg
  CNAME               custom domain, do not change
scripts/
  check_site.py       static checks, run by CI
  update_latest.py    refreshes the "latest release" labels
  test_*.py           unit tests for both scripts
tools/og/og.html      source of site/images/og.jpg
.github/workflows/    CI and deploy
```

The CSP is a meta tag in the head of each page. It allows only the site itself and `api.open-meteo.com`.
That means no inline styles (`style=""`), no inline scripts and no inline event handlers. Put new CSS in `style.css`.

## Local preview

```
python3 -m http.server 8770 --directory site
```

Open http://127.0.0.1:8770/. The theme follows the system. The toggle in the nav saves the choice in `localStorage` under `theme`.

## Checks

```
python3 scripts/check_site.py
python3 -m unittest discover scripts
```

`check_site.py` fails on style attributes, inline scripts, `on*=` attributes, a changed CSP, broken in-page anchors,
images without alt, width or height, missing local files, forbidden strings, invalid JSON-LD, malformed latest markers and a missing CNAME.
CI runs both commands on every push and pull request.

## How "latest" updates

Each release label in `index.html` sits between two markers:

```
<!-- latest:OriginalMHV/Ward --><a ...>v0.6.2 · latest · 15 Oct 2026</a><!-- /latest -->
```

The deploy job runs `python3 scripts/update_latest.py site/index.html` before it uploads the site.
The script reads the latest release of each repository from the GitHub API and rewrites only the text between the markers.
If the API call or the data is bad, the committed label stays and the deploy goes on. The committed values are the fallback.
To add a project, copy a marker pair and change the repository name. `check_site.py` lists the repositories it expects.

The workflow also runs every Monday at 05:17 UTC so the labels follow new releases.

## Scheduled workflows stop after 60 days of silence

GitHub disables scheduled workflows in a repository after 60 days without repository activity.
When that happens, the labels stop updating and the Actions tab shows a banner.
To start them again, open the repository on GitHub, go to Actions, select the "Site" workflow and press "Enable workflow".
Any push to the default branch also counts as activity.

## Fonts and licences

Newsreader, Fira Sans Condensed and Fira Mono are licensed under the SIL Open Font License 1.1. The licence texts sit in `site/fonts/`.
Weather data comes from Open-Meteo.com and is credited on the page.
