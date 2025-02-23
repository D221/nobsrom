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
        """
        Initializes the main application class.
        Attributes:
            app_name (str): The name of the application.
            vendor_name (str): The name of the vendor.
            config_dir (Path): The directory where the configuration files are stored.
            config_file (Path): The path to the configuration file.
            favorites_file (Path): The path to the favorites file.
            config (dict): The loaded configuration data.
            favorites (list): The loaded list of favorite ROMs.
            roms (dict): The dictionary of available ROMs.
            all_roms (list): The combined list of all ROMs.
            selected_system (int): The index of the currently selected system.
            selected_rom (int): The index of the currently selected ROM.
            total_roms (int): The total number of ROMs.
            current_rom_index (int): The index of the current ROM.
            system_window (Any): The window displaying the systems.
            rom_window (Any): The window displaying the ROMs.
            emulator_process (Any): The process running the emulator.
            focus (str): The current focus, either "systems" or "roms".
            filter_string (str): The current filter string for ROMs.
            filtered_roms (dict): The dictionary of filtered ROMs.
            last_selection_change_time (float): The timestamp of the last selection change.
            mode (str): The current mode of the application, e.g., "navigate".
            view_mode (str): The current view mode, either "favorites" or "systems".
            joystick (Any): The joystick input device.
            first_axis_event (dict): The timestamp of the first axis event for each direction.
            last_axis_event (dict): The timestamp of the last axis event for each direction.
            first_hat_event (dict): The timestamp of the first hat event for each direction.
            last_hat_event (dict): The timestamp of the last hat event for each direction.
        """
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
        """
        Load the configuration from a platform-specific location.
        This method attempts to load the configuration from a file specified by
        `self.config_file`. If the file does not exist, it creates a default
        configuration file. If an error occurs during loading, it prints an error
        message and returns the default configuration.
        Returns:
            dict: The loaded configuration as a dictionary. If the configuration
            file does not exist or an error occurs, returns the default configuration.
        """
        try:
            if not self.config_file.exists():
                self.create_default_config()

            with open(self.config_file, "r") as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            print(f"Error loading config: {e}")
            return self.create_default_config()

    def create_default_config(self):
        """
        Creates and saves a default configuration for the ROM launcher.

        The default configuration includes settings for the NES system, specifying
        the emulator path, launch arguments, and ROM paths.

        Returns:
            dict: The default configuration dictionary.
        """
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
        """
        Save the current configuration to a file.

        Args:
            config (dict, optional): The configuration dictionary to save.
                                     If not provided, the current configuration
                                     stored in self.config will be used.

        Raises:
            IOError: If there is an error writing to the file.
        """
        config = config or self.config
        with open(self.config_file, "w") as f:
            yaml.dump(config, f, default_flow_style=False)

    def load_favorites(self):
        """
        Loads the favorites from a YAML file.
        This method attempts to load the favorites from a specified YAML file.
        If the file does not exist, it returns an empty dictionary. If there is
        an error during the loading process, it catches the exception, prints
        an error message, and returns an empty dictionary.
        Returns:
            dict: A dictionary containing the favorites loaded from the YAML file,
                  or an empty dictionary if the file does not exist or an error occurs.
        """
        try:
            if not self.favorites_file.exists():
                return {}

            with open(self.favorites_file, "r") as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            print(f"Error loading favorites: {e}")
            return {}

    def save_favorites(self):
        """
        Saves the current list of favorite ROMs to a file.

        This method writes the contents of the `self.favorites` list to the file
        specified by `self.favorites_file` in YAML format.

        Raises:
            IOError: If the file cannot be opened or written to.
        """
        with open(self.favorites_file, "w") as f:
            yaml.dump(self.favorites, f)

    def init_colors(self):
        """
        Initialize color pairs for the UI using the curses library.
        This method sets up the color pairs that will be used throughout the UI.
        It starts by initializing the curses color system and using the default
        terminal colors. Then, it defines several color pairs for different UI
        elements such as headers, selected items, favorites, normal text,
        highlighted text, and the status bar.
        Color pairs defined:
        - HEADER: White text on a blue background
        - SELECTED: Black text on a white background
        - FAVORITE: Yellow text on the default background
        - NORMAL: White text on the default background
        - HIGHLIGHT: Cyan text on the default background
        - STATUS_BAR: Black text on a white background
        """
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
        """
        Draws borders and headers for the system and ROM windows.
        This method draws a box around the system window and adds a header
        labeled "[ Systems ]" with a specific color. It also draws a box
        around the ROM window and adds a header labeled "[ Games ]" with
        the same color.
        The colors used for the headers are defined by the Colors.HEADER
        enumeration value.
        """
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

    def get_roms(self):
        """
        Retrieves a list of ROMs from the configured paths for each system.

        This method iterates through the systems defined in the configuration,
        collects ROM file paths from the specified directories, and organizes
        them by system.

        Returns:
            dict: A dictionary where the keys are system names and the values
                  are lists of ROM file paths.

        Raises:
            Prints a warning message if a specified ROM path is invalid.
        """
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

    def combine_all_roms(self, roms):
        """
        Combines all ROMs from all systems into a list of (system, rom_path) tuples.

        Args:
            roms (dict): A dictionary where keys are system names and values are lists of ROM paths.

        Returns:
            list: A sorted list of tuples, where each tuple contains a system name and a ROM path.
                  The list is sorted by the ROM name in a case-insensitive manner.
        """
        all_roms = []
        for system, system_roms in roms.items():
            for rom in system_roms:
                all_roms.append((system, rom))
        return sorted(
            all_roms, key=lambda x: os.path.basename(x[1]).lower()
        )  # Sort by ROM name

    def format_size(self, size):
        """
        Formats a given size in bytes into a human-readable string with appropriate units.

        Args:
            size (float): The size in bytes to be formatted.

        Returns:
            str: The formatted size string with units (B, KB, MB, GB, TB, or PB).
        """
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size < 1024:
                if unit == "B":
                    return f" {int(size)}{unit}"
                else:
                    return f" {size:.1f}{unit}"
            size /= 1024
        return f"{size:.1f}PB"

    def draw_system_window(self):
        """
        Draws the system selection window with enhanced visuals.
        This method clears the current system window and redraws it with updated
        information, including the number of favorite ROMs, all ROMs, and ROMs
        categorized by system. It highlights the currently selected view mode
        and system, if applicable.
        The window includes:
        - A favorites section with a count of favorite ROMs.
        - An "All" section with a count of all available ROMs.
        - A separator line for visual clarity.
        - A list of systems with their respective ROM counts.
        The visual elements are styled using curses color pairs to indicate
        selection and different categories.
        Attributes:
            self.system_window (curses.window): The window object where the system
                selection is drawn.
            self.view_mode (str): The current view mode, which can be "favorites",
                "all", or "systems".
            self.favorites (dict): A dictionary containing favorite ROMs categorized
                by system.
            self.all_roms (list): A list of all available ROMs.
            self.roms (dict): A dictionary containing ROMs categorized by system.
            self.selected_system (int): The index of the currently selected system
                in the systems list.
        """
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
        """
        Draws the ROM selection window with borders, ROM entries, and additional information.
        This method clears the current ROM window, draws borders, and populates the window
        with a list of ROMs based on the current view mode (systems, all, or favorites).
        It handles scrolling, selection highlighting, and displays ROM names along with their
        sizes. If a ROM is marked as a favorite, it adds a star icon next to its name.
        The method also manages scrolling for long ROM names when they are selected and ensures
        that the display is updated accordingly.
        Attributes:
            self.rom_window (curses.window): The window object where ROMs are displayed.
            self.view_mode (str): The current view mode ("systems", "all", or "favorites").
            self.roms (dict): Dictionary containing ROMs categorized by systems.
            self.filtered_roms (dict): Dictionary containing filtered ROMs based on the view mode.
            self.selected_system (int): Index of the currently selected system.
            self.selected_rom (int): Index of the currently selected ROM.
            self.total_roms (int): Total number of ROMs in the current view.
            self.current_rom_index (int): Index of the currently selected ROM (1-based).
            self.focus (str): The current focus of the application ("roms" or other).
            self.last_selection_change_time (float): Timestamp of the last selection change.
        Raises:
            Exception: If there is an error retrieving the file size of a ROM.
        """
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
        """
        Launches a ROM using the specified emulator and arguments.
        Args:
            emulator_path (str): The file path to the emulator executable.
            launch_arguments (str): The arguments to pass to the emulator. Use "{rom_path}" as a placeholder for the ROM path.
            rom_path (str): The file path to the ROM to be launched.
            start_in_directory (str): The directory to set as the working directory when launching the emulator.
        Raises:
            subprocess.CalledProcessError: If there is an error launching the emulator.
            FileNotFoundError: If the emulator executable is not found at the specified path.
        """
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
        """
        Updates the list of filtered ROMs based on the filter string and view mode.
        This method filters the ROMs according to the current filter string and view mode.
        The view modes can be "systems", "all", or "favorites". Depending on the view mode,
        the filtered ROMs are updated as follows:
        - "systems": Filters ROMs within each system based on the filter string.
        - "all": Filters all ROMs across all systems based on the filter string.
        - "favorites": Filters favorite ROMs based on the filter string.
        If the filter string is empty, the filtered ROMs list is set to the full list of ROMs
        for the current view mode.
        Attributes:
            filter_string (str): The string used to filter ROMs.
            view_mode (str): The current view mode ("systems", "all", or "favorites").
            roms (dict): A dictionary of ROMs categorized by system.
            all_roms (list): A list of all ROMs across all systems.
            filtered_roms (dict): A dictionary of filtered ROMs based on the filter string and view mode.
            get_favorite_roms_with_system (function): A function that returns favorite ROMs with their systems.
        """
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
        """
        Returns a list of favorite ROMs with their system names.

        This method iterates through the 'favorites' dictionary, which contains
        system names as keys and lists of favorite ROMs as values. It creates a
        list of tuples, where each tuple contains a system name and a ROM name.

        Returns:
            list of tuple: A list of tuples, where each tuple contains a system
            name (str) and a ROM name (str).
        """
        favorite_roms = []
        for system, roms in self.favorites.items():
            for rom in roms:
                favorite_roms.append((system, rom))
        return favorite_roms

    def toggle_favorite(self):
        """
        Toggles the favorite status of the currently selected ROM.
        Depending on the current view mode, this method will:
        - In "systems" view mode: Toggle the favorite status of the selected ROM within the selected system.
        - In "all" view mode: Toggle the favorite status of the selected ROM from the complete list of ROMs.
        - In "favorites" view mode: Toggle the favorite status of the selected ROM from the list of favorite ROMs.
        After toggling the favorite status, the method updates the filtered ROMs list and redraws the ROM window.
        It also ensures that the ROM selection position is restored and within bounds.
        Attributes:
            self.selected_rom (int): The index of the currently selected ROM.
            self.view_mode (str): The current view mode ("systems", "all", or "favorites").
            self.roms (dict): A dictionary containing ROMs categorized by systems.
            self.filtered_roms (dict): A dictionary containing filtered ROMs based on the current view mode.
            self.favorites (dict): A dictionary containing favorite ROMs categorized by systems.
            self.selected_system (int): The index of the currently selected system.
        Methods:
            self.save_favorites(): Saves the current state of favorite ROMs.
            self.toggle_favorite_by_system_and_path(system, rom_path): Toggles the favorite status of a ROM by system and path.
            self.update_filtered_roms(): Updates the list of filtered ROMs based on the current view mode.
            self.draw_rom_window(): Redraws the ROM window to reflect the current state.
        """
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
        """
        Toggles the favorite status of a ROM by its system and path.
        If the ROM is already a favorite, it will be removed from the favorites list.
        If the ROM is not a favorite, it will be added to the favorites list.
        Args:
            system (str): The system to which the ROM belongs.
            rom_path (str): The file path of the ROM.
        Returns:
            None
        """
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
        """
        Check if a ROM is marked as a favorite.

        Args:
            rom_path (str): The file path of the ROM to check.

        Returns:
            bool: True if the ROM is a favorite, False otherwise.
        """
        for system, favorites in self.favorites.items():
            if rom_path in favorites:
                return True
        return False

    def handle_input(self, key):
        """
        Handles user input for navigating and filtering ROMs.
        Parameters:
        key (int): The key code of the pressed key.
        Behavior:
        - In "filter" mode:
            - Escape key (27): Switch to "navigate" mode, clear filter string, update filtered ROMs, and reset selected ROM.
            - Enter key (10): Launch the selected ROM.
            - Backspace key (curses.KEY_BACKSPACE, 127, 8): Remove the last character from the filter string, update filtered ROMs, and reset selected ROM.
            - Up key (curses.KEY_UP): Move the selection up in the filtered ROM list.
            - Down key (curses.KEY_DOWN): Move the selection down in the filtered ROM list.
            - F2 key (curses.KEY_F2): Toggle favorite status of the selected ROM if focus is on ROMs.
            - Printable characters (32-126): Append the character to the filter string, update filtered ROMs, and reset selected ROM.
        - In "navigate" mode:
            - Up key (curses.KEY_UP): Navigate through ROMs or switch view modes and systems.
            - Down key (curses.KEY_DOWN): Navigate through ROMs or switch view modes and systems.
            - Left key (curses.KEY_LEFT): Set focus to systems.
            - Right key (curses.KEY_RIGHT): Set focus to ROMs.
            - Slash key (ord("/")): Switch to "filter" mode, clear filter string, update filtered ROMs, and reset selected ROM.
            - Enter key (10): Launch the selected ROM.
            - F2 key (curses.KEY_F2): Toggle favorite status of the selected ROM if focus is on ROMs.
        Updates:
        - Updates the timestamp if any selection state changes.
        - Redraws the ROM window, system window, and filter bar.
        """
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
        """
        Launches the selected ROM using the appropriate emulator configuration.
        Args:
            systems (list): A list of available systems.
            rom_list (list): A list of ROMs available for the selected system.
        Preconditions:
            - `self.focus` must be "roms".
            - `self.emulator_process` must be None.
            - `rom_list` must not be empty.
        Behavior:
            - If `self.view_mode` is "systems":
                - Retrieves the system configuration for the selected system.
                - Launches the ROM using the emulator path and launch arguments from the system configuration.
            - If `self.view_mode` is "favorites" or "all":
                - Retrieves the system and ROM path for the selected ROM.
                - Launches the ROM using the emulator path and launch arguments from the system configuration.
        Postconditions:
            - Clears the filter string.
            - Updates the filtered ROMs list.
            - Resets the selected ROM index to 0.
        """
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
        """
        Draws the filter bar at the bottom of the terminal window.
        This method clears the current status bar, sets the appropriate style,
        and displays the current status based on the mode (filter or ready).
        It also ensures that the status bar text fits within the window width.
        The status bar displays different information based on the mode:
        - In "filter" mode, it shows the filter string and the current ROM count.
        - In "ready" mode, it shows a ready message and the current ROM count.
        The status bar also includes help text with key bindings for various actions.
        Attributes:
            height (int): The height of the terminal window.
            width (int): The width of the terminal window.
            current_rom (int): The index of the current ROM.
            counter (str): The string representing the current ROM count.
            status (str): The status message to be displayed.
            help_text (str): The help text with key bindings.
            total_length (int): The total length of the status and help text.
            padding (int): The padding to ensure the text fits within the window width.
            final_text (str): The final text to be displayed on the status bar.
        """
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
        """
        Main function to initialize and run the ROM launcher interface.
        Args:
            stdscr: The curses window object.
        This function sets up the curses environment, initializes pygame for gamepad support,
        and handles the main event loop for the ROM launcher. It processes keyboard and gamepad
        inputs, updates the display, and manages the state of the application.
        The function also handles window resizing, auto-repeat for gamepad D-pad and joystick
        axes, and checks for the completion of the emulator process.
        Attributes:
            stdscr: The main curses window object.
            joystick: The pygame joystick object, if a gamepad is connected.
            system_window: The curses window for displaying system information.
            rom_window: The curses window for displaying ROM information.
            mode: The current mode of the application (e.g., "navigate").
            first_hat_event: Dictionary to track the first event time for each D-pad direction.
            last_hat_event: Dictionary to track the last event time for each D-pad direction.
            first_axis_event: Dictionary to track the first event time for each joystick axis direction.
            last_axis_event: Dictionary to track the last event time for each joystick axis direction.
            emulator_process: The subprocess running the emulator, if any.
        """
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


def main():
    """
    The main function that initializes the EmulatorLauncher and runs its main method
    within a curses wrapper.

    This function sets up the necessary environment for the emulator launcher
    to run with a text-based user interface using the curses library.
    """
    launcher = EmulatorLauncher()
    curses.wrapper(launcher.main)


if __name__ == "__main__":
    main()
