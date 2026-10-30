# gfx

2D graphics: canvases, anti-aliased shapes, text, images and a window.

```silly
import gfx
fn main():
    let win = gfx.open("Hello", 400, 300)
    var running = true
    while running:
        for ev in win.events():
            match ev:
                case Quit: running = false
                case _: pass
        let c = win.canvas()
        c.clear(gfx.WHITE)
        c.text(20, 20, "Hello, Silly", gfx.BLACK, gfx.FONT_TITLE)
        win.present()
        win.wait(16)
```

Colors are ints 0xAARRGGBB (see rgb / rgba). Windows use SDL2 when it is
installed and a display is available; otherwise they are headless.
SILLY_GFX=headless forces headless mode. A headless window saves each
presented frame to the PNG named by SILLY_GFX_SHOT, if set, and asks to quit
after SILLY_GFX_FRAMES frames (default 3). SDL2 is loaded at run time, so
programs build without its headers.

## Constants

- `BLACK: int = 0xFF000000`
- `WHITE: int = 0xFFFFFFFF`
- `TRANSPARENT: int = 0`
- `RED: int = 0xFFE53935`
- `GREEN: int = 0xFF43A047`
- `BLUE: int = 0xFF1E88E5`
- `YELLOW: int = 0xFFFDD835`
- `ORANGE: int = 0xFFFB8C00`
- `PURPLE: int = 0xFF8E24AA`
- `GRAY: int = 0xFF9E9E9E`
- `FONT_SANS: int = 0`
- `FONT_BOLD: int = 1`
- `FONT_MONO: int = 2`
- `FONT_SMALL: int = 3`
- `FONT_HEADING: int = 4`
- `FONT_TITLE: int = 5`
- `MOD_SHIFT: int = 1`
- `MOD_CTRL: int = 2`
- `MOD_ALT: int = 4`
- `MOD_SUPER: int = 8`
- `MOUSE_LEFT: int = 1`
- `MOUSE_MIDDLE: int = 2`
- `MOUSE_RIGHT: int = 3`
- `KEY_RETURN: int = 0x0D` — Key codes (printable keys are their lowercase character: 'a' as int).
- `KEY_ESCAPE: int = 0x1B`
- `KEY_BACKSPACE: int = 0x08`
- `KEY_TAB: int = 0x09`
- `KEY_SPACE: int = 0x20`
- `KEY_DELETE: int = 0x7F`
- `KEY_RIGHT: int = 0x4000004F`
- `KEY_LEFT: int = 0x40000050`
- `KEY_DOWN: int = 0x40000051`
- `KEY_UP: int = 0x40000052`
- `KEY_HOME: int = 0x4000004A`
- `KEY_END: int = 0x4000004D`
- `KEY_PAGE_UP: int = 0x4000004B`
- `KEY_PAGE_DOWN: int = 0x4000004E`
- `KEY_INSERT: int = 0x40000049`
- `KEY_KP_ENTER: int = 0x40000058`
- `KEY_F1: int = 0x4000003A`
- `CURSOR_ARROW: int = 0`
- `CURSOR_TEXT: int = 1`
- `CURSOR_WAIT: int = 2`
- `CURSOR_CROSSHAIR: int = 3`
- `CURSOR_RESIZE_H: int = 7`
- `CURSOR_RESIZE_V: int = 8`
- `CURSOR_MOVE: int = 9`
- `CURSOR_NO: int = 10`
- `CURSOR_HAND: int = 11`

## Types

### `Canvas`

A pixel buffer. Canvases are handles: copies refer to the same pixels, and the pixels live until free() (or the end of the program).

- `id: int`

