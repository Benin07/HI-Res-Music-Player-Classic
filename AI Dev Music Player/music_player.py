"""A simple GUI music player built with Tkinter and pygame."""

import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import pygame
try:
    from mutagen import File as MutagenFile  # type: ignore
except Exception:
    # mutagen may not be installed in some environments; fall back to None.
    # Provide a lightweight fallback that exposes .info.length similar to mutagen.File
    from types import SimpleNamespace

    class MutagenFile:
        def __init__(self, path):
            self.path = path
            self.info = SimpleNamespace(length=self._probe_length(path))

        @staticmethod
        def _probe_length(path):
            # Try to use pygame to probe length if possible; initialize mixer if needed.
            try:
                if not pygame.mixer.get_init():
                    # initialize with default values; this is lightweight for probing
                    pygame.mixer.init()
                snd = pygame.mixer.Sound(path)
                return float(snd.get_length())
            except Exception:
                # As a last resort, try to read WAV file length via wave module
                try:
                    import wave
                    with wave.open(path, 'rb') as wf:
                        frames = wf.getnframes()
                        rate = wf.getframerate()
                        return frames / float(rate) if rate else 0
                except Exception:
                    return 0

SUPPORTED_EXTENSIONS = (".mp3", ".wav", ".ogg", ".flac")


