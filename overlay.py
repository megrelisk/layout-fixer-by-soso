"""Red marks under doubtful words and the suggestion popup above them.

Runs Tk in its own thread; other threads talk to it through a queue. The
windows never take the keyboard focus, so the user keeps typing where they were.

A mark sits under the first letter of a doubtful word. Hovering anywhere over
the word opens a popup above it with up to two suggestions and the word itself:
clicking a suggestion replaces the word, clicking the word keeps it.
"""

import queue
import threading
import time
from dataclasses import dataclass, field

MARK_COLOR = "#e53935"
HIDE_DELAY = 0.7        # seconds the mouse may be away before the popup closes
MAX_AGE = 600           # a mark older than this is dropped


@dataclass
class Mark:
    id: int
    word: str               # as typed
    suggestions: list       # replacements, best first
    x: int                  # screen position of the word's first letter
    top: int
    bottom: int
    end_x: int              # right edge of the word
    created: float = field(default_factory=time.monotonic)

    @property
    def letter_width(self):
        return max(6, (self.end_x - self.x) // max(1, len(self.word)))

    def word_box(self):
        return (self.x - 2, self.top - 2, max(self.end_x, self.x + 8) + 2, self.bottom + 6)


def _inside(box, x, y):
    return box[0] <= x <= box[2] and box[1] <= y <= box[3]


class Overlay:
    def __init__(self, on_pick, on_keep, cursor_pos, make_tool_window):
        self._on_pick = on_pick        # (mark_id, replacement)
        self._on_keep = on_keep        # (mark_id)
        self._cursor_pos = cursor_pos
        self._make_tool_window = make_tool_window
        self._cmds = queue.Queue()
        self._boxes = []               # screen boxes of our windows, for the mouse hook
        self._lock = threading.Lock()
        threading.Thread(target=self._run, daemon=True, name="overlay").start()

    # --- any thread

    def show(self, mark):
        self._cmds.put(("show", mark))

    def remove(self, mark_id):
        self._cmds.put(("remove", mark_id))

    def clear(self):
        self._cmds.put(("clear", None))

    def contains(self, x, y):
        """True if a click at (x, y) lands on one of our windows."""
        with self._lock:
            return any(_inside(b, x, y) for b in self._boxes)

    # --- Tk thread

    def _run(self):
        import tkinter as tk
        self.tk = tk
        self.root = tk.Tk()
        self.root.withdraw()
        self.marks = {}         # id -> (Mark, Toplevel)
        self.popup = None       # (mark_id, Toplevel, box)
        self.away_since = None
        self.root.after(40, self._tick)
        self.root.mainloop()

    def _window(self):
        win = self.tk.Toplevel(self.root)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.update_idletasks()
        try:
            self._make_tool_window(int(self.root.tk.call("wm", "frame", win), 16))
        except Exception:
            pass
        return win

    def _tick(self):
        try:
            while True:
                cmd, arg = self._cmds.get_nowait()
                getattr(self, "_do_" + cmd)(arg)
        except queue.Empty:
            pass
        now = time.monotonic()
        for mid, (mark, _) in list(self.marks.items()):
            if now - mark.created > MAX_AGE:
                self._do_remove(mid)
        self._hover()
        self._publish_boxes()
        self.root.after(40, self._tick)

    def _do_show(self, mark):
        self._do_remove(mark.id)
        win = self._window()
        win.configure(bg=MARK_COLOR)
        win.geometry(f"{mark.letter_width}x3+{mark.x}+{mark.bottom + 1}")
        self.marks[mark.id] = (mark, win)

    def _do_remove(self, mark_id):
        if self.popup and self.popup[0] == mark_id:
            self._close_popup()
        item = self.marks.pop(mark_id, None)
        if item:
            item[1].destroy()

    def _do_clear(self, _):
        for mid in list(self.marks):
            self._do_remove(mid)

    def _hover(self):
        x, y = self._cursor_pos()
        if self.popup:
            mid, _, box = self.popup
            mark = self.marks.get(mid, (None,))[0]
            if _inside(box, x, y) or mark and _inside(mark.word_box(), x, y):
                self.away_since = None
            elif self.away_since is None:
                self.away_since = time.monotonic()
            elif time.monotonic() - self.away_since > HIDE_DELAY:
                self._close_popup()
            return
        for mid, (mark, _) in self.marks.items():
            if _inside(mark.word_box(), x, y):
                self._open_popup(mark)
                return

    def _open_popup(self, mark):
        tk = self.tk
        win = self._window()
        win.configure(bg="#9e9e9e")
        frame = tk.Frame(win, bg="white", padx=4, pady=2)
        frame.pack(padx=1, pady=1)
        font = ("Segoe UI", 11)

        def option(text, action, **style):
            lbl = tk.Label(frame, text=text, bg="white", padx=6, pady=1, cursor="hand2",
                           font=font, **style)
            lbl.pack(side="left")
            lbl.bind("<Enter>", lambda e: lbl.configure(bg="#e3f2fd"))
            lbl.bind("<Leave>", lambda e: lbl.configure(bg="white"))
            lbl.bind("<Button-1>", lambda e: action())

        for s in mark.suggestions:
            option(s, lambda s=s: self._pick(mark.id, s), fg="#0d47a1")
        tk.Frame(frame, width=1, bg="#bdbdbd").pack(side="left", fill="y", padx=3)
        option(mark.word, lambda: self._keep(mark.id), fg="#757575")

        win.update_idletasks()
        w, h = win.winfo_reqwidth(), win.winfo_reqheight()
        px, py = mark.x - 8, mark.top - h - 4
        if py < 0:
            py = mark.bottom + 6
        win.geometry(f"+{px}+{py}")
        self.popup = (mark.id, win, (px, py, px + w, py + h))
        self.away_since = None

    def _close_popup(self):
        if self.popup:
            self.popup[1].destroy()
            self.popup = None

    def _pick(self, mark_id, text):
        self._do_remove(mark_id)
        self._on_pick(mark_id, text)

    def _keep(self, mark_id):
        self._do_remove(mark_id)
        self._on_keep(mark_id)

    def _publish_boxes(self):
        boxes = []
        for mark, win in self.marks.values():
            boxes.append((mark.x, mark.bottom, mark.x + mark.letter_width, mark.bottom + 5))
        if self.popup:
            boxes.append(self.popup[2])
        with self._lock:
            self._boxes = boxes