- `width(self) -> int`
- `height(self) -> int`
- `free(self)`
- `resize(self, w: int, h: int)` — Changes the size, keeping the overlapping pixels; resets the clip.
- `clip(self, x: int, y: int, w: int, h: int)` — Restricts drawing to a rectangle (clipped to the canvas).
- `unclip(self)`
- `clear(self, color: int)` — Sets every pixel inside the clip to `color` (no blending).
- `fill_rect(self, x: int, y: int, w: int, h: int, color: int)`
- `rect(self, x: int, y: int, w: int, h: int, t: int, color: int)` — A rectangle outline `t` pixels thick, drawn inside the rectangle.
- `fill_round_rect(self, x: int, y: int, w: int, h: int, r: int, color: int)`
- `round_rect(self, x: int, y: int, w: int, h: int, r: int, t: int, color: int)`
- `fill_circle(self, cx: f64, cy: f64, r: f64, color: int)`
- `circle(self, cx: f64, cy: f64, r: f64, t: f64, color: int)`
- `line(self, x0: f64, y0: f64, x1: f64, y1: f64, w: f64, color: int)` — An anti-aliased line `w` pixels wide with round ends.
- `polyline(self, pts: list[f64], w: f64, color: int)` — Connected line segments through points given as [x0, y0, x1, y1, ...].
- `fill_poly(self, pts: list[f64], color: int)` — A filled polygon from points [x0, y0, x1, y1, ...] (nonzero winding).
- `fill_triangle(self, x0: f64, y0: f64, x1: f64, y1: f64, x2: f64, y2: f64, color: int)`
- `gradient_v(self, x: int, y: int, w: int, h: int, top: int, bottom: int)`
- `gradient_h(self, x: int, y: int, w: int, h: int, left: int, right: int)`
- `set_pixel(self, x: int, y: int, color: int)`
- `blend_pixel(self, x: int, y: int, color: int)` — Blends `color` over the pixel at (x, y).
- `pixel(self, x: int, y: int) -> int` — The pixel at (x, y), or 0 outside the canvas.
- `text(self, x: int, y: int, s: str, color: int, font: int) -> int` — Draws `s` with the top-left of its line box at (x, y); returns its width.
- `text_centered(self, x: int, y: int, w: int, h: int, s: str, color: int, font: int)` — Draws `s` centred in the rectangle (x, y, w, h).
- `blit(self, src: Canvas, x: int, y: int, alpha: int)` — Blends all of `src` onto this canvas at (x, y), with extra opacity `alpha` (0..255).
- `blit_scaled(self, src: Canvas, x: int, y: int, w: int, h: int)` — Stretches all of `src` over (x, y, w, h), nearest-neighbour.
- `pixels(self) -> list[int]` — Every pixel, row by row.
- `set_pixels(self, px: &list[int])`
- `save_png(self, path: str) -> bool`
- `save_ppm(self, path: str) -> bool`

### `Event`

Something that happened to a window (see Window.poll()).

- `Quit`
- `Resize(w: int, h: int)`
- `MouseMove(x: int, y: int)`
- `MouseDown(x: int, y: int, button: int, clicks: int)`
- `MouseUp(x: int, y: int, button: int)`
- `Wheel(dx: int, dy: int)`
- `KeyDown(key: int, mods: int, repeat: bool)`
- `KeyUp(key: int, mods: int)`
- `Text(str)`
- `FocusIn`
- `FocusOut`
- `Expose`
- `MouseLeave`

### `Window`

The program's window (one at a time) and its back buffer, which follows the window's size.

- `back: Canvas`

- `canvas(self) -> Canvas` — The back buffer, resized to the window if the window changed size.
- `width(self) -> int`
- `height(self) -> int`
- `present(self)` — Shows the back buffer.
- `poll(self) -> Option[Event]` — The next pending event, if any.
- `events(self) -> list[Event]` — All pending events.
- `wait(self, ms: int) -> bool` — Sleeps until an event arrives or `ms` milliseconds pass; true if an event is ready.
- `set_title(self, s: str)`
- `set_cursor(self, kind: int)`
- `set_frame_limit(self, n: int)` — Headless only: send Quit after `n` presented frames (0 = never), unless SILLY_GFX_FRAMES is set.
- `backend(self) -> str` — "sdl" or "headless".
- `close(self)`

## Functions

### `rgb(r: int, g: int, b: int) -> int`

An opaque colour from 0-255 channels.

### `rgba(r: int, g: int, b: int, a: int) -> int`

A colour with alpha (0 transparent, 255 opaque).

### `with_alpha(c: int, a: int) -> int`

The color `c` with its alpha replaced by `a` (0..255).

### `mix(a: int, b: int, t: f64) -> int`

Linear blend from `a` (t = 0.0) to `b` (t = 1.0), all four channels.

### `red_of(c: int) -> int`

The red channel of c.

### `green_of(c: int) -> int`

The green channel of c.

### `blue_of(c: int) -> int`

The blue channel of c.

### `alpha_of(c: int) -> int`

The alpha channel of c.

### `hex(s: str) -> Option[int]`

Parses "#rgb", "#rrggbb" or "#aarrggbb" (the "#" is optional).

### `text_width(s: str, font: int) -> int`

How many pixels wide s is in font.

### `text_index(s: str, font: int, x: int) -> int`

Byte offset of the character boundary nearest to `x` pixels into `s`.

### `font_height(font: int) -> int`

The line height of font in pixels.

### `font_ascent(font: int) -> int`

Pixels from the top of a line to font's baseline.

### `canvas(w: int, h: int) -> Canvas`

A new canvas, transparent black.

### `load_image(path: str) -> Option[Canvas]`

Loads a binary PPM (P6) or an uncompressed BMP.

### `key_f(n: int) -> int`

Function key n (1..12).

### `open(title: str, w: int, h: int) -> Window`

Opens the window.

### `clipboard_set(s: str)`

Puts s on the system clipboard.

### `clipboard_get() -> str`

The clipboard's text, or "".

### `ticks() -> int`

Milliseconds since the first call (monotonic).

### `sleep_ms(ms: int)`

Waits ms milliseconds.
