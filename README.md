# Passpartout demo: MCP server

A working demo that lets an AI assistant (Claude, ChatGPT and others) find and "book" private, moment-triggered hotel offers within a short car or train ride of Milan or Turin.

**Demo only:** the five hotels are fictional, availability is simulated, and bookings and payment links are fake.

## What the AI can do (tools)

| Tool | What it does |
| --- | --- |
| `current_moments` | What's happening now (rain in Milan, first snow, empty midweek) |
| `find_getaways` | Offers within X minutes by car or train, for given dates, budget and vibe |
| `get_offer` | Full details of one offer |
| `check_availability` | Is it open for these dates? |
| `book_offer` | Creates a demo booking and a fake payment link |

**Public vs private:** without a member code, prices show the public rate plus the added value. With the demo member code `DEMO-MEMBER`, the private discounted rate appears.

## Files

- `server.py`: the MCP server (the tools above)
- `data.py`: sample hotels, offers and moments. **Edit this to change the demo.**
- `requirements.txt`, `Procfile`: for hosting

## 1. Run it on your computer

Needs Python 3.10+.

```
pip install -r requirements.txt
python server.py
```

The server runs at `http://127.0.0.1:8000/mcp`.

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
4. Your connector URL is `https://<that domain>/mcp`.

The demo has no login, so anyone with the URL can use it. That's fine for fake data; a real version needs proper sign-in.

## Try these prompts

- "What's a good getaway from Milan this weekend? I'd rather take the train."
- "My Passpartout member code is DEMO-MEMBER. Any wine or food getaways from Turin midweek, under €300?"
- "Book the Lake Garda spa offer for 2 nights from Sunday, for Colleen, colleen@example.com."

## Next steps with Claude Code

Good things to ask for, one at a time:

1. "Replace the simulated moments with a real weather forecast from Open-Meteo."
2. "Store hotels and offers in a database instead of data.py, with a simple page to add offers."
3. "Add a members list so `member_code` is checked properly."
4. "Add a page showing all demo bookings."

Before real guests use it, an engineer should add secure sign-in, GDPR-compliant storage of guest data, real payments and hotel system connections.
