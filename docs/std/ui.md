# ui

Themed widgets for gfx windows, in the spirit of Tk's ttk.

The toolkit is immediate mode. Your program keeps its own state in ordinary
variables and describes the whole window every frame. Widgets edit that state
through `&mut` and return true when the user changed it or clicked:

```silly
import ui

fn main():
    var app = ui.app("Hello", 420, 240)
    var name = ""
    var loud = false
    while app.frame():
        app.heading("Greeter")
        app.entry("Your name", &mut name)
        app.checkbox("Shout", &mut loud)
        if app.button("Quit"):
            app.close()
```

Widgets are laid out top to bottom. row()/column()/grid(n)/group(title)/
scroll(id, h) open containers that end with end(). frame() sleeps until
there is input, so an idle window uses no CPU.

## Constants

- `PAD: int = 12`
- `GAP: int = 8`
- `ROW_H: int = 28`
- `FIELD_W: int = 200`
- `FONT: int = 0`

## Types

### `Rect`

A rectangle in window pixels.

- `x: int`
- `y: int`
- `w: int`
- `h: int`

- `contains(self, px: int, py: int) -> bool`
- `intersect(self, o: Rect) -> Rect`
- `inset(self, d: int) -> Rect`
- `is_empty(self) -> bool`

### `Theme`

The colours widgets are drawn with.

- `bg: int`
- `fg: int`
- `dim: int`
- `field: int`
- `border: int`
- `focus: int`
- `accent: int`
- `accent_fg: int`
- `button: int`
- `button_hover: int`
- `button_down: int`
- `select: int`
- `select_fg: int`
- `trough: int`
- `tooltip_bg: int`
- `tooltip_fg: int`
- `shadow: int`
- `radius: int`

### `App`

A window of immediate-mode widgets (see app()); call frame() once per frame.

- `win: gfx.Window`
- `c: gfx.Canvas`
- `th: Theme`
- `running: bool`
- `started: bool`
- `dirty: int`
- `now: int`
- `mx: int`
- `my: int`
- `m_down: bool`
- `m_pressed: bool`
- `m_released: bool`
- `clicks: int`
- `r_pressed: bool`
- `wheel: int`
- `keys: list[int]` — this frame's key presses in order; 0 = text
- `kmods: list[int]`
- `ktext: list[str]`
- `press_taken: bool`
- `blocked: Rect`
- `sim: list[gfx.Event]`
- `active: int`
- `focus: int`
- `focus_text: bool`
- `hover_id: int`
- `prev_hover: int`
- `hover_since: int`
- `order: list[int]`
- `want_cursor: int`
- `cur_cursor: int`
- `enabled: bool`
- `next_w: int`
- `boxes: list[_Box]`
- `titles: list[str]`
- `clips: list[Rect]`
- `cursor: map[int, int]`
- `anchor: map[int, int]`
- `xscroll: map[int, int]`
- `scrolls: map[int, int]`
- `seen: map[int, int]`
- `blink0: int`
- `pop_id: int`
- `pop_r: Rect`
- `pop_items: list[str]`
- `pop_sel: int`
- `pop_top: int`
- `pop_fresh: bool`
- `pick_id: int`
- `pick: int`
- `tip: str`
- `last_id: int`
- `last_r: Rect`
- `entered_id: int`
- `last_entered: int`

