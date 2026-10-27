# pcbmotorgen

![Heavily In Progress](./imgs/in-progress-banner.svg)

A tool for generating multi-layer PCB stator layouts for linear coreless
motors.

Rather than drawing copper traces by hand, `pcbmotorgen` computes coil
geometry via extensible **routing patterns**, validates the motor force and
DFM (design-rule) constraints, and writes the complete track/arc/via layout to
an open KiCad 10 PCB file over the KiCad 10 IPC (protobuf over NNG) interface.

The user interface is a **Tauri + Svelte desktop app** (`pcbmotorgen` parent
crate) backed by four independently-buildable Rust sub-crates:
`pcbmotorgen-routing` (traces & generation), `pcbmotorgen-simulation` (all
physics), `pcbmotorgen-dfm` (design rules + DRC diagnostics, downstream of
routing), and `pcbmotorgen-export` (KiCad adapter + DXF exporter). There is no
Python runtime dependency.

---

## What it generates

Given mechanical and electrical parameters the tool produces:

- **Extensible coil geometry** — a selected _routing pattern_ (bundled
  `infinity-braid` by default, or a user-authored Rust `cdylib` / Python runner
  plugin) produces segments, arcs, and vias, each owning its `layer` and `net`.
- **DFM diagnostics downstream** — any routing is allowed in the generator;
  the `pcbmotorgen-dfm` crate applies the `DesignRules` sizing authority and
  runs overlap / via-pad DRC (`check_interference`) on the generated geometry
  afterwards, reporting violations as diagnostics (never altering geometry).
- **Multiphysics feedback** — magnetic B-field grid, Lorentz force sweep with
  ripple %, stackup, power budget, friction, and height stack, all computed in
  the simulation crate.
- **KiCad export** — the KiCad adapter consumes the generic geometry model and
  writes tracks/arcs/vias atomically (single undo step).

The result is sent directly to KiCad as one undoable commit via the IPC API.

---

## Requirements

- **KiCad 10.0+** — PCB editor open, IPC API enabled
- **Rust (stable, 1.80+)** — sub-crates + Tauri backend
- **Node.js 18+** — Svelte frontend
- macOS 12+ or Linux (Windows untested)

---

## Installation

```bash
git clone https://github.com/<your-handle>/pcbmotorgen.git
cd pcbmotorgen

# Desktop app (primary UI)
cd app
pnpm install
pnpm run tauri dev
```

---

## Frontend checks

Run the desktop frontend checks from `app/desktop` after installing its locked dependencies:

```bash
pnpm check       # Svelte and TypeScript diagnostics
pnpm test        # Frontend unit tests
pnpm build      # Production frontend build
```

`pnpm check` uses the project's pinned checker and TypeScript dependencies, not an external `npx` environment. These checks do not establish numerical qualification or native WKWebView acceptance.

## Quick start

### 1. Enable the KiCad IPC API (one-time)

1. Open KiCad 10
2. **Preferences → Plugins → Enable IPC API**
3. Restart KiCad

### 2. Launch the desktop app

```bash
cd app
pnpm run tauri dev
```

Configure your motor in the UI, preview the magnetic field and force plots,
then click **Write to KiCad** when ready.

All generated tracks and vias appear as **one undo step** — `Ctrl+Z` rolls
back the entire layout cleanly.
