import json
import os
import platform
import queue
import random
import sys
import threading
import time
import tkinter as tk
import customtkinter as ctk
from PIL import Image, ImageTk

# Fast native Windows TTS binding without external process overhead
if platform.system() == "Windows":
    try:
        import win32com.client
        import pythoncom
    except ImportError:
        pass


def resource_path(relative_path: str) -> str:
    """Get absolute path to resource, works for dev and PyInstaller packaging."""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


# --- CONFIGURATION & LOCK FILES ---
CONFIG_FILE = os.path.join(os.path.expanduser("~"), ".bingo_caller_config.json")
LOCK_FILE = os.path.join(os.path.expanduser("~"), ".bingo_caller_app.lock")


def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_config(config_data):
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(config_data, f)
    except Exception:
        pass


def acquire_lock():
    if os.path.exists(LOCK_FILE):
        try:
            with open(LOCK_FILE, "r") as f:
                old_pid = int(f.read().strip())

            if platform.system() == "Windows":
                import subprocess
                cmd = f'tasklist /FI "PID eq {old_pid}"'
                tasks = subprocess.check_output(cmd, shell=True).decode()
                if "python" not in tasks.lower():
                    os.remove(LOCK_FILE)
                else:
                    print(f"Bingo Caller is already running! (PID: {old_pid})")
                    sys.exit(0)
            else:
                os.remove(LOCK_FILE)
        except Exception:
            try:
                os.remove(LOCK_FILE)
            except Exception:
                pass

    try:
        with open(LOCK_FILE, "w") as f:
            f.write(str(os.getpid()))
    except Exception:
        pass


acquire_lock()

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

speech_queue = queue.Queue()


def clear_speech_queue():
    """Purge all pending speech tasks from the queue."""
    with speech_queue.mutex:
        speech_queue.queue.clear()


def speech_worker():
    """Background worker with native COM initialization for Windows and voice selection."""
    system_os = platform.system()
    speaker = None

    if system_os == "Windows":
        try:
            pythoncom.CoInitialize()
            speaker = win32com.client.Dispatch("SAPI.SpVoice")
        except Exception:
            speaker = None

    try:
        while True:
            item = speech_queue.get()
            if item is None:
                break

            phrase, post_delay, speech_rate, on_complete_func, app_ref, selected_voice = item

            try:
                if system_os == "Windows" and speaker:
                    if selected_voice:
                        try:
                            voices = speaker.GetVoices()
                            for v in voices:
                                if v.GetDescription() == selected_voice:
                                    speaker.Voice = v
                                    break
                        except Exception:
                            pass
                    speaker.Speak(phrase)
                elif system_os == "Darwin":
                    os.system(f'say "{phrase}"')
                else:
                    os.system(f'espeak "{phrase}"')
            except Exception:
                pass

            if post_delay > 0:
                time.sleep(post_delay)

            if on_complete_func and app_ref:
                try:
                    app_ref.after(10, on_complete_func)
                except Exception:
                    pass

            speech_queue.task_done()
    finally:
        if system_os == "Windows":
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass


threading.Thread(target=speech_worker, daemon=True).start()


