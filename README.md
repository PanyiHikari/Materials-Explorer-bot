# Materials Project Bot

A [NoneBot2](https://github.com/nonebot/nonebot2) plugin that connects to the [Materials Project](https://materialsproject.org/) API, allowing users to query crystal structures, search for materials, retrieve CIF files, and render crystal structure images via [VESTA](https://jp-minerals.org/vesta/) in QQ group chats.

---

## Features

- **Material lookup**: Retrieve symmetrized CIF files using a `material_id` (e.g., `mp-162`)
- **Structure rendering**: Render crystal structures via VESTA, either in the default view or projected along a specified crystal plane
- **Material search**: Automatically match one of three search modes — "only elements", "at least elements", or "chemical formula"
- **Paged browsing**: Search results are displayed 10 per page, with `nextp` / `lastp` for pagination
- **Index reference**: Reference a search result by index to fetch its CIF or rendered image
- **Cooldown**: Per-group cooldown timers to prevent abuse
- **Admin commands**: Per-group enable/disable toggle and cooldown reset

---

## Installation

### 1. Install NoneBot2 and the adapter

If you don't have a NoneBot2 project yet, follow the [official guide](https://nonebot.dev/docs/quick-start) to create one:

```bash
pip install nonebot2 nonebot-adapter-onebot
```

### 2. Install plugin dependencies

```bash
pip install mp-api pymatgen
```

### 3. Install VESTA

Download and install the version for your OS from the [official VESTA website](https://jp-minerals.org/vesta/en/download.html).

> **Important notes**
> - **Windows / macOS**: Precompiled binaries are available. Just install and go.
> - **Linux**: There is **no** official Linux binary. To run on a Linux server, use [Wine](https://www.winehq.org/) to run the Windows version, together with `Xvfb` for a virtual display.
> - VESTA is a GUI program and requires an available display environment (a Windows/macOS desktop, or Linux with Xvfb).

### 4. Install the plugin

Place the `materials_project` directory inside your NoneBot2 project's `plugins` directory:

```
your_bot_project/
├── plugins/
│   └── materials_project/
│       ├── __init__.py
│       ├── config.py
│       ├── mp_api.py
│       ├── render_vesta.py
│       ├── search.py
│       ├── cooldown.py
│       └── admin.py
├── .env
└── pyproject.toml
```

Then make sure the plugin is loaded in `pyproject.toml`:

```toml
[tool.nonebot]
plugins = ["materials_project"]
```

---

## Configuration

Add the following to your project's `.env` file:

```env
# Materials Project API Key (required)
# Apply for one at https://materialsproject.org/api
MP_API_KEY=your_api_key_here

# Path to the VESTA executable (required)
# Windows example: C:/Program Files/VESTA/VESTA.exe
# macOS example:   /Applications/VESTA/VESTA.app/Contents/MacOS/VESTA
# Linux example:   /usr/local/bin/VESTA
VESTA_EXEC=C:/Program Files/VESTA/VESTA.exe

# Image generation timeout in seconds (optional, default 30)
IMAGE_TIMEOUT=30

# Search results per page (optional, default 10)
SEARCH_PAGE_SIZE=10
```

These fields are automatically mapped to the `Config` model in `config.py` (NoneBot2 converts environment variable names to lowercase field names).

---

## Usage

All commands respond **only when the bot is @-mentioned** (except `nextp` / `lastp`).

### Basic commands

| Command | Description |
|---|---|
| `/mp <material_id>` | Fetch the symmetrized CIF file for the given material |
| `/mp.prev <material_id>` | Render the crystal structure in the default view |
| `/mp.prev <material_id> <view>` | Render projected along the given crystal plane (e.g., `011`, `111`) |
| `/mp.help` | Show the command index |

### Search and reference

| Command | Description |
|---|---|
| `/mp.search <query>` | Search materials, 10 results per page |
| `nextp` / `lastp` | Page navigation (no @, no `/`, no cooldown) |
| `/mp.res <index>` | Fetch the CIF of the search result at the given index |
| `/mp.res.prev <index>` | Render the default view of the search result at the given index |
| `/mp.res.prev <index> <view>` | Render the projection of the search result at the given index |
| `/mp.res.CLR` | Clear the current group's search results |

**Automatic search mode matching:**

| Input example | Mode | Description |
|---|---|---|
| `Si-O` | Only elements | Contains only Si and O |
| `Li-Fe-P-O` | Only elements | Contains only Li, Fe, P, O |
| `Si,O` | At least elements | Contains at least Si and O |
| `Fe,Co,Ni` | At least elements | Contains at least Fe, Co, Ni |
| `Fe2O3` | Formula | Exact chemical formula match |

### Admin commands (not listed in `/mp.help`)

| Command | Description |
|---|---|
| `/mp.SWT` | Toggle the plugin's enabled/disabled state for the current group (enabled by default) |
| `/mp.CD` | Reset all cooldown timers for the current group |

### Cooldown mechanism

- `/mp` and `/mp.prev` **share** one cooldown timer, duration **1 minutes**
- `/mp.search` has its own timer, duration **1 minutes**
- Cooldowns are **tracked separately per group**
- Pagination commands `nextp` / `lastp` have **no cooldown**

---

## Project structure

```
materials_project/
├── __init__.py        # Plugin entry, event handler registration, command handling
├── config.py          # Configuration model (loaded from .env)
├── mp_api.py          # Materials Project API wrapper
├── render_vesta.py    # VESTA rendering and image export
├── search.py          # Search result cache and pagination
├── cooldown.py        # Per-group cooldown management
└── admin.py           # Per-group enabled/disabled state management
```

### Module responsibilities

| Module | Responsibility |
|---|---|
| `mp_api.py` | Wraps `MPRester`; provides async interfaces for fetching structures, generating CIFs, and searching materials |
| `render_vesta.py` | Invokes the VESTA command line to render CIF and export PNG; supports default view and plane projection |
| `search.py` | Maintains per-group search caches and handles page formatting |
| `cooldown.py` | Maintains the two kinds of cooldown timers per group |
| `admin.py` | Maintains the enabled state per group |

---

## About VESTA rendering

### Command-line invocation

The plugin invokes VESTA with the following command-line arguments:

```bash
VESTA -open structure.cif -export_img output.png -close
```

When a crystal plane is specified, rotation parameters are appended:

```bash
VESTA -open structure.cif -rotate_x 30 -rotate_y 45 -export_img output.png -close
```

### Known limitations

- VESTA's `-export_img` argument only exports the image; it **does not** cause the program to exit. The plugin therefore **actively terminates the VESTA process** once the PNG is detected.
- VESTA's command line only exposes `-rotate_x/y/z` Euler angles and **cannot directly specify the `[hkl]` normal direction**. The plugin's plane projection uses a heuristic approximation; precise alignment would require a preset `.vesta` template file (not yet implemented).
- Headless Linux servers require `Xvfb`:

  ```bash
  xvfb-run -a /path/to/VESTA -open structure.cif -export_img output.png -close
  ```

  Alternatively, prepend `["xvfb-run", "-a"]` to the `Popen` arguments in `render_vesta.py`.

---

## Troubleshooting

<details>
<summary><b>Plugin fails to load with <code>No module named 'mp_api'</code></b></summary>

The Materials Project SDK is not installed. Inside your virtual environment, run:

```bash
pip install mp-api pymatgen
```
</details>

<details>
<summary><b>Rendering fails with <code>VESTA executable not found</code></b></summary>

Check that `VESTA_EXEC` in `.env` is a correct **absolute path**, or make sure VESTA is in your system `PATH`.
</details>

<details>
<summary><b>Rendering reports <code>VESTA process terminated on timeout</code>, but the image was generated</b></summary>

This is expected. VESTA does not exit automatically after exporting an image; the plugin terminates the process once the PNG is detected. The warning can be ignored.
</details>

<details>
<summary><b>Search returns no results</b></summary>

1. Make sure your `MP_API_KEY` is valid.
2. Try a broader query, e.g., change `Si-O` to `Si,O`.
3. Check the backend logs for the search parameters and result count to determine whether it's an API semantics issue or genuinely no results.
</details>

<details>
<summary><b>Field error: <code>invalid fields requested: ['is_experimental']</code></b></summary>

The Materials Project API has removed the `is_experimental` field. Use `theoretical` instead (`theoretical=False` indicates an experimental structure). Ensure field names in `mp_api.py` are correct.
</details>

<details>
<summary><b>No output when commands are on cooldown</b></summary>

Check that `_check_enabled_and_cooldown` takes a `bot` parameter and uses `bot.send(event, ...)` rather than `event.bot.send(...)`. A `GroupMessageEvent` has no `.bot` attribute.
</details>

---

## Contributing

Issues and PRs are welcome. If you implement any of the following, contributions are especially appreciated:

- [ ] Precise `[hkl]` projection (via a preset `.vesta` template)
- [ ] Automatic Linux + Xvfb adaptation
- [ ] Support for additional rendering backends (e.g., ASE, py3Dmol)
- [ ] Filtering by space group, band gap, stability, etc.

---

## License

This project is released under the [MIT License](LICENSE).

---

## Acknowledgements

- [Materials Project](https://materialsproject.org/) — for providing an open materials database and API
- [NoneBot2](https://github.com/nonebot/nonebot2) — an excellent asynchronous Python bot framework
- [VESTA](https://jp-minerals.org/vesta/) — a powerful crystal structure visualization tool
- [pymatgen](https://pymatgen.org/) — a Python library for materials science

---

## Disclaimer

This plugin is intended for learning and research purposes only. When using the Materials Project API, please comply with their [terms of use](https://materialsproject.org/terms-of-use).