class MusicPlayer:
    def __init__(self, root):
        self.root = root
        self.root.title("Hi-Res Music Player")
        self.root.geometry("600x600")
        self.root.resizable(False, False)

        pygame.mixer.init()

        self.playlist = []
        self.current_index = None
        self.paused = False
        self.playing = False
        self.track_length = 0
        self.seek_offset = 0
        self.slider_dragging = False

        self._build_ui()
        self._poll_progress()

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")

        # Now playing label
        self.track_var = tk.StringVar(value="No track loaded")
        ttk.Label(
            self.root, textvariable=self.track_var, font=("Helvetica", 13, "bold"),
            anchor="center", wraplength=520,
        ).pack(fill="x", padx=20, pady=(15, 5))

        # Playlist box
        list_frame = ttk.Frame(self.root)
        list_frame.pack(fill="both", expand=True, padx=20, pady=5)
        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side="right", fill="y")
        self.listbox = tk.Listbox(
            list_frame, selectmode="browse", activestyle="dotbox",
            yscrollcommand=scrollbar.set, font=("Helvetica", 11),
        )
        self.listbox.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self.listbox.yview)
        self.listbox.bind("<Double-Button-1>", lambda e: self.play_selected())

        # Progress bar + time labels
        progress_frame = ttk.Frame(self.root)
        progress_frame.pack(fill="x", padx=20, pady=5)
        self.time_elapsed = ttk.Label(progress_frame, text="0:00", width=6)
        self.time_elapsed.pack(side="left")
        self.progress = ttk.Scale(progress_frame, from_=0, to=100, orient="horizontal")
        self.progress.pack(side="left", fill="x", expand=True, padx=5)
        self.progress.bind("<ButtonPress-1>", self._on_slider_press)
        self.progress.bind("<ButtonRelease-1>", self._on_slider_release)
        self.time_total = ttk.Label(progress_frame, text="0:00", width=6, anchor="e")
        self.time_total.pack(side="right")

        # Control buttons
        controls = ttk.Frame(self.root)
        controls.pack(pady=8)
        ttk.Button(controls, text="⏮ Prev", command=self.prev_track).grid(row=0, column=0, padx=4)
        self.play_button = ttk.Button(controls, text="▶ Play", command=self.toggle_play)
        self.play_button.grid(row=0, column=1, padx=4)
        ttk.Button(controls, text="⏹ Stop", command=self.stop).grid(row=0, column=2, padx=4)
        ttk.Button(controls, text="⏭ Next", command=self.next_track).grid(row=0, column=3, padx=4)

        # Volume + file buttons
        bottom = ttk.Frame(self.root)
        bottom.pack(fill="x", padx=20, pady=(0, 15))
        ttk.Button(bottom, text="Add Files", command=self.add_files).pack(side="left", padx=(0, 5))
        ttk.Button(bottom, text="Add Folder", command=self.add_folder).pack(side="left", padx=5)
        ttk.Button(bottom, text="Remove", command=self.remove_selected).pack(side="left", padx=5)
        ttk.Label(bottom, text="🔊").pack(side="left", padx=(15, 2))
        self.volume = ttk.Scale(
            bottom, from_=0, to=100, orient="horizontal", command=self._on_volume,
        )
        self.volume.set(70)
        pygame.mixer.music.set_volume(0.7)
        self.volume.pack(side="left", fill="x", expand=True)

    # ----------------------------------------------------------- playlist
    def add_files(self):
        paths = filedialog.askopenfilenames(
            title="Select audio files",
            filetypes=[("Audio files", " ".join(f"*{e}" for e in SUPPORTED_EXTENSIONS)),
                       ("All files", "*.*")],
        )
        self._add_paths(paths)

    def add_folder(self):
        folder = filedialog.askdirectory(title="Select music folder")
        if not folder:
            return
        paths = sorted(
            os.path.join(folder, f)
            for f in os.listdir(folder)
            if f.lower().endswith(SUPPORTED_EXTENSIONS)
        )
        self._add_paths(paths)

    def _add_paths(self, paths):
        for path in paths:
            if path and path not in self.playlist:
                self.playlist.append(path)
                self.listbox.insert("end", os.path.basename(path))

    def remove_selected(self):
        selection = self.listbox.curselection()
        if not selection:
            return
        index = selection[0]
        if index == self.current_index:
            self.stop()
            self.current_index = None
        elif self.current_index is not None and index < self.current_index:
            self.current_index -= 1
        self.listbox.delete(index)
        del self.playlist[index]

    # ------------------------------------------------------------ playback
    def play_selected(self):
        selection = self.listbox.curselection()
        if selection:
            self._play_index(selection[0])

    def toggle_play(self):
        if self.playing and not self.paused:
            pygame.mixer.music.pause()
            self.paused = True
            self.play_button.config(text="▶ Play")
        elif self.playing and self.paused:
            pygame.mixer.music.unpause()
            self.paused = False
            self.play_button.config(text="⏸ Pause")
        else:
            selection = self.listbox.curselection()
            if selection:
                self._play_index(selection[0])
            elif self.playlist:
                self._play_index(0)
            else:
                messagebox.showinfo("Music Player", "Add some audio files first.")

    def _play_index(self, index):
        if not (0 <= index < len(self.playlist)):
            return
        path = self.playlist[index]
        try:
            pygame.mixer.music.load(path)
            pygame.mixer.music.play()
        except pygame.error as exc:
            messagebox.showerror("Music Player", f"Could not play file:\n{exc}")
            return
        self.current_index = index
        self.playing = True
        self.paused = False
        self.seek_offset = 0
        self.track_length = self._get_length(path)
        self.track_var.set(os.path.basename(path))
        self.time_total.config(text=self._fmt(self.track_length))
        self.progress.config(to=max(self.track_length, 1))
        self.play_button.config(text="⏸ Pause")
        self.listbox.selection_clear(0, "end")
        self.listbox.selection_set(index)
        self.listbox.see(index)

    def stop(self):
        pygame.mixer.music.stop()
        self.playing = False
        self.paused = False
        self.seek_offset = 0
        self.play_button.config(text="▶ Play")
        self.progress.set(0)
        self.time_elapsed.config(text="0:00")

    def next_track(self):
        if not self.playlist:
            return
        index = 0 if self.current_index is None else (self.current_index + 1) % len(self.playlist)
        self._play_index(index)

    def prev_track(self):
        if not self.playlist:
            return
        index = 0 if self.current_index is None else (self.current_index - 1) % len(self.playlist)
        self._play_index(index)

    # ---------------------------------------------------------------- seek
    def _on_slider_press(self, _event):
        self.slider_dragging = True

    def _on_slider_release(self, _event):
        self.slider_dragging = False
        if self.playing:
            position = self.progress.get()
            try:
                pygame.mixer.music.play(start=position)
                self.seek_offset = position
                if self.paused:
                    pygame.mixer.music.pause()
            except pygame.error:
                pass

    def _on_volume(self, value):
        pygame.mixer.music.set_volume(float(value) / 100)

    # ------------------------------------------------------------- helpers
    @staticmethod
    def _get_length(path):
        try:
            audio = MutagenFile(path)
            if audio is not None and audio.info is not None:
                return audio.info.length
        except Exception:
            pass
        return 0

    @staticmethod
    def _fmt(seconds):
        seconds = int(seconds)
        return f"{seconds // 60}:{seconds % 60:02d}"

    def _poll_progress(self):
        if self.playing and not self.paused:
            pos_ms = pygame.mixer.music.get_pos()
            if pos_ms == -1 and not pygame.mixer.music.get_busy():
                # Track finished — advance to the next one.
                if self.current_index is not None and self.current_index < len(self.playlist) - 1:
                    self.next_track()
                else:
                    self.stop()
            else:
                position = self.seek_offset + max(pos_ms, 0) / 1000
                if not self.slider_dragging:
                    self.progress.set(position)
                self.time_elapsed.config(text=self._fmt(position))
        self.root.after(500, self._poll_progress)


def main():
    root = tk.Tk()
    MusicPlayer(root)
    root.mainloop()


if __name__ == "__main__":
    main()