- `frame(mut self) -> bool` — Finishes the previous frame, waits for input and starts the next one. Returns false once the window is closed.
- `close(mut self)` — Closes the window; the next frame() returns false.
- `redraw(mut self)` — Draws another frame right away instead of waiting for input.
- `set_theme(mut self, t: Theme)`
- `theme(self) -> Theme`
- `set_title(self, s: str)`
- `canvas(self) -> gfx.Canvas` — The canvas being drawn this frame, for custom painting.
- `width(self) -> int`
- `height(self) -> int`
- `mouse_x(self) -> int`
- `mouse_y(self) -> int`
- `mouse_down(self) -> bool`
- `simulate(mut self, e: gfx.Event)` — Queues an input event as if it came from the window (for tests and demos).
- `set_frame_limit(self, n: int)` — Headless only: how many frames to show before quitting (0 = never).
- `key_pressed(self, key: int, mods: int) -> bool` — True if `key` was pressed this frame with exactly `mods` held.
- `set_enabled(mut self, on: bool)` — Greys out and disables the widgets that follow, until set_enabled(true).
- `width_next(mut self, w: int)` — Gives the next widget a fixed width.
- `entered(self) -> bool` — True if Return was pressed in the most recent entry() this frame.
- `last_rect(self) -> Rect` — Where the most recent widget was placed this frame.
- `focus_last(mut self)` — Moves keyboard focus to the most recent widget.
- `row(mut self)` — Lays out the following widgets left to right.
- `column(mut self)` — Lays out the following widgets top to bottom (inside a row or grid).
- `grid(mut self, n: int)` — Lays out the following widgets in `n` equal columns.
- `group(mut self, title: str)` — A framed, titled column.
- `end(mut self)` — Closes the innermost row, column, grid, group or scroll area.
- `scroll(mut self, id: str, h: int)` — A scrolling area `h` pixels tall; close it with end().
- `label(mut self, s: &str)`
- `heading(mut self, s: &str)`
- `title(mut self, s: &str)`
- `caption(mut self, s: &str)` — Small, dimmed text.
- `code(mut self, s: &str)` — Text in a fixed-width font.
- `paragraph(mut self, s: &str)` — Text wrapped to the available width; "\n" starts a new line.
- `separator(mut self)` — A horizontal rule (a vertical one in a row).
- `spacer(mut self, n: int)` — Empty space: `n` pixels down in a column, across in a row.
- `image(mut self, img: gfx.Canvas)` — Shows a canvas as an image.
- `area(mut self, w: int, h: int) -> Rect` — Reserves an area for custom drawing on canvas(); w <= 0 fills the width.
- `tooltip(mut self, text: &str)` — Shows `text` when the mouse rests on the previous widget.
- `button(mut self, label: &str) -> bool` — A push button; true when clicked (or activated with Return/Space).
- `primary_button(mut self, label: &str) -> bool` — A button in the accent colour, for the main action.
- `checkbox(mut self, label: &str, v: &mut bool) -> bool`
- `radio(mut self, label: &str, cur: &mut int, mine: int) -> bool` — One choice of several: selects `mine` into `cur` when clicked.
- `switch(mut self, label: &str, v: &mut bool) -> bool` — An on/off switch.
- `entry(mut self, label: &str, s: &mut str) -> bool` — A one-line text field editing `s`. The label before "##" is shown as a placeholder while the field is empty. True when the text changed; see entered() for Return.
- `secret_entry(mut self, label: &str, s: &mut str) -> bool` — Like entry(), but shows '*' for each character.
- `slider(mut self, label: &str, v: &mut f64, lo: f64, hi: f64) -> bool` — A horizontal slider over lo..hi. Arrow keys step by 1/20 of the range.
- `progress(mut self, frac: f64)` — A bar filled to `frac` (0..1).
- `spinbox(mut self, label: &str, v: &mut int, lo: int, hi: int, step: int) -> bool` — An integer field with up/down arrows (also arrow keys and the wheel).
- `combobox(mut self, label: &str, items: &list[str], sel: &mut int) -> bool` — A drop-down list choosing `sel` from `items`.
- `listbox(mut self, label: &str, items: &list[str], sel: &mut int, rows: int) -> bool` — A list showing `rows` items at a time; `sel` is the selected index (-1 for none).
- `tabs(mut self, names: &list[str], cur: &mut int) -> bool` — A row of tabs; `cur` is the selected one. Draw the page's widgets after it.

## Functions

### `light() -> Theme`

The default light theme.

### `dark() -> Theme`

A dark theme.

### `app(title: str, w: int, h: int) -> App`

Opens a window and returns its app.
