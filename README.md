<div align="center">

<img src="icon.png" width="120" alt="Storyboard Logo">

# Storyboard

**Your entire world in one file.**

A desktop worldbuilding app for writers, game designers, and tabletop creators.  
Lore, timelines, maps, graphs, and notes — all in a single portable project.

No cloud. No accounts. No internet. Just your world.

Made for **Windows** and **Linux**.

<br>

[⬇ Download for Windows](https://github.com/patman124/Storyboard/releases/tag/python)

</div>

<br>

---

## 📁 Virtual File System

Everything lives in one `.json` file — a full hierarchy of folders and documents that you organize however makes sense for your world.

- **Five document types** — Text, Tables, Timelines, Image Viewers, and Graphs
- **Drag-and-drop** to reorder files and folders freely
- **Search** by file name or by content across every document
- **Bookmarks** — star your most-used files for instant access from the ★ menu
- **Duplicate, rename, copy, move, and delete** — with confirmation safeguards so you don't lose work
- **Unsaved change detection** — you'll always get prompted before anything gets discarded
- **Save As** automatically offers to copy your custom dictionary and all linked images to the new location

---

## ✍️ Rich Text Editor

Write lore, character bios, session notes — with real formatting, not markdown.

- **Bold**, **italic**, **underline**, **strikethrough** — toolbar buttons and keyboard shortcuts
- **Bullet and numbered lists** with Tab/Shift+Tab nesting, auto-continuation on Enter, and auto-renumbering
- **Find** with highlighted matches across the document
- Full **undo/redo** history
- **Live spellcheck** — misspelled words get red underlines, right-click for suggestions
- **Per-project custom dictionary** (`.dict` file) — add your world's invented words once and they stay known
- **Internal links** to any file in your project, inserted through a visual file picker

---

## 📊 Table Editor

Track characters, items, factions, locations — anything that fits a grid.

- Spreadsheet-style CSV grid with header row
- Full **keyboard navigation** — arrow keys, Tab between cells, Escape to cancel
- **Checkbox cells** — toggle with a click or Spacebar
- **Internal links** work inside cells
- **Drag-and-drop columns and rows** to reorder
- Auto-expanding rows — always a blank row ready at the bottom
- In-editor hotkey legend so you never have to guess

---

## 🕰️ Chronological Timeline

Design your world's calendar from scratch. Define how time works, then fill it with history.

- **Fully configurable time units** — Ages, Years, Months, Days of Month, Days of Week
- **Custom counts and names** for every unit — name your months, your weekdays, your ages
- **Per-age year counts** — the First Age can span 3000 years while the Second Age lasts 500
- **BC/AD-style epochal dating** with customizable era labels (call them whatever fits your world)
- **Master timeline scrubber** — one slider that moves across your entire world history at once
- **Individual unit scrubbers** with mouse wheel support, integer snapping, and current value display
- **Events** with start dates, end dates, descriptions, and embedded links
- **Hierarchical sub-events** that auto-nest inside parent date ranges
- **Live event highlighting** — events light up in the list when the scrubber hits their date
- **Calculated day-of-week** from cumulative day count with configurable offset
- **Day naming exclusion** — name your days of the week OR days of the month (not both, to avoid conflicts)
- **Position memory** — each timeline remembers where you left off

### 📈 Visual Timeline

Toggle to a **graphical Gantt-style view** of your world's history:

- Events rendered as **colored bars** (duration events) or **diamond markers** (point events)
- **Lane-based stacking** — overlapping events stack vertically so nothing is hidden
- **Gold time indicator** shows the current scrubber position
- **Scroll to navigate** through time — mouse wheel pans the view
- **Precision mode** (spacebar toggle) — scroll one day at a time for fine navigation
- **Click any event** to jump the scrubbers to that date
- **Right-click** for the same context menu as the list view
- **Hover tooltips** show event name, date range, and description
- View preference **saved per file** — it remembers whether you prefer list or visual

### 🔁 Recurring Events

Holidays, festivals, market days — events that repeat on a schedule.

- **Three recurrence types:**
  - **Yearly** — every N years in a specific month (e.g., "Harvest Festival, month 9, every year")
  - **Monthly** — every N months (e.g., "Full moon market, every 3 months")
  - **Interval** — every N days from a start date (e.g., "Patrol rotation every 14 days")
- **Two day rules:**
  - **Specific day** — "On day 15 of the month"
  - **Nth weekday** — "The last Thursday of the month" (1st, 2nd, 3rd, 4th, or last)
- **Multi-day duration** — a 5-day festival shows as a bar, not just a dot
- **Active period** — set when a recurring event starts and ends (required, to prevent performance issues)
- **Gold ★ indicator** in the time navigator when the current date is a recurring event
- **Always visible** in the event list with highlight on matching dates
- **Rendered on the visual timeline** as gold markers with lane stacking
- **Links in descriptions** — right-click to insert links to other files in your project
- **Occurrence count validation** — warns you before creating thousands of events that would slow things down

---

## 🗺️ Image Viewer

Pin notes to maps. Annotate character art. Label diagrams. All without leaving the app.

- Supports **PNG, JPG, WEBP, GIF** — including full **animated GIF playback**
- **Pin markers** — colored dots placed anywhere on the image with:
  - Custom labels visible on the map
  - Hover notes for longer descriptions
  - Links to other files in your project
- **Blinking pins** — make key locations pulse to draw attention
- **Floating text labels** — customizable color, font size, background color, and borders
- **Fit-to-window** and **full-size** viewing modes
- **Shift+drag** to reposition any marker after placing it
- Images stored as **relative paths** — your project folder stays fully portable

---

## 🕸️ Graph Editor

Map relationships, family trees, faction webs, and flowcharts with a node-and-edge canvas.

- **Nodes** with customizable shapes — circle, rectangle, diamond, hexagon, triangle, star, octagon, pill, or custom image
- **Edges** — directed, undirected, or bidirectional, with labels and descriptions
- **Color-coded groups** — assign nodes to groups that auto-color and label
- **Junction nodes** — add bends to edges by Ctrl+clicking on a connection
- **Zoom, pan, and fit-to-view** — middle-click drag to pan, scroll to zoom
- **Multi-select and align** — box-select nodes, then align horizontally or vertically
- **Undo/redo** with full state history
- **Copy/paste nodes** for quick duplication
- **Node images** — use character portraits or icons as node shapes
- **Hover tooltips** on nodes and edges for descriptions
- **Links** — attach any node to a file in your project, click to navigate

---

## 🔗 Internal Linking

Every file can link to every other file. Your world becomes a connected web, not a pile of documents.

- `[[path/to/file|Display Text]]` syntax works everywhere — text, tables, timeline events, image pins, labels, graphs, and recurring events
- **Click any link** to jump directly to the target file
- **Links auto-update** when you rename or move files — nothing breaks
- **Right-click → Insert Link** opens a visual file picker so you never have to type paths manually

---

## ⭐ Bookmarks

Quick access to your most-used files.

- **★ toggle** on the right side of the tab bar — one click to bookmark the current file
- **★ menu** in the top bar — click to see all bookmarks and jump to any of them instantly
- **Right-click any file** in the tree → Add/Remove Bookmark
- Bookmarks are **per-world-file** — each project has its own favorites

---

## 🗂️ Tabs & Windows

- Open as many files as you want in **tabs** along the editor top
- **Drag tabs** to reorder them
- **Pop out** any file into its own floating window — perfect for referencing one doc while writing another
- Content **syncs back** to the project when you close a pop-out
- Right-click any tab to close, close others, or pop out
- Optional **auto-collapse** hides the file tree when you open a document for maximum writing space

---

## 🎨 Themes & Settings

- **Dark and Light** color themes
- **Startup behavior** — always reopen your last file, ask each time, or start fresh
- Configurable **window size** and **fullscreen** launch
- All accessible from the ⚙️ button in-app

---
---

## Getting Started

Grab the `win_storyboard .zip` from [Releases](https://github.com/patman124/Storyboard/releases/tag/python), extract the zip file and run the exe. No install required.

1. Launch Storyboard
2. **Save As** to create your world file, or **Load** an existing `.json`
3. Right-click the file tree to create folders and documents
4. Double-click any file to open it in the editor
5. **Save** to persist changes to disk

---

## Keyboard Shortcuts

<details>
<summary><strong>Text Editor</strong></summary>

| Key | Action |
|-----|--------|
| `Ctrl+B` | Bold |
| `Ctrl+I` | Italic |
| `Ctrl+U` | Underline |
| `Ctrl+F` | Find |
| `Ctrl+Z / Y` | Undo / Redo |
| `Ctrl+A` | Select All |
| `Tab` | Indent list item |

</details>

<details>
<summary><strong>Timeline</strong></summary>

| Key | Action |
|-----|--------|
| `Enter` | Edit selected event |
| `Shift+Enter` | New event |
| `Delete` | Remove event |
| `Arrow keys` | Navigate events |
| `Space` | Toggle precision scroll (visual view) |

</details>

<details>
<summary><strong>Table</strong></summary>

| Key | Action |
|-----|--------|
| `Arrow keys` | Navigate cells |
| `Tab` | Next cell |
| `Space` | Toggle checkbox |
| `Del` | Clear cell |
| `Esc` | Cancel edit |

</details>

<details>
<summary><strong>Graph</strong></summary>

| Key | Action |
|-----|--------|
| `Ctrl+Click` | Start/complete connection |
| `Shift+Drag` | Move selected nodes |
| `Ctrl+Z / Y` | Undo / Redo |
| `Ctrl+C / V` | Copy / Paste nodes |
| `Delete` | Remove selected nodes |
| `Escape` | Cancel connection |

</details>

---

## Project Structure

```
Storyboard/
├── storyboard.exe          ← The app
├── storyboard.config       ← Settings (auto-generated)
└── _internal/              ← Runtime files

Your world (saved anywhere)/
├── MyWorld.json            ← Entire world in one portable file
├── MyWorld.dict            ← Custom spellcheck dictionary
└── images/                 ← Recommended to keep images for your world in the same folder (paths are relative)
```

---

## Building from Source

<details>
<summary>Click to expand</summary>

**Requirements:**
- Python 3.8+
- Tkinter (included with most Python installations)
- Pillow
- pyspellchecker

```bash
pip install Pillow pyspellchecker tksheet
python storyboard.py
```

**To compile a standalone `.exe`:**

Windows
```
pyinstaller --onedir --windowed --icon=logo.ico --add-data "logo.ico;." --add-data "icon.png;." --collect-data spellchecker storyboard.py
```
Linux
```
pyinstaller --onedir --windowed --add-data "logo.ico:." --add-data "icon.png:." --collect-data spellchecker storyboard.py
```
Output goes to `dist/`.

</details>

---

## Configuration

<details>
<summary>Click to expand</summary>

Settings live in `storyboard.config` next to the executable:

```json
{
  "last_opened_file": "~/Documents/MyWorld.json",
  "reopen_behavior": "always",
  "window_size": "1200x800",
  "fullscreen": false,
  "auto_collapse_vfs": false,
  "theme": "dark"
}
```

| Key | Values | Description |
|-----|--------|-------------|
| `reopen_behavior` | `always`, `ask`, `never` | What happens with your last file on launch |
| `theme` | `light`, `dark` | Color scheme |
| `auto_collapse_vfs` | `true`, `false` | Hide file panel when opening a file |
| `fullscreen` | `true`, `false` | Launch maximized |

</details>

---

## License

This project is provided as-is for personal use.
