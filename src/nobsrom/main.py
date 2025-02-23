import curses
import os
import subprocess
import time
from enum import Enum

import yaml
from platformdirs import user_config_path

os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "hide"
os.environ["SDL_AUDIODRIVER"] = "dummy"

import pygame.event
import pygame.joystick


class Colors(Enum):
    HEADER = 1
    SELECTED = 2
    FAVORITE = 3
    NORMAL = 4
    HIGHLIGHT = 5
    STATUS_BAR = 6


class EmulatorLauncher:
    def __init__(self):
        # config
        self.app_name = "nobsrom"
        self.vendor_name = "D221"
        self.config_dir = user_config_path(
            self.app_name, self.vendor_name, ensure_exists=True
        )
        # Set default file paths if not specified
        self.config_file = self.config_dir / "config.yaml"
        self.favorites_file = self.config_dir / "favorites.yaml"
        self.config = self.load_config()
        self.favorites = self.load_favorites()

        self.roms = self.get_roms()
        self.all_roms = self.combine_all_roms(self.roms)
        self.selected_system = 0
        self.selected_rom = 0
        self.total_roms = 0
        self.current_rom_index = 0
        self.system_window = None
        self.rom_window = None
        self.emulator_process = None
        self.focus = "systems"
        self.filter_string = ""
        self.filtered_roms = {}
        self.last_selection_change_time = 0
        self.mode = "navigate"
        self.view_mode = "favorites" if self.favorites else "systems"
        self.joystick = None
        self.first_axis_event = {"up": 0, "down": 0, "left": 0, "right": 0}
        self.last_axis_event = {"up": 0, "down": 0, "left": 0, "right": 0}
        self.first_hat_event = {"up": 0, "down": 0, "left": 0, "right": 0}
        self.last_hat_event = {"up": 0, "down": 0, "left": 0, "right": 0}

    def load_config(self):
        """Load config from platform-specific location"""
        try:
            if not self.config_file.exists():
                self.create_default_config()

            with open(self.config_file, "r") as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            print(f"Error loading config: {e}")
            return self.create_default_config()

    def create_default_config(self):
        """Create default configuration if none exists"""
        default_config = {
            "systems": {
                "NES": {
                    "emulator_path": "retroarch",
                    "launch_arguments": "-L cores/fceumm_libretro.dll {rom_path}",
                    "paths": ["~/ROMs/NES"],
                }
            }
        }
        self.save_config(default_config)
        return default_config

    def save_config(self, config=None):
        """Save configuration to platform-specific location"""
        config = config or self.config
        with open(self.config_file, "w") as f:
            yaml.dump(config, f, default_flow_style=False)

    def load_favorites(self):
        """Load favorites from platform-specific location"""
        try:
            if not self.favorites_file.exists():
                return {}

            with open(self.favorites_file, "r") as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            print(f"Error loading favorites: {e}")
            return {}

    def save_favorites(self):
        """Save favorites to platform-specific location"""
        with open(self.favorites_file, "w") as f:
            yaml.dump(self.favorites, f)

    def init_colors(self):
        """Initialize color pairs for the UI"""
        curses.start_color()
        curses.use_default_colors()

        # Define color pairs
        curses.init_pair(Colors.HEADER.value, curses.COLOR_WHITE, curses.COLOR_BLUE)
        curses.init_pair(Colors.SELECTED.value, curses.COLOR_BLACK, curses.COLOR_WHITE)
        curses.init_pair(Colors.FAVORITE.value, curses.COLOR_YELLOW, -1)
        curses.init_pair(Colors.NORMAL.value, curses.COLOR_WHITE, -1)
        curses.init_pair(Colors.HIGHLIGHT.value, curses.COLOR_CYAN, -1)
        curses.init_pair(
            Colors.STATUS_BAR.value, curses.COLOR_BLACK, curses.COLOR_WHITE
        )

    def draw_borders(self):
        """Draw borders around windows"""
        height, width = self.stdscr.getmaxyx()

        # Draw system window border
        self.system_window.box()
        self.system_window.addstr(
            0, 2, "[ Systems ]", curses.color_pair(Colors.HEADER.value)
        )

        # Draw ROM window border
        self.rom_window.box()
        self.rom_window.addstr(
            0, 2, "[ Games ]", curses.color_pair(Colors.HEADER.value)
        )

    def combine_all_roms(self, roms):
        """Combines all ROMs from all systems into a list of (system, rom_path) tuples."""
        all_roms = []
        for system, system_roms in roms.items():
            for rom in system_roms:
                all_roms.append((system, rom))
        return sorted(
            all_roms, key=lambda x: os.path.basename(x[1]).lower()
        )  # Sort by ROM name

    def get_roms(self):
        """Gets a list of ROMs from the configured paths."""
        roms = {}
        for system, config in self.config["systems"].items():
            roms[system] = []
            for path in config.get("paths", []):
                if os.path.isdir(path):
                    roms[system].extend(
                        [
                            os.path.join(path, f)
                            for f in os.listdir(path)
                            if not f.startswith(".")
                        ]
                    )
                else:
                    print(f"Warning: Invalid ROM path for {system}: {path}")
        return roms

    def format_size(self, size):
        """Formats a file size (in bytes) into a human-readable string."""
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size < 1024:
                if unit == "B":
                    return f" {int(size)}{unit}"
                else:
                    return f" {size:.1f}{unit}"
            size /= 1024
        return f"{size:.1f}PB"

    def draw_system_window(self):
        """Draws the system selection window with enhanced visuals"""
        self.system_window.clear()
        self.draw_borders()
        y, x = 1, 2  # Start below the border

        # Favorites view with icon
        favorites_count = sum(len(roms) for roms in self.favorites.values())
        fav_text = f"★ Favorites ({favorites_count})"
        if self.view_mode == "favorites":
            self.system_window.addstr(
                y, x, fav_text, curses.color_pair(Colors.SELECTED.value)
            )
        else:
            self.system_window.addstr(
                y, x, fav_text, curses.color_pair(Colors.FAVORITE.value)
            )
        y += 1

        # ALL category with icon
        all_text = f"◆ All ({len(self.all_roms)})"
        if self.view_mode == "all":
            self.system_window.addstr(
                y, x, all_text, curses.color_pair(Colors.SELECTED.value)
            )
        else:
            self.system_window.addstr(
                y, x, all_text, curses.color_pair(Colors.NORMAL.value)
            )
        y += 1

        # Separator with nice pattern
        self.system_window.addstr(y, x, "─" * (self.system_window.getmaxyx()[1] - 4))
        y += 1

        # Systems with ROM counts and icons
        systems = list(self.roms.keys())
        for i, system in enumerate(systems):
            count = len(self.roms[system])
            system_text = f"▸ {system} ({count})"
            if self.view_mode == "systems" and i == self.selected_system:
                self.system_window.addstr(
                    y, x, system_text, curses.color_pair(Colors.SELECTED.value)
                )
            else:
                self.system_window.addstr(
                    y, x, system_text, curses.color_pair(Colors.NORMAL.value)
                )
            y += 1

        self.system_window.refresh()

    def draw_rom_window(self):
        """Draws the ROM selection window with enhanced visuals"""
        self.rom_window.clear()
        self.draw_borders()

        rom_list = []
        if self.view_mode == "systems":
            systems = list(self.roms.keys())
            if systems:
                selected_system_name = systems[self.selected_system]
                rom_list = self.filtered_roms.get(selected_system_name, [])
        elif self.view_mode == "all":
            rom_list = self.filtered_roms.get("all", [])
        elif self.view_mode == "favorites":
            rom_list = self.filtered_roms.get("favorites", [])

        viewable_height = self.rom_window.getmaxyx()[0] - 1  # Account for borders
        num_roms = len(rom_list)

        # Update counters
        self.total_roms = num_roms
        self.current_rom_index = self.selected_rom + 1 if num_roms > 0 else 0

        # Calculate scrolling
        if num_roms <= viewable_height:
            top_index = 0
        else:
            if self.selected_rom == 0:
                top_index = 0
            else:
                top_index = self.selected_rom - (viewable_height // 2)
            top_index = max(0, min(top_index, num_roms - viewable_height + 1))

        for i, rom_data in enumerate(rom_list[top_index : top_index + viewable_height]):
            y = i + 1  # Start below the border
            if y >= viewable_height:
                break

            # Determine ROM display information
            if self.view_mode in ["favorites", "all"]:
                system, rom_path = rom_data
                rom_name = f"[{system}] {os.path.basename(rom_path)}"
            else:
                rom_path = rom_data
                rom_name = os.path.basename(rom_path)

            # Add favorite star if needed
            if self.is_favorite(rom_path):
                rom_name = "★ " + rom_name
            else:
                rom_name = "  " + rom_name

            # Get file size
            try:
                size = os.path.getsize(rom_path)
                file_size_str = self.format_size(size)
            except Exception:
                file_size_str = "N/A"

            # Calculate display positions
            win_width = self.rom_window.getmaxyx()[1]
            size_width = len(file_size_str) + 2
            name_width = win_width - size_width - 2

            # Determine display attributes
            is_selected = (top_index + i == self.selected_rom) and (
                self.focus == "roms"
            )
            if is_selected:
                attr = curses.color_pair(Colors.SELECTED.value)
            elif self.is_favorite(rom_path):
                attr = curses.color_pair(Colors.FAVORITE.value)
            else:
                attr = curses.color_pair(Colors.NORMAL.value)

            # Handle scrolling for long names
            if is_selected and len(rom_name) > name_width:
                scroll_speed = 5
                current_time = time.time()
                time_since_selection = current_time - self.last_selection_change_time
                scroll_offset = int(time_since_selection * scroll_speed)
                scroll_offset = scroll_offset % (len(rom_name) + 5)
                display_name = rom_name + "     " + rom_name
                display_name = display_name[scroll_offset : scroll_offset + name_width]
            else:
                display_name = rom_name[:name_width]

            # Draw the ROM entry
            self.rom_window.addstr(y, 2, display_name.ljust(name_width), attr)
            self.rom_window.addstr(y, name_width + 2, file_size_str, attr)

        self.rom_window.refresh()

    def launch_rom(self, emulator_path, launch_arguments, rom_path, start_in_directory):
        """Launches the emulator with the chosen ROM."""
        command = [emulator_path]
        if launch_arguments:
            args = launch_arguments.split()
            for i, arg in enumerate(args):
                if "{rom_path}" in arg:
                    args[i] = arg.replace("{rom_path}", rom_path)
            command.extend(args)

        # print(f"Launching: {' '.join(command)}")
        try:
            self.emulator_process = subprocess.Popen(
                command, cwd=start_in_directory
            )  # Set working directory
        except subprocess.CalledProcessError as e:
            print(f"Error launching emulator: {e}")
        except FileNotFoundError:
            print(f"Emulator not found at: {emulator_path}")

    def update_filtered_roms(self):
        """Updates the list of filtered ROMs based on the filter string and view mode."""
        if not self.filter_string:
            if self.view_mode == "systems":
                self.filtered_roms = self.roms
            elif self.view_mode == "all":
                self.filtered_roms = {"all": self.all_roms}
            elif self.view_mode == "favorites":
                self.filtered_roms = {"favorites": self.get_favorite_roms_with_system()}
            return

        self.filtered_roms = {}

        if self.view_mode == "systems":
            for system, roms in self.roms.items():
                self.filtered_roms[system] = [
                    rom
                    for rom in roms
                    if self.filter_string.lower() in os.path.basename(rom).lower()
                ]
        elif self.view_mode == "all":
            self.filtered_roms["all"] = [
                (system, rom)
                for system, rom in self.all_roms
                if self.filter_string.lower() in os.path.basename(rom).lower()
            ]
        elif self.view_mode == "favorites":
            favorite_roms = self.get_favorite_roms_with_system()
            self.filtered_roms["favorites"] = [
                rom_data
                for rom_data in favorite_roms
                if self.filter_string.lower() in os.path.basename(rom_data[1]).lower()
            ]

    def get_favorite_roms_with_system(self):
        """Returns a list of favorite ROMs with their system names."""
        favorite_roms = []
        for system, roms in self.favorites.items():
            for rom in roms:
                favorite_roms.append((system, rom))
        return favorite_roms

    def toggle_favorite(self):
        """Toggles the favorite status of the currently selected ROM."""
        current_rom_index = self.selected_rom  # Store the current ROM index

        if self.view_mode == "systems":
            systems = list(self.roms.keys())
            if systems:
                selected_system_name = systems[self.selected_system]
                rom_list = self.filtered_roms.get(selected_system_name, [])
                if rom_list:
                    selected_rom_path = rom_list[current_rom_index]  # Use stored index

                    if selected_system_name not in self.favorites:
                        self.favorites[selected_system_name] = []

                    if selected_rom_path in self.favorites[selected_system_name]:
                        self.favorites[selected_system_name].remove(selected_rom_path)
                    else:
                        self.favorites[selected_system_name].append(selected_rom_path)

                    if not self.favorites[selected_system_name]:
                        del self.favorites[selected_system_name]

                    self.save_favorites()
        elif self.view_mode == "all":
            rom_data = self.filtered_roms.get("all", [])[
                current_rom_index
            ]  # Use stored index
            system, rom_path = rom_data
            self.toggle_favorite_by_system_and_path(system, rom_path)
        elif self.view_mode == "favorites":
            rom_data = self.filtered_roms.get("favorites", [])[
                current_rom_index
            ]  # Use stored index
            system, rom_path = rom_data
            self.toggle_favorite_by_system_and_path(system, rom_path)

        self.update_filtered_roms()
        self.draw_rom_window()

        # Restore the ROM selection position
        if self.view_mode == "systems":
            rom_list = self.filtered_roms.get(systems[self.selected_system], [])
        elif self.view_mode == "all":
            rom_list = self.filtered_roms.get("all", [])
        elif self.view_mode == "favorites":
            rom_list = self.filtered_roms.get("favorites", [])

        # Ensure the stored index is within bounds
        self.selected_rom = min(current_rom_index, len(rom_list) - 1)
        self.selected_rom = max(self.selected_rom, 0)  # Ensure it's not negative

    def toggle_favorite_by_system_and_path(self, system, rom_path):
        """Helper function to toggle favorite status using system and path."""
        if system not in self.favorites:
            self.favorites[system] = []

        if rom_path in self.favorites[system]:
            self.favorites[system].remove(rom_path)
            if not self.favorites[system]:
                del self.favorites[system]
        else:
            self.favorites[system].append(rom_path)

        self.save_favorites()
        self.update_filtered_roms()
        self.draw_rom_window()

    def is_favorite(self, rom_path):
        """Checks if a ROM is in the favorites."""
        for system, favorites in self.favorites.items():
            if rom_path in favorites:
                return True
        return False

    def handle_input(self, key):
        """Handles user input."""
        prev_selected_rom = self.selected_rom
        prev_view_mode = self.view_mode
        prev_selected_system = self.selected_system

        systems = list(self.roms.keys())
        num_systems = len(systems)

        rom_list = []
        if self.view_mode == "systems" and systems:
            selected_system_name = systems[self.selected_system]
            rom_list = self.filtered_roms.get(selected_system_name, [])
        elif self.view_mode == "all":
            rom_list = self.filtered_roms.get("all", [])
        elif self.view_mode == "favorites":
            rom_list = self.filtered_roms.get("favorites", [])

        num_roms = len(rom_list)

        if self.mode == "filter":
            if key == 27:  # Escape key
                self.mode = "navigate"
                self.filter_string = ""
                self.update_filtered_roms()
                self.selected_rom = 0
            elif key == 10:  # Enter key in filter mode
                self.launch_selected_rom(systems, rom_list)
            elif key == curses.KEY_BACKSPACE or key == 127 or key == 8:
                if self.filter_string:
                    self.filter_string = self.filter_string[:-1]
                    self.update_filtered_roms()
                    self.selected_rom = 0
            elif key == curses.KEY_UP:
                if self.selected_rom > 0:
                    self.selected_rom -= 1
            elif key == curses.KEY_DOWN:
                if self.selected_rom < num_roms - 1:
                    self.selected_rom += 1
            elif key == curses.KEY_F2:
                if self.focus == "roms":
                    self.toggle_favorite()
            elif key >= 32 and key <= 126:  # Printable characters
                self.filter_string += chr(key)
                self.update_filtered_roms()
                self.selected_rom = 0
        else:  # Navigate mode
            if key == curses.KEY_UP:
                if self.focus == "roms" and num_roms > 0:
                    self.selected_rom = (self.selected_rom - 1) % num_roms
                elif self.focus == "systems":
                    if self.view_mode == "favorites":
                        self.view_mode = "systems"
                        self.selected_system = num_systems - 1
                        self.selected_rom = 0
                        self.update_filtered_roms()
                    elif self.view_mode == "all" and num_systems > 0:
                        self.view_mode = "favorites"
                        self.selected_rom = 0
                        self.update_filtered_roms()
                    elif self.view_mode == "systems" and self.selected_system == 0:
                        self.view_mode = "all"
                        self.selected_rom = 0
                        self.update_filtered_roms()
                    elif self.view_mode == "systems" and self.selected_system > 0:
                        self.selected_system -= 1
                        self.selected_rom = 0
            elif key == curses.KEY_DOWN:
                if self.focus == "roms" and num_roms > 0:
                    self.selected_rom = (self.selected_rom + 1) % num_roms
                elif self.focus == "systems":
                    if self.view_mode == "favorites":
                        self.view_mode = "all"
                        self.selected_rom = 0
                        self.update_filtered_roms()
                    elif self.view_mode == "all" and num_systems > 0:
                        self.view_mode = "systems"
                        self.selected_system = 0
                        self.selected_rom = 0
                        self.update_filtered_roms()
                    elif (
                        self.view_mode == "systems"
                        and self.selected_system < num_systems - 1
                    ):
                        self.selected_system += 1
                        self.selected_rom = 0
                        self.update_filtered_roms()
                    elif (
                        self.view_mode == "systems"
                        and self.selected_system == num_systems - 1
                    ):
                        self.view_mode = "favorites"
                        self.selected_rom = 0
                        self.update_filtered_roms()
            elif key == curses.KEY_LEFT:
                self.focus = "systems"
            elif key == curses.KEY_RIGHT:
                self.focus = "roms"
            elif key == ord("/"):
                self.mode = "filter"
                self.filter_string = ""
                self.update_filtered_roms()
                self.selected_rom = 0
            elif key == 10:  # Enter key in navigate mode
                self.launch_selected_rom(systems, rom_list)
            elif key == curses.KEY_F2:
                if self.focus == "roms":
                    self.toggle_favorite()

            # Update timestamp if any selection state changed
        if (
            prev_selected_rom != self.selected_rom
            or prev_view_mode != self.view_mode
            or prev_selected_system != self.selected_system
        ):
            self.last_selection_change_time = time.time()

        self.draw_rom_window()
        self.draw_system_window()
        self.draw_filter_bar()

    def launch_selected_rom(self, systems, rom_list):
        """Launches the selected ROM if possible."""
        if self.focus == "roms" and self.emulator_process is None and rom_list:
            if self.view_mode == "systems":
                system_config = self.config["systems"].get(
                    systems[self.selected_system]
                )
                if system_config and rom_list:
                    start_in_directory = system_config.get("start_in")
                    self.launch_rom(
                        system_config["emulator_path"],
                        system_config["launch_arguments"],
                        rom_list[self.selected_rom],
                        start_in_directory,
                    )
            elif self.view_mode in ["favorites", "all"] and rom_list:
                system, rom_path = rom_list[self.selected_rom]
                system_config = self.config["systems"].get(system)
                if system_config:
                    start_in_directory = system_config.get("start_in")
                    self.launch_rom(
                        system_config["emulator_path"],
                        system_config["launch_arguments"],
                        rom_path,
                        start_in_directory,
                    )

            # Clear filter and update display after launching
            self.mode = "navigate"
            self.filter_string = ""
            self.update_filtered_roms()
            self.selected_rom = 0

    def draw_filter_bar(self):
        """Draws an enhanced filter/status bar"""
        height, width = self.stdscr.getmaxyx()

        # Clear the status bar
        self.stdscr.move(height - 1, 0)
        self.stdscr.clrtoeol()

        # Set status bar style
        self.stdscr.attron(curses.color_pair(Colors.STATUS_BAR.value))

        current_rom = self.current_rom_index if self.total_roms > 0 else 0
        counter = f" {current_rom}/{self.total_roms}"

        if self.mode == "filter":
            status = f" / {self.filter_string}{counter}"
            help_text = "ESC:Exit │ ENTER/A:Launch │ F2/X:Favorite │ Q/B:Quit"
        else:
            status = f" Ready{counter}"
            help_text = "/:Search │ ENTER/A:Launch │ F2/X:Favorite │ Q/B:Quit"

        # Calculate padding, ensuring we don't exceed the window width
        total_length = len(status) + len(help_text)
        padding = max(0, width - total_length - 1)  # Leave one character at the end

        # Ensure we don't write beyond the last column
        final_text = (status + " " * padding + help_text)[: width - 1]

        # Draw status bar
        self.stdscr.addstr(height - 1, 0, final_text)
        self.stdscr.attroff(curses.color_pair(Colors.STATUS_BAR.value))
        self.stdscr.refresh()

    def main(self, stdscr):
        """Main function to run the launcher with keyboard and gamepad support,
        including auto-repeat with an initial delay for both D-pad and joystick axes."""
        self.stdscr = stdscr
        stdscr.keypad(True)
        curses.curs_set(0)
        self.init_colors()
        stdscr.clear()
        stdscr.refresh()

        # Initialize pygame for gamepad support.
        pygame.init()
        pygame.joystick.init()
        if pygame.joystick.get_count() > 0:
            self.joystick = pygame.joystick.Joystick(0)
            self.joystick.init()
            # print("Controller connected:", self.joystick.get_name())
        else:
            self.joystick = None
            # print("No controller found.")

        stdscr.nodelay(True)

        # Calculate split for windows.
        height, width = stdscr.getmaxyx()
        system_width = width // 4
        rom_width = width - system_width
        self.system_window = curses.newwin(height - 1, system_width, 0, 0)
        self.rom_window = curses.newwin(height - 1, rom_width, 0, system_width)
        self.mode = "navigate"

        self.update_filtered_roms()
        self.draw_system_window()
        self.draw_rom_window()
        self.draw_filter_bar()

        # Timing parameters (in seconds)
        initial_delay = 0.3  # Delay before auto-repeat kicks in
        repeat_interval = 0.04  # Interval between repeats after initial delay

        # Timing parameters for scroll updates
        last_scroll_time = 0
        scroll_interval = 0.1  # 100 milliseconds

        running = True

        while running:
            current_time = time.time()

            if current_time - last_scroll_time >= scroll_interval:
                self.draw_rom_window()
                self.draw_filter_bar()
                last_scroll_time = current_time

            # Process keyboard input.
            key = stdscr.getch()
            if key != -1:
                if key == curses.KEY_RESIZE:
                    # Handle window resize
                    curses.resize_term(*stdscr.getmaxyx())
                    height, width = stdscr.getmaxyx()
                    system_width = width // 4
                    rom_width = width - system_width
                    self.system_window = curses.newwin(height - 1, system_width, 0, 0)
                    self.rom_window = curses.newwin(
                        height - 1, rom_width, 0, system_width
                    )
                    stdscr.clear()
                    curses.curs_set(0)  # Re-hide cursor after resize
                    self.init_colors()  # Re-initialize colors if necessary
                    self.update_filtered_roms()
                    self.draw_system_window()
                    self.draw_rom_window()
                    self.draw_filter_bar()
                elif (
                    key == ord("q")
                    and self.emulator_process is None
                    and self.mode == "navigate"
                ):
                    break
                self.handle_input(key)

            # Process pygame events for button presses.
            for event in pygame.event.get():
                if event.type == pygame.JOYBUTTONDOWN:
                    if event.button == 0:  # Typically A button.
                        self.handle_input(10)  # Enter key.
                    elif event.button == 1:  # Typically B button.
                        running = False
                    elif event.button == 2:  # Example: X button.
                        self.handle_input(curses.KEY_F2)
                # We poll the hat state below for auto-repeat.

            now = time.time()
            if self.joystick is not None:
                # ----- Process D-pad (hat) with initial delay auto-repeat -----
                hat_x, hat_y = self.joystick.get_hat(0)
                # For UP
                if hat_y == 1:
                    if self.first_hat_event["up"] == 0:
                        self.handle_input(curses.KEY_UP)
                        self.first_hat_event["up"] = now
                        self.last_hat_event["up"] = now
                    elif (
                        now - self.first_hat_event["up"] >= initial_delay
                        and now - self.last_hat_event["up"] >= repeat_interval
                    ):
                        self.handle_input(curses.KEY_UP)
                        self.last_hat_event["up"] = now
                else:
                    self.first_hat_event["up"] = 0
                    self.last_hat_event["up"] = 0

                # For DOWN
                if hat_y == -1:
                    if self.first_hat_event["down"] == 0:
                        self.handle_input(curses.KEY_DOWN)
                        self.first_hat_event["down"] = now
                        self.last_hat_event["down"] = now
                    elif (
                        now - self.first_hat_event["down"] >= initial_delay
                        and now - self.last_hat_event["down"] >= repeat_interval
                    ):
                        self.handle_input(curses.KEY_DOWN)
                        self.last_hat_event["down"] = now
                else:
                    self.first_hat_event["down"] = 0
                    self.last_hat_event["down"] = 0

                # For RIGHT
                if hat_x == 1:
                    if self.first_hat_event["right"] == 0:
                        self.handle_input(curses.KEY_RIGHT)
                        self.first_hat_event["right"] = now
                        self.last_hat_event["right"] = now
                    elif (
                        now - self.first_hat_event["right"] >= initial_delay
                        and now - self.last_hat_event["right"] >= repeat_interval
                    ):
                        self.handle_input(curses.KEY_RIGHT)
                        self.last_hat_event["right"] = now
                else:
                    self.first_hat_event["right"] = 0
                    self.last_hat_event["right"] = 0

                # For LEFT
                if hat_x == -1:
                    if self.first_hat_event["left"] == 0:
                        self.handle_input(curses.KEY_LEFT)
                        self.first_hat_event["left"] = now
                        self.last_hat_event["left"] = now
                    elif (
                        now - self.first_hat_event["left"] >= initial_delay
                        and now - self.last_hat_event["left"] >= repeat_interval
                    ):
                        self.handle_input(curses.KEY_LEFT)
                        self.last_hat_event["left"] = now
                else:
                    self.first_hat_event["left"] = 0
                    self.last_hat_event["left"] = 0

                # ----- Process Joystick Axes if D-pad is neutral -----
                if (hat_x, hat_y) == (0, 0):
                    axis_x = self.joystick.get_axis(0)
                    axis_y = self.joystick.get_axis(1)

                    # For UP
                    if axis_y < -0.5:
                        if self.first_axis_event["up"] == 0:
                            self.handle_input(curses.KEY_UP)
                            self.first_axis_event["up"] = now
                            self.last_axis_event["up"] = now
                        elif (
                            now - self.first_axis_event["up"] >= initial_delay
                            and now - self.last_axis_event["up"] >= repeat_interval
                        ):
                            self.handle_input(curses.KEY_UP)
                            self.last_axis_event["up"] = now
                    else:
                        self.first_axis_event["up"] = 0
                        self.last_axis_event["up"] = 0

                    # For DOWN
                    if axis_y > 0.5:
                        if self.first_axis_event["down"] == 0:
                            self.handle_input(curses.KEY_DOWN)
                            self.first_axis_event["down"] = now
                            self.last_axis_event["down"] = now
                        elif (
                            now - self.first_axis_event["down"] >= initial_delay
                            and now - self.last_axis_event["down"] >= repeat_interval
                        ):
                            self.handle_input(curses.KEY_DOWN)
                            self.last_axis_event["down"] = now
                    else:
                        self.first_axis_event["down"] = 0
                        self.last_axis_event["down"] = 0

                    # For LEFT
                    if axis_x < -0.5:
                        if self.first_axis_event["left"] == 0:
                            self.handle_input(curses.KEY_LEFT)
                            self.first_axis_event["left"] = now
                            self.last_axis_event["left"] = now
                        elif (
                            now - self.first_axis_event["left"] >= initial_delay
                            and now - self.last_axis_event["left"] >= repeat_interval
                        ):
                            self.handle_input(curses.KEY_LEFT)
                            self.last_axis_event["left"] = now
                    else:
                        self.first_axis_event["left"] = 0
                        self.last_axis_event["left"] = 0

                    # For RIGHT
                    if axis_x > 0.5:
                        if self.first_axis_event["right"] == 0:
                            self.handle_input(curses.KEY_RIGHT)
                            self.first_axis_event["right"] = now
                            self.last_axis_event["right"] = now
                        elif (
                            now - self.first_axis_event["right"] >= initial_delay
                            and now - self.last_axis_event["right"] >= repeat_interval
                        ):
                            self.handle_input(curses.KEY_RIGHT)
                            self.last_axis_event["right"] = now
                    else:
                        self.first_axis_event["right"] = 0
                        self.last_axis_event["right"] = 0

            # Check if the emulator process has finished.
            if self.emulator_process and self.emulator_process.poll() is not None:
                self.emulator_process = None

            time.sleep(0.01)


if __name__ == "__main__":
    launcher = EmulatorLauncher()
    curses.wrapper(launcher.main)
