# Passpartout demo: MCP server + REST API

A working demo that lets an AI assistant (Claude, ChatGPT and others) find and "book" private, moment-triggered hotel offers within a short car or train ride of Milan or Turin.

It also exposes a REST API with interactive docs, so the same offers can be browsed from a web app, mobile app or any HTTP client.

**Demo only:** the five hotels are fictional, availability is simulated, and bookings and payment links are fake. Weather forecasts are real, pulled from Open-Meteo.

## What the AI can do (MCP tools)

| Tool | What it does |
| --- | --- |
| `current_moments` | Live weather forecast and moments triggered by it (rain, snow, sun on coast) |
| `find_getaways` | Offers within X minutes by car or train, for given dates, budget and vibe |
| `get_offer` | Full details of one offer |
| `check_availability` | Is it open for these dates? |
| `book_offer` | Creates a demo booking and a fake payment link |

## REST API endpoints

| Method | Endpoint | What it does |
| --- | --- | --- |
| GET | `/api/moments` | Live weather and triggered moments for a city |
| GET | `/api/offers` | Search offers (city, dates, budget, vibe, travel mode) |
| GET | `/api/offers/{id}` | Full details of one offer |
| GET | `/api/offers/{id}/availability` | Check availability for dates |
| POST | `/api/bookings` | Book an offer (demo) |

Interactive API docs are at `/docs` (Swagger UI) and `/redoc` (ReDoc).

**Public vs private:** without a member code, prices show the public rate plus the added value. With the demo member code `DEMO-MEMBER`, the private discounted rate appears.

## Files

- `server.py`: the MCP server and REST API (FastAPI)
- `data.py`: sample hotels, offers and weather trigger rules. **Edit this to change the demo.**
- `weather.py`: live 7-day forecasts from Open-Meteo (free, no API key). Triggers offers based on actual weather conditions.
- `requirements.txt`, `Procfile`: for hosting

## 1. Run it on your computer

Needs Python 3.10+.

```
pip install -r requirements.txt
python server.py
```

The server runs at `http://127.0.0.1:8000`:
- API docs: `http://127.0.0.1:8000/docs`
- MCP endpoint: `http://127.0.0.1:8000/mcp`

## 2. Use it in Claude

**Option A: Claude Desktop (local, easiest).** Add this to Claude Desktop's MCP config file (`claude_desktop_config.json`), with the real path to the folder, then restart Claude Desktop:

```json
{
  "mcpServers": {
    "passpartout": {
      "command": "python",
      "args": ["/full/path/to/passpartout-mcp/server.py", "--stdio"]
    }
  }
}
```

**Option B: online, so Sara and others can use it.** Deploy it (step 3), then add the public URL (ending in `/mcp`) as a custom connector in Claude. Check Claude's help center for the current steps.

## 3. Put it online (Railway example)

1. Put this folder in a GitHub repository.
2. In Railway, create a new project from that repository. It reads the `Procfile` automatically.
3. Generate a public domain in Railway, then add an environment variable `PUBLIC_HOST` set to that domain (e.g. `passpartout-demo.up.railway.app`).
4. Your MCP connector URL is `https://<that domain>/mcp`.
5. Your API docs are at `https://<that domain>/docs`.

The demo has no login, so anyone with the URL can use it. That's fine for fake data; a real version needs proper sign-in.

## Try these prompts

- "What's a good getaway from Milan this weekend? I'd rather take the train."
- "My Passpartout member code is DEMO-MEMBER. Any wine or food getaways from Turin midweek, under €300?"
- "Book the Lake Garda spa offer for 2 nights from Sunday, for Colleen, colleen@example.com."

## Try the API

```
curl http://localhost:8000/api/moments?city=Milan
curl http://localhost:8000/api/offers?from_city=Turin&vibe=wine&member_code=DEMO-MEMBER
curl -X POST http://localhost:8000/api/bookings \
  -H "Content-Type: application/json" \
  -d '{"offer_id": "o-como-rain", "check_in": "2026-12-05", "nights": 2, "guest_name": "Test", "guest_email": "test@example.com"}'
```

## Next steps with Claude Code

Good things to ask for, one at a time:

1. "Store hotels and offers in a database instead of data.py, with a simple page to add offers."
3. "Add a members list so `member_code` is checked properly."
4. "Add a page showing all demo bookings."

Before real guests use it, an engineer should add secure sign-in, GDPR-compliant storage of guest data, real payments and hotel system connections.
