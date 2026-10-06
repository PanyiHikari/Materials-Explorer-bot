[简体中文](README_ZH.md)

# Materials Project Bot

A QQ bot plugin based on [NoneBot2](https://github.com/nonebot/nonebot2) that integrates with the [Materials Project](https://materialsproject.org/) API to query crystal structures, search materials, obtain CIF files, and render crystal structure images via [VESTA](https://jp-minerals.org/vesta/) in group chats.

---

## Features

- **Material query**: Obtain symmetrized CIF files by `material_id` (e.g., `mp-162`)
- **Structure rendering**: Call VESTA to render the default view or a specified crystal plane projection image of a crystal structure
- **Material search**: Support automatic matching search by three modes: "only these elements", "at least these elements", and "chemical formula"
- **Paginated browsing**: Search results are displayed 10 per page, with `nextp` / `lastp` page turning
- **Index reference**: Directly reference the index in search results to obtain a CIF or rendered image
- **Cooldown mechanism**: Timed independently per group chat to prevent abuse
- **Admin commands**: Support group-level switches and cooldown reset

---

## Installation

### 1. Install NoneBot2 and the adapter

If you do not already have a NoneBot2 project, first refer to the [official documentation](https://nonebot.dev/docs/quick-start) to create one:

```bash
pip install nonebot2 nonebot-adapter-onebot
```

### 2. Install plugin dependencies

```bash
pip install mp-api pymatgen
```

### 3. Install VESTA

Download the version for your system from the [VESTA official website](https://jp-minerals.org/vesta/en/download.html) and install it.

> **Important**
> - **Windows / macOS**: Official precompiled builds are provided, and they can be used after installation.
> - **Linux**: The official website does **not** provide a Linux binary version. If you need to run it on a Linux server, use [Wine](https://www.winehq.org/) to run the Windows version, together with an `Xvfb` virtual display environment.
> - VESTA is a GUI program, and it requires a usable display environment at runtime (Windows/macOS desktop or Linux Xvfb).

### 4. Install the plugin

Place the `materials_project` directory into the `plugins` directory of your NoneBot2 project:

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

Then confirm in `pyproject.toml` that the plugin is loaded:

```toml
[tool.nonebot]
plugins = ["materials_project"]
```

---

## Configuration

Add the following configuration to the `.env` file in the project root directory:

```env
# Materials Project API Key (required)
# Apply at https://materialsproject.org/api
MP_API_KEY=your_api_key_here

# VESTA executable path (required)
# Windows example: C:/Program Files/VESTA/VESTA.exe
# macOS example: /Applications/VESTA/VESTA.app/Contents/MacOS/VESTA
# Linux example: /usr/local/bin/VESTA
VESTA_EXEC=C:/Program Files/VESTA/VESTA.exe

# Image generation timeout (seconds, optional, default 30)
IMAGE_TIMEOUT=30

# Search results per page (optional, default 10)
SEARCH_PAGE_SIZE=10
```

The configuration fields are automatically mapped to the `Config` model in `config.py` (NoneBot2 automatically converts environment variable names to lowercase field names).

---

## Usage

All commands respond **only when the bot is @-mentioned** (except `nextp` / `lastp`).

### Basic Commands

| Command | Description |
|---|---|
| `/mp <material_id>` | Get the symmetrized CIF file for the specified material |
| `/mp.prev <material_id>` | Render the crystal structure image in the default view |
| `/mp.prev <material_id> <view>` | Render a projection along the specified crystal plane (e.g., `011`, `111`) |
| `/mp.help` | Show the command index |

### Search and Reference

| Command | Description |
|---|---|
| `/mp.search <condition>` | Search materials, 10 per page |
| `nextp` / `lastp` | Page turning (no @, no `/`, no cooldown) |
| `/mp.res <index>` | Get the CIF for the specified index in the search results |
| `/mp.res.prev <index>` | Render the default view for the specified index in the search results |
| `/mp.res.prev <index> <view>` | Render a projection image for the specified index in the search results |
| `/mp.res.CLR` | Clear the search results for this group |

**Automatic search condition matching rules:**

| Input example | Matching mode | Description |
|---|---|---|
| `Si-O` | Only these elements | The material contains only Si and O |
| `Li-Fe-P-O` | Only these elements | The material contains only Li, Fe, P, and O |
| `Si,O` | At least these elements | The material contains at least Si and O |
| `Fe,Co,Ni` | At least these elements | The material contains at least Fe, Co, and Ni |
| `Fe2O3` | Chemical formula | Exact match by chemical formula |

### Admin Commands

| Command | Description |
|---|---|
| `/mp.SWT` | Toggle the plugin enabled/disabled state for this group (enabled by default) |
| `/mp.CD` | Reset all cooldown timers in this group to zero |

### Cooldown Mechanism

- `/mp` and `/mp.prev` **share** one cooldown timer, with a duration of **1 minute**
- `/mp.search` has a separate timer, with a duration of **1 minute**
- Cooldowns are **calculated independently per group chat**
- The page-turning commands `nextp` / `lastp` have **no cooldown**

---

## Project Structure

```
materials_project/
├── __init__.py        # Plugin entry, event responder registration and command handling
├── config.py          # Configuration model (read from .env)
├── mp_api.py          # Materials Project API wrapper
├── render_vesta.py    # VESTA rendering and image export
├── search.py          # Search result cache and pagination management
├── cooldown.py        # Per-group cooldown management
└── admin.py           # Group-level enable/disable state management
```

### Module Responsibilities

| Module | Responsibility |
|---|---|
| `mp_api.py` | Wraps `MPRester`, providing async interfaces for obtaining structures, generating CIFs, and searching materials |
| `render_vesta.py` | Calls VESTA command line to render CIFs and export PNGs, supporting default view and crystal plane projection |
| `search.py` | Maintains the search cache for each group chat and handles pagination formatting |
| `cooldown.py` | Maintains two types of cooldown timers for each group chat |
| `admin.py` | Maintains the enabled state for each group chat |

---

## About VESTA Rendering

### Command-line Invocation

The plugin calls VESTA with the following command-line arguments:

```bash
VESTA -open structure.cif -export_img output.png -close
```

When specifying a crystal plane projection, append rotation parameters:

```bash
VESTA -open structure.cif -rotate_x a -rotate_y b -export_img output.png -close
```

The rotation parameters `a` and `b` are calculated as follows:

```python
# In pymatgen, the row vectors of lattice.matrix are a, b, c
lat = np.array(structure.lattice.matrix)
# Reciprocal basis: column vectors are a*, b*, c*
recip = np.linalg.inv(lat).T

# Normal vector of the (hkl) plane in Cartesian coordinates
normal = h * recip[:, 0] + k * recip[:, 1] + l * recip[:, 2]
norm = np.linalg.norm(normal)
if norm < 1e-12:
    return 0.0, 0.0, 0.0
vx, vy, vz = normal / norm

# Step 1: rotate around the x-axis by a so that vy -> 0
a = float(np.degrees(np.arctan2(vy, vz)))

# Step 2: rotate around the y-axis by b so that vx -> 0
v_z_after_x = float(np.sqrt(vy ** 2 + vz ** 2))
b = float(np.degrees(np.arctan2(-vx, v_z_after_x)))

return a, b, 0.0
```

### Known Limitations

- VESTA's `-export_img` parameter only exports the image and **does not make the program exit automatically**, so the plugin **actively terminates the VESTA process** after detecting that the PNG has been generated.
- VESTA's command line only exposes `-rotate_x/y/z` Euler angle parameters and **cannot directly specify the `[hkl]` normal direction**. The crystal plane projection in the plugin uses heuristic approximate rotation; precise alignment requires a preset `.vesta` template file (not implemented yet).
- Linux headless servers require an `Xvfb` virtual display:

  ```bash
  xvfb-run -a /path/to/VESTA -open structure.cif -export_img output.png -close
  ```

  Or add `["xvfb-run", "-a"]` before the `Popen` arguments in `render_vesta.py`.

---

## FAQ

<details>
<summary><b>Plugin loading reports <code>No module named 'mp_api'</code></b></summary>

The Materials Project SDK is not installed. Run the following in your virtual environment:

```bash
pip install mp-api pymatgen
```
</details>

<details>
<summary><b>Rendering reports <code>VESTA executable not found</code></b></summary>

Check whether `VESTA_EXEC` in `.env` contains the correct **absolute path**, or make sure VESTA has been added to the system `PATH`.
</details>

<details>
<summary><b>Rendering reports <code>VESTA process timed out and was terminated</code>, but the image has been generated</b></summary>

This is normal. VESTA does not exit automatically after exporting the image; the plugin actively terminates the process after detecting that the image has been generated. This warning can be ignored.
</details>

<details>
<summary><b>Search returns empty results</b></summary>

1. Confirm that `MP_API_KEY` is valid.
2. Try broader conditions, e.g., change `Si-O` to `Si,O`.
3. Check the search parameters and number of returned results in the backend logs to determine whether it is an API semantics issue or there really are no results.
</details>

<details>
<summary><b>Field error <code>invalid fields requested: ['is_experimental']</code></b></summary>

The Materials Project API has removed the `is_experimental` field and uses `theoretical` instead (`theoretical=False` indicates an experimental structure). Make sure the field name in `mp_api.py` is correct.
</details>

<details>
<summary><b>No output during cooldown</b></summary>

Check whether the `_check_enabled_and_cooldown` function receives the `bot` parameter and uses `bot.send(event, ...)` instead of `event.bot.send(...)`. `GroupMessageEvent` does not have a `.bot` attribute.
</details>

---

## Contributing

Issues and PRs are welcome. If you implement the following features, you are very welcome to share them:

- [ ] Precise `[hkl]` projection (via a preset `.vesta` template)
- [ ] Automatic adaptation for Linux + Xvfb
- [ ] Support for more rendering backends (e.g., ASE, py3Dmol)
- [ ] Support for filtering by space group, band gap, stability, etc.

---

## License

This project is open source under the [MIT License](LICENSE).

---

## Acknowledgements

- [Materials Project](https://materialsproject.org/) — provides an open materials database and API
- [NoneBot2](https://github.com/nonebot/nonebot2) — an excellent Python asynchronous bot framework
- [VESTA](https://jp-minerals.org/vesta/) — a powerful crystal structure visualization tool
- [pymatgen](https://pymatgen.org/) — a Python toolkit for materials science

---

## Disclaimer

This plugin is for learning and scientific research only. When using the Materials Project API, please comply with its [Terms of Use](https://materialsproject.org/terms-of-use).
