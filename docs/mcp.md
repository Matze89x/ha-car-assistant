# MCP access (Claude Code)

🇬🇧 English · [🇩🇪 Deutsch](mcp.de.md)

With MCP access, **Claude Code** (or another MCP client) can look into your Car Assistant and - if you allow it - correct records. It is meant for finding and fixing mistakes together with Claude: *"why is the consumption of the diesel car so low?"*, *"fix the date of this service entry"*.

It is **off by default** and always under your control.

## What you need first

MCP can be switched on only when all three things are in place (the settings card tells you which one is missing):

1. **A user** exists (Settings → User).
2. **Your external https address** is saved (Settings → System → address of this app).
3. **The port of the app is open** (Home Assistant: the app's *Network* tab).

If one of them goes away later (address removed, port closed), MCP is off again at once.

## Switch it on

1. Open *Settings → System → MCP access*.
2. Choose the **level**:
   - **Off** - nothing works (the default; the endpoint does not even answer).
   - **Read** - the client can look at everything described below, but change nothing.
   - **Read and write** - the client may also add, change and delete records of the cars.
3. Create the **access key** (one key for everything). The level above decides what it may do - there is no second setting.
4. Copy the key **now** - it is shown only once and only a hash is stored. If it is lost or leaked, press **Renew key**: a new one is made and the old one stops working at once (then change it in Claude as well).

## Connect Claude Code

Claude Code adds the server with one command (the key page shows it with your address and key filled in):

```bash
claude mcp add --transport http car-assistant https://car.example.com/mcp --header "Authorization: Bearer cam_..."
```

Then ask Claude Code something like *"list my vehicles"*. The address is your external https address plus `/mcp`.

## Use it from everywhere: a connector in your Claude account

A *custom connector* belongs to your Claude account, so it is there in the web chat, the desktop app and on your phone - and you can let Claude complete your data from any of them.

1. In Claude open **Customize → Connectors → Add → Add custom connector** (German: *Benutzerdefinierten Konnektor hinzufügen*; Team accounts: Organization settings → Connectors).
2. Enter the address `https://your-address/mcp` - **without a port** such as `:8443` (Claude does not connect to those), and the server must be reachable from the internet.
3. Easiest: use the address **with the key** from the key page (`https://your-address/mcp/cam_...`) and leave everything else empty. Safer, if your dialog has *Request headers*: use the plain address and add the header `Authorization` with the value `Bearer cam_...`. There is no OAuth: the app uses the fixed key.
4. Save, then switch the connector on in a chat. Ask for example: *"Look at my vehicles and tell me what data is missing"* - Claude calls `data_gaps` and asks you for the values.

Request headers cannot be changed later: for a new key remove the connector and add it again.

## What the client can do

| Tool | Needs | What it does |
|---|---|---|
| `app_info` | read | version, stage, size, the kinds of records |
| `list_vehicles` | read | all vehicles with slug, name, fuel type, odometer |
| `get_vehicle` | read | all data of one vehicle, live values, what needs attention, record counts |
| `list_entries` | read | the records of one kind (service, fuel, appointments, tasks, tyres, modifications, parts, trips, counters), newest first, paged |
| `get_costs` | read | costs per day / week / month and every priced entry |
| `data_gaps` | read | what is still missing: empty vehicle fields, refuels without odometer / amount / price, service without cost or odometer, tasks never done, trips without places |
| `get_logs` | read | the newest plugin log lines - useful when something does not work |
| `list_plugins` | read | plugins and integrations of a vehicle: name, version, on / off, set up, settings (secrets hidden) |
| `list_documents` | read | the documents of a vehicle (title, category, size - not the files) |
| `get_charging` | read | charging sessions of an electric car |
| `get_tyres` | read | recommended tyre pressures and tyre sets |
| `get_settings` | read | language, units, currency and how many vehicles / plugins / integrations exist |
| `add_entry` | write | add a record (wrong values are refused with the reason) |
| `update_entry` | write | change only the given fields of a record |
| `delete_entry` | write | delete a record (cannot be undone) |

Values are in base units (km, litres or kWh, bar, °C, money as a plain number), independent of the units you chose for display.

## What it can never do

- change settings, users, passwords, keys, plugins, sources or the address of the app;
- show secrets (passwords, tokens, access keys, the external address);
- be used from the Home Assistant panel, from another website (the `Origin` is checked) or without a key.

## Security

- **https only**, and only while all requirements are met.
- There is **one key**, stored only as a **hash**; renewing or deleting it cuts every client off at once.
- Wrong keys are slowed down and the address is blocked for a while after too many attempts; every key is limited to 120 calls per minute.
- **Everything a key does is logged** (the latest calls are on the settings card).
- Write access changes real data. **Make a backup first** (Settings → System) and prefer *Read* unless you want Claude to correct something.
- Treat a key like a password. Do not put it into a repository, a chat or a screenshot.

## When it does not work

| Sign | Likely reason |
|---|---|
| `404` | MCP is off, or a requirement is missing (see the card), or you used the Home Assistant panel address |
| `401` | wrong or deleted key |
| `403` | the request came from a website (an `Origin` that is not your address) |
| `429` | too many wrong keys from that address (wait 15 minutes), or more than 120 calls a minute |
| writing is refused | the key or the server level is *Read* |