class ModernBingoApp(ctk.CTk):

    def __init__(self):
        super().__init__()

        self.title("BINGO CALLER")
        self.configure(fg_color="#000000")
        self.attributes("-fullscreen", True)

        icon_path = resource_path("bingo.ico")
        if os.path.exists(icon_path):
            try:
                self.iconbitmap(icon_path)
            except Exception:
                pass

        self.colors = [
            "#FF007F", "#00F5FF", "#7000FF", "#00FF66",
            "#FFB800", "#FF4500", "#18FFFF", "#CCFF00"
        ]

        self.esc_count = 0
        self.reset_count = 0
        self.paused_mode = False
        self.is_busy_speaking = False
        self.has_paused_once = False
        self.first_draw_after_check = False
        self.fullscreen_mode = False
        self.first_five_drawn = []
        self.game_mode_selected = False
        self.current_announcement = ""
        self.last_rendered_text = "--"
        self.last_rendered_color = "#64748B"
        self.splash_active = True
        self.ui_built = False
        
        self.raw_splash_image = None
        self.splash_image_tk = None

        # Winner GIF variables
        self.winner_active = False
        self.winner_frames = []
        self.winner_frame_index = 0
        self.winner_animation_job = None

        self.speech_enabled_var = ctk.BooleanVar(value=True)
        
        self.available_voices = self.get_windows_voices()
        saved_config = load_config()
        saved_voice = saved_config.get("selected_voice")

        if saved_voice and saved_voice in self.available_voices:
            default_voice_val = saved_voice
        else:
            default_voice_val = self.available_voices[0] if self.available_voices else "Default Voice"

        self.selected_voice_var = ctk.StringVar(value=default_voice_val)

        self.draw_sequence = list(range(1, 91))
        random.shuffle(self.draw_sequence)
        self.drawn_numbers = set()

        self.build_main_ui()

        self.splash_frame = ctk.CTkFrame(self, fg_color="#000000")
        self.splash_frame.place(relx=0, rely=0, relwidth=1, relheight=1)

        self.splash_canvas = tk.Canvas(self.splash_frame, bg="#000000", highlightthickness=0, bd=0)
        self.splash_canvas.pack(fill="both", expand=True)
        self.splash_canvas.bind("<Configure>", self.redraw_splash_canvas)

        self.splash_prompt = ctk.CTkLabel(
            self.splash_frame,
            text="PRESS  [ TAB ]  OR CLICK TO START GAME",
            font=ctk.CTkFont(size=28, weight="bold"),
            text_color="#FFFFFF",
            fg_color="#000000",
            corner_radius=8
        )
        self.splash_prompt.place(relx=0.5, rely=0.92, anchor="center")

        # --- DEDICATED TAB & KEY BINDINGS ---
        self.bind("<Tab>", self._on_tab_key)
        self.bind("<KeyPress-Tab>", self._on_tab_key)
        self.bind("<ISO_Left_Tab>", self._on_tab_key)
        self.bind_all("<Tab>", self._on_tab_key)
        self.bind_all("<KeyPress-Tab>", self._on_tab_key)
        self.bind_all("<ISO_Left_Tab>", self._on_tab_key)
        self.bind_all("<Key>", self._on_key_press)

        self.splash_frame.bind("<Button-1>", self.dismiss_splash_screen)
        self.splash_canvas.bind("<Button-1>", self.dismiss_splash_screen)
        self.splash_prompt.bind("<Button-1>", self.dismiss_splash_screen)

        self.lift()
        self.attributes("-topmost", True)
        self.after(100, lambda: self.attributes("-topmost", False))
        self.focus_force()

        self.load_splash_image()

    def get_windows_voices(self):
        voices_list = ["Default Voice"]
        if platform.system() == "Windows":
            try:
                pythoncom.CoInitialize()
                speaker = win32com.client.Dispatch("SAPI.SpVoice")
                voices = speaker.GetVoices()
                for v in voices:
                    desc = v.GetDescription()
                    if desc not in voices_list:
                        voices_list.append(desc)
                pythoncom.CoUninitialize()
            except Exception:
                pass
        return voices_list

    def on_voice_changed(self, choice):
        config = load_config()
        config["selected_voice"] = choice
        save_config(config)
        self.focus_force()

    def _on_tab_key(self, event):
        if self.splash_active:
            self.dismiss_splash_screen()
        return "break"

    def dismiss_splash_screen(self, event=None):
        if self.splash_active:
            self.splash_active = False
            self.splash_frame.place_forget()
            self.base_container.pack(fill="both", expand=True)
            self.update_idletasks()
            self.focus_set()
            self.focus_force()

    def _on_key_press(self, event):
        keysym = event.keysym.lower()
        char = event.char.lower() if event.char else ""

        # If winner banner is active, any key press can dismiss it
        if self.winner_active:
            if keysym in ("escape", "return", "space") or char in ("\r", " ", "w"):
                self.hide_winner_display()
            return

        if self.is_busy_speaking and keysym != "escape" and char != chr(27):
            return

        if self.splash_active:
            if keysym in ("return", "space", "tab", "iso_left_tab") or char in ("\r", " "):
                self.dismiss_splash_screen()
            elif keysym == "escape":
                self.handle_escape()
            return

        if keysym == "return" or char == "\r":
            self.handle_enter()
        elif keysym == "space" or char == " ":
            self.handle_space()
        elif keysym == "r" or char == "r":
            self.handle_reset()
        elif keysym == "x" or char == "x":
            self.handle_x_key()
        elif keysym == "d" or char == "d":
            self.handle_d_key()
        elif keysym == "t" or char == "t":
            self.handle_toggle_view()
        elif keysym == "w" or char == "w":
            self.handle_winner_trigger()
        elif keysym == "l" or char == "l":
            self.set_game_mode("Line")
        elif keysym == "f" or char == "f":
            self.set_game_mode("Full House")
        elif keysym == "c" or char == "c":
            self.set_game_mode("Carry On")
        elif keysym == "escape":
            self.handle_escape()

    def handle_winner_trigger(self):
        """Displays winner.gif and plays we_have_winner.mp3 from the data folder."""
        if self.winner_active:
            return
        
        self.winner_active = type(self).winner_active = True
        
        # 1. Play audio file: data/we_have_winner.mp3 (Lazy loaded to prevent startup hangs)
        audio_path = resource_path(os.path.join("data", "we_have_winner.mp3"))
        if os.path.exists(audio_path):
            try:
                import pygame
                if not pygame.mixer.get_init():
                    pygame.mixer.init()
                pygame.mixer.music.load(audio_path)
                pygame.mixer.music.play()
            except Exception as e:
                print(f"Error playing audio: {e}")

        # 2. Display winner banner: data/winner.gif
        gif_path = resource_path(os.path.join("data", "winner.gif"))
        if hasattr(self, "winner_overlay"):
            self.winner_overlay.place(relx=0, rely=0, relwidth=1, relheight=1)
            self.winner_overlay.lift()
        else:
            self.winner_overlay = ctk.CTkFrame(self, fg_color="#000000")
            self.winner_overlay.place(relx=0, rely=0, relwidth=1, relheight=1)
            
            self.winner_canvas = tk.Canvas(self.winner_overlay, bg="#000000", highlightthickness=0, bd=0)
            self.winner_canvas.pack(fill="both", expand=True)
            self.winner_canvas.bind("<Button-1>", lambda e: self.hide_winner_display())

        self.winner_frames = []
        self.winner_frame_index = 0

        if os.path.exists(gif_path):
            try:
                img = Image.open(gif_path)
                try:
                    while True:
                        self.winner_frames.append(ImageTk.PhotoImage(img.copy()))
                        img.seek(len(self.winner_frames))
                except EOFError:
                    pass
            except Exception:
                self.winner_frames = []

        if self.winner_frames:
            self.animate_winner_gif()
        else:
            # Fallback text if GIF can't be loaded
            self.winner_canvas.delete("all")
            w = self.winfo_screenwidth()
            h = self.winfo_screenheight()
            self.winner_canvas.create_text(
                w // 2, h // 2,
                text="WE HAVE A WINNER!",
                font=("Arial", 64, "bold"),
                fill="#00FF66",
                justify="center"
            )

    def animate_winner_gif(self):
        if not self.winner_active or not self.winner_frames:
            return
        
        w = self.winner_canvas.winfo_width()
        h = self.winner_canvas.winfo_height()
        if w <= 1:
            w = self.winfo_screenwidth()
        if h <= 1:
            h = self.winfo_screenheight()

        frame = self.winner_frames[self.winner_frame_index]
        self.winner_canvas.delete("all")
        self.winner_canvas.create_image(w // 2, h // 2, image=frame, anchor="center")

        self.winner_frame_index = (self.winner_frame_index + 1) % len(self.winner_frames)
        self.winner_animation_job = self.after(100, self.animate_winner_gif)

    def hide_winner_display(self):
        if not self.winner_active:
            return
        self.winner_active = False
        if self.winner_animation_job:
            try:
                self.after_cancel(self.winner_animation_job)
            except Exception:
                pass
        if hasattr(self, "winner_overlay"):
            self.winner_overlay.place_forget()
        
        # Stop audio if playing
        try:
            import pygame
            if pygame.mixer.get_init():
                pygame.mixer.music.stop()
        except Exception:
            pass

    def draw_number(self):
        if self.splash_active or not self.ui_built or self.is_busy_speaking:
            return
        self.esc_count = 0
        self.reset_count = 0

        if not self.game_mode_selected or self.paused_mode or not self.draw_sequence:
            return

        num = self.draw_sequence.pop()
        self.drawn_numbers.add(num)

        if len(self.first_five_drawn) < 5:
            self.first_five_drawn.append(num)

        accent_color = random.choice(self.colors)
        total_drawn = len(self.drawn_numbers)

        self.counter_label.configure(text=f"{total_drawn} / 90")
        self.current_label.configure(
            text=str(num),
            font=ctk.CTkFont(size=380, weight="bold"),
            text_color=accent_color
        )
        self.card_display.configure(border_width=4, border_color=accent_color)
        self.number_tiles[num].configure(fg_color=accent_color, text_color="#0F172A")
        self.overlay_counter_label.configure(text=f"NUMBERS CALLED: {total_drawn} OF 90")

        self.toggle_view(show_overlay=True)
        self.render_3d_text_on_canvas(str(num), front_color=accent_color)
        self.overlay_status_banner.configure(text=self.current_announcement)

        phrase = self.format_number_phrase(num)
        if self.first_draw_after_check:
            phrase = f"Your next number is, {phrase}"
            self.first_draw_after_check = False

        if total_drawn == 5 and not self.has_paused_once and self.draw_sequence:
            self.paused_mode = True
            self.has_paused_once = True
            self.draw_btn.configure(
                text="PAUSED (CHECKING 5 NUMBERS...)",
                fg_color="#F59E0B",
                hover_color="#D97706"
            )
            self.speak(phrase, speech_rate=140, post_delay=0.5, on_complete=self.read_first_five_sequence)
        else:
            self.speak(phrase, speech_rate=140)

        if not self.draw_sequence:
            self.current_label.configure(
                text="END",
                font=ctk.CTkFont(size=180, weight="bold"),
                text_color="#EF4444"
            )
            self.render_3d_text_on_canvas("END", front_color="#EF4444")
            self.draw_btn.configure(text="GAME OVER", state="disabled", fg_color="#475569")

    def init_game_state(self):
        clear_speech_queue()
        self.draw_sequence = list(range(1, 91))
        random.shuffle(self.draw_sequence)
        self.drawn_numbers = set()
        self.first_five_drawn = []
        self.paused_mode = False
        self.is_busy_speaking = False
        self.has_paused_once = False
        self.first_draw_after_check = False
        self.game_mode_selected = False
        self.current_announcement = ""

    def load_splash_image(self):
        img_path = resource_path("welcome.png")
        if os.path.exists(img_path):
            try:
                self.raw_splash_image = Image.open(img_path)
            except Exception:
                self.raw_splash_image = None
        else:
            self.raw_splash_image = None
        self.redraw_splash_canvas()

    def redraw_splash_canvas(self, event=None):
        self.splash_canvas.delete("all")
        w = self.splash_canvas.winfo_width()
        h = self.splash_canvas.winfo_height()
        if w <= 1:
            w = self.winfo_screenwidth()
        if h <= 1:
            h = self.winfo_screenheight()

        cx, cy = w // 2, h // 2

        if self.raw_splash_image:
            try:
                img_w, img_h = self.raw_splash_image.size
                ratio = max(w / img_w, h / img_h)
                new_w = max(1, int(img_w * ratio))
                new_h = max(1, int(img_h * ratio))

                resized_img = self.raw_splash_image.resize((new_w, new_h), Image.Resampling.LANCZOS)
                
                left = (new_w - w) // 2
                top = (new_h - h) // 2
                cropped_img = resized_img.crop((left, top, left + w, top + h))

                self.splash_image_tk = ImageTk.PhotoImage(cropped_img)
                self.splash_canvas.create_image(cx, cy, image=self.splash_image_tk, anchor="center")
            except Exception:
                self.splash_canvas.create_text(
                    cx, cy,
                    text="BINGO CALLER\n\nPRESS [ TAB ] OR CLICK TO START",
                    font=("Arial", 48, "bold"),
                    fill="#00F5FF",
                    justify="center"
                )
        else:
            self.splash_canvas.create_text(
                cx, cy,
                text="BINGO CALLER\n\nPRESS [ TAB ] OR CLICK TO START",
                font=("Arial", 48, "bold"),
                fill="#00F5FF",
                justify="center"
            )

    def handle_enter(self, event=None):
        if not self.splash_active and not self.paused_mode:
            self.draw_number()

    def handle_space(self, event=None):
        if not self.splash_active:
            self.esc_count = 0
            self.reset_count = 0
            self.unpause_game()

    def handle_reset(self, event=None):
        if self.splash_active or not self.ui_built:
            return
        self.esc_count = 0
        self.reset_count += 1

        if self.reset_count == 1:
            self.draw_btn.configure(text="PRESS 'R' 2 MORE TIME(S) TO RESET", fg_color="#EF4444", hover_color="#DC2626")
            return
        if self.reset_count == 2:
            self.draw_btn.configure(text="PRESS 'R' 1 MORE TIME TO RESET", fg_color="#EF4444", hover_color="#DC2626")
            self.speak("Game resetting", speech_rate=140)
            return

        self.reset_count = 0
        self.init_game_state()
        self.title_label.configure(text="PRESS 'L', 'F', OR 'C' TO SELECT GAME TYPE", text_color="#F59E0B")
        self.overlay_status_banner.configure(text="")
        self.current_label.configure(text="--", font=ctk.CTkFont(size=380, weight="bold"), text_color="#64748B")
        self.overlay_counter_label.configure(text="NUMBERS CALLED: 0")
        self.card_display.configure(border_width=0)
        self.counter_label.configure(text="0 / 90")
        self.draw_btn.configure(text="SELECT GAME TYPE FIRST [L, F, C]", state="normal", fg_color="#475569", hover_color="#334155")
        for tile in self.number_tiles.values():
            tile.configure(fg_color="#334155", text_color="#64748B")

        self.toggle_view(show_overlay=False)
        self.render_3d_text_on_canvas("--", front_color="#64748B")

    def handle_x_key(self, event=None):
        if not self.splash_active and len(self.first_five_drawn) == 5 and not self.is_busy_speaking:
            self.read_first_five_sequence()

    def handle_d_key(self, event=None):
        if not self.splash_active and not self.is_busy_speaking:
            self.recall_all_numbers()

    def handle_toggle_view(self, event=None):
        if not self.splash_active:
            self.toggle_view()

    def handle_escape(self, event=None):
        self.reset_count = 0
        self.esc_count += 1
        if self.esc_count >= 3:
            self.destroy()

    def build_main_ui(self):
        if self.ui_built:
            return

        self.configure(fg_color="#0F172A")
        self.base_container = ctk.CTkFrame(self, fg_color="transparent")

        self.top_bar = ctk.CTkFrame(self.base_container, fg_color="transparent")
        self.top_bar.pack(pady=(20, 10), padx=50, fill="x")

        self.title_label = ctk.CTkLabel(
            self.top_bar,
            text="PRESS 'L', 'F', OR 'C' TO SELECT GAME TYPE",
            font=ctk.CTkFont(size=24, weight="bold"),
            text_color="#F59E0B"
        )
        self.title_label.pack(side="left")

        self.right_controls_frame = ctk.CTkFrame(self.top_bar, fg_color="transparent")
        self.right_controls_frame.pack(side="right", padx=(10, 0))

        self.draw_btn = ctk.CTkButton(
            self.right_controls_frame,
            text="SELECT GAME TYPE FIRST [L, F, C]",
            font=ctk.CTkFont(size=20, weight="bold"),
            fg_color="#475569",
            hover_color="#334155",
            height=60,
            width=380,
            corner_radius=14,
            command=self.draw_number
        )
        self.draw_btn.pack(side="right", padx=(15, 0))

        self.speech_checkbox = ctk.CTkCheckBox(
            self.right_controls_frame,
            text="SPEECH",
            variable=self.speech_enabled_var,
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#94A3B8",
            fg_color="#10B981",
            hover_color="#059669",
            border_color="#475569",
            corner_radius=6
        )
        self.speech_checkbox.pack(side="right", padx=(15, 0))

        self.voice_dropdown = ctk.CTkOptionMenu(
            self.right_controls_frame,
            values=self.available_voices,
            variable=self.selected_voice_var,
            command=self.on_voice_changed,
            font=ctk.CTkFont(size=14, weight="bold"),
            dropdown_font=ctk.CTkFont(size=13),
            width=220,
            height=40,
            fg_color="#334155",
            button_color="#475569",
            button_hover_color="#64748B",
            dropdown_fg_color="#1E293B"
        )
        self.voice_dropdown.pack(side="right")

        self.main_container = ctk.CTkFrame(self.base_container, fg_color="transparent")
        self.main_container.pack(pady=10, padx=20, fill="both", expand=True)

        self.display_panel = ctk.CTkFrame(
            self.main_container,
            fg_color="#1E293B",
            corner_radius=24,
            border_width=2,
            border_color="#334155",
            width=500
        )
        self.display_panel.pack(side="left", fill="y", expand=False, padx=(0, 10), pady=10)
        self.display_panel.pack_propagate(False)

        self.card_display = ctk.CTkFrame(
            self.display_panel,
            fg_color="#0F172A",
            corner_radius=20
        )
        self.card_display.pack(fill="both", expand=True, pady=(15, 8), padx=15)

        self.current_label = ctk.CTkLabel(
            self.card_display,
            text="--",
            font=ctk.CTkFont(size=380, weight="bold"),
            text_color="#64748B"
        )
        self.current_label.pack(expand=True, fill="both")

        self.counter_card = ctk.CTkFrame(
            self.display_panel,
            fg_color="#0F172A",
            corner_radius=20,
            height=140
        )
        self.counter_card.pack(fill="x", pady=(0, 15), padx=15)
        self.counter_card.pack_propagate(False)

        self.counter_title = ctk.CTkLabel(
            self.counter_card,
            text="NUMBERS CALLED",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color="#94A3B8"
        )
        self.counter_title.pack(pady=(10, 0))

        self.counter_label = ctk.CTkLabel(
            self.counter_card,
            text="0 / 90",
            font=ctk.CTkFont(size=72, weight="bold"),
            text_color="#38BDF8"
        )
        self.counter_label.pack(expand=True)

        self.grid_frame = ctk.CTkFrame(self.main_container, fg_color="#1E293B", corner_radius=24)
        self.grid_frame.pack(side="right", fill="both", expand=True, pady=10)

        self.grid_container = ctk.CTkFrame(self.grid_frame, fg_color="transparent")
        self.grid_container.pack(expand=True, fill="both", padx=15, pady=15)

        for r in range(9):
            self.grid_container.rowconfigure(r, weight=1)
        for c in range(10):
            self.grid_container.columnconfigure(c, weight=1)

        self.number_tiles = {}
        font_style = ctk.CTkFont(size=54, weight="bold")

        for num in range(1, 91):
            row, col = divmod(num - 1, 10)
            lbl = ctk.CTkLabel(
                self.grid_container,
                text=str(num),
                font=font_style,
                corner_radius=8,
                fg_color="#334155",
                text_color="#64748B"
            )
            lbl.grid(row=row, column=col, padx=3, pady=3, sticky="nsew")
            self.number_tiles[num] = lbl

        self.overlay_frame = ctk.CTkFrame(self, fg_color="#0B0F19")
        self.overlay_counter_label = ctk.CTkLabel(
            self.overlay_frame,
            text="NUMBERS CALLED: 0",
            font=ctk.CTkFont(size=64, weight="bold"),
            text_color="#94A3B8"
        )
        self.overlay_counter_label.pack(pady=(20, 0))

        self.canvas_3d = tk.Canvas(self.overlay_frame, bg="#0B0F19", highlightthickness=0, bd=0)
        self.canvas_3d.pack(expand=True, fill="both")

        self.overlay_status_banner = ctk.CTkLabel(
            self.overlay_frame,
            text="",
            font=ctk.CTkFont(size=48, weight="bold"),
            text_color="#00F5FF"
        )
        self.overlay_status_banner.pack(pady=(0, 10))

        self.overlay_hint_label = ctk.CTkLabel(
            self.overlay_frame,
            text="[ENTER] NEXT NUMBER    |    [T] TOGGLE GRID BOARD",
            font=ctk.CTkFont(size=28, weight="bold"),
            text_color="#475569"
        )
        self.overlay_hint_label.pack(pady=(0, 30))

        self.ui_built = True

    def render_3d_text_on_canvas(self, text: str, front_color: str, depth: int = 20):
        if not self.ui_built:
            return

        self.last_rendered_text = text
        self.last_rendered_color = front_color

        w = self.canvas_3d.winfo_width()
        h = self.canvas_3d.winfo_height()

        if w <= 1 or h <= 1:
            w = max(self.winfo_screenwidth(), 800)
            h = max(self.winfo_screenheight() - 200, 600)

        cx, cy = w // 2, h // 2
        font_size = 540 if len(text) <= 2 else 380
        font_tuple = ("Arial", font_size, "bold")

        try:
            self.canvas_3d.delete("all")
            self.canvas_3d.create_text(cx + depth + 10, cy + depth + 10, text=text, font=font_tuple, fill="#020617")
            for i in range(depth, 0, -2):
                self.canvas_3d.create_text(cx + i, cy + i, text=text, font=font_tuple, fill="#1E293B")
            self.canvas_3d.create_text(cx, cy, text=text, font=font_tuple, fill=front_color)
        except Exception:
            pass

    def speak(self, phrase: str, post_delay: float = 0.0, speech_rate: int = 140, on_complete=None):
        if self.speech_enabled_var.get():
            current_voice = self.selected_voice_var.get()
            speech_queue.put((phrase, post_delay, speech_rate, on_complete, self, current_voice))
        elif on_complete:
            self.after(10, on_complete)

    def unpause_game(self):
        self.is_busy_speaking = False
        if self.paused_mode and self.draw_sequence:
            self.paused_mode = False
            if self.ui_built:
                self.draw_btn.configure(
                    text="DRAW NUMBER [ENTER]",
                    fg_color="#10B981",
                    hover_color="#059669"
                )

    def set_game_mode(self, mode: str):
        if self.splash_active or self.is_busy_speaking:
            return
        modes = {
            "Line": "This game is for a Line",
            "Full House": "This game is for a Full House",
            "Carry On": "We will now carry on for a Full House"
        }
        if mode not in modes:
            return

        display_text = modes[mode]
        self.game_mode_selected = True
        self.current_announcement = display_text.upper()

        if self.ui_built:
            self.title_label.configure(text=self.current_announcement, text_color="#38BDF8")
            self.overlay_status_banner.configure(text=self.current_announcement)
            self.draw_btn.configure(
                text="DRAW NUMBER [ENTER]",
                fg_color="#10B981",
                hover_color="#059669"
            )
            self.overlay_counter_label.configure(text=f"NUMBERS CALLED: {len(self.drawn_numbers)} / 90")

        display_num = str(len(self.drawn_numbers)) if self.drawn_numbers else "--"
        self.toggle_view(show_overlay=True)
        self.render_3d_text_on_canvas(display_num, front_color="#64748B")
        self.speak(display_text, speech_rate=140)

    def format_number_phrase(self, num: int, simple_number_only: bool = False) -> str:
        double_digit_words = {
            22: "twos", 33: "threes", 44: "fours",
            55: "fives", 66: "sixes", 77: "sevens", 88: "eights"
        }
        if num > 10 and num % 10 == 0:
            return f"{num // 10} zero blind {num}"
        if num in double_digit_words:
            return f"All the {double_digit_words[num]}, {num}"
        if num < 10:
            return f"On its own number, {num}"
        if simple_number_only:
            return str(num)
        num_str = str(num)
        return f"{num_str[0]} and {num_str[1]}, {num}"

    def read_first_five_sequence(self):
        self.is_busy_speaking = True
        self.toggle_view(show_overlay=False)
        sorted_first_five = sorted(self.first_five_drawn)
        if not self.speech_enabled_var.get():
            self.after(1000, self.unpause_game)
            return

        self.speak("Your five number check is", post_delay=0.4, speech_rate=140)
        for i, num in enumerate(sorted_first_five):
            phrase = self.format_number_phrase(num, simple_number_only=True)
            is_last = (i == len(sorted_first_five) - 1)
            cb = self.unpause_game_and_flag if is_last else None
            self.speak(phrase, post_delay=0.3, speech_rate=140, on_complete=cb)

    def unpause_game_and_flag(self):
        self.unpause_game()
        self.first_draw_after_check = True

    def recall_all_numbers(self):
        if self.splash_active or not self.drawn_numbers or self.is_busy_speaking:
            return
        self.is_busy_speaking = True
        self.paused_mode = True
        if self.ui_built:
            self.draw_btn.configure(
                text="RECALLING ALL NUMBERS...",
                fg_color="#F59E0B",
                hover_color="#D97706"
            )
        self.toggle_view(show_overlay=False)
        sorted_drawn = sorted(self.drawn_numbers)

        if not self.speech_enabled_var.get():
            self.after(1000, self.unpause_game)
            return

        self.speak("Recalling all numbers", post_delay=0.4, speech_rate=140)
        for i, num in enumerate(sorted_drawn):
            phrase = self.format_number_phrase(num, simple_number_only=True)
            is_last = (i == len(sorted_drawn) - 1)
            cb = self.unpause_game if is_last else None
            self.speak(phrase, post_delay=0.3, speech_rate=140, on_complete=cb)

    def toggle_view(self, show_overlay: bool = None):
        if self.splash_active or not self.ui_built:
            return
        self.fullscreen_mode = (not self.fullscreen_mode) if show_overlay is None else show_overlay
        if self.fullscreen_mode:
            self.base_container.pack_forget()
            self.overlay_frame.pack(fill="both", expand=True)
            self.after(
                50,
                lambda: self.render_3d_text_on_canvas(self.last_rendered_text, self.last_rendered_color)
            )
        else:
            self.overlay_frame.pack_forget()
            self.base_container.pack(fill="both", expand=True)

    def destroy(self):
        try:
            if os.path.exists(LOCK_FILE):
                os.remove(LOCK_FILE)
        except Exception:
            pass
        super().destroy()


if __name__ == "__main__":
    app = ModernBingoApp()
    app.mainloop()