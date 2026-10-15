<img align="right" src="https://visitor-badge.laobi.icu/badge?page_id=platima.wa_surf_Data" height="20" />

# WA Surf Data 🏄

This project reads the WA Department of Transport wave buoy charts for all nine WA stations every half hour and converts them to numbers. It then publishes a small surf page plus JSON on GitHub Pages.

The stations are Geraldton, Jurien Bay, Cottesloe, Rottnest Island, Mandurah, Cape Naturaliste, Albany, Bremer Bay and Esperance.

## Choosing a station

The page shows the station nearest the visitor, worked out from their IP address. For a more accurate result, the visitor can press "Use precise location" to share their device location instead.

Visitors outside WA see Cape Naturaliste, with a banner explaining why. Any station can be picked from the list, and the choice is remembered in the browser. A link such as `.../#rottnest-island` opens a specific station.

## Files

- `index.html`: the page
- `stations.json`: the station list, with each station's latest swell
- `<station>/raw.json`: current values and a 4-day hourly series
- `<station>/history.json`: hourly records kept for 60 days
- `healthz.json`: status of the last update

Values are read from chart pixels, not from a data feed. Accuracy is about one chart pixel, which is roughly ±0.05 m and ±0.12 s.

## Setup

1. Push this repository to GitHub as a public repository, on the `main` branch.
2. Go to Settings > Pages > Build and deployment, and set Source to **GitHub Actions**.
3. Go to the Actions tab, open **Update wave data**, and click **Run workflow**.

The site will be at https://platima.github.io/WA_Surf_Data.

## Running locally

```
pip install -r requirements.txt
python capenat_waves.py
```

This keeps `site/` updated and serves it on port 8080.

## Documentation

The docstring at the top of `capenat_waves.py` is the reference. It covers the method, calibration, accuracy, verification, failure handling, limits, the location logic and the GitHub Pages caveats.

Source charts: [DoT wave data](https://www.transport.wa.gov.au/marine/charts-warnings-current-conditions/coastal-data-charts/wave-data)
