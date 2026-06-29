# World Clock

This folder contains a simple static world clock web app.

## Run locally

Open `index.html` directly in a browser, or use a simple local server:

```bash
cd docs/world-clock
python -m http.server 8000
# then visit http://localhost:8000
```

## Features

- Live clock updates every second
- Multiple time zones displayed at once
- 12-hour / 24-hour toggle
- Add/remove time zones from the UI
- Uses built-in browser internationalization APIs (no paid external service)
