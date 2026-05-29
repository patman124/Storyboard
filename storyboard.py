import tkinter as tk
from tkinter import ttk, filedialog, simpledialog, messagebox
import json
import re
import os
import uuid 

# --- Global Chronology Parsing Utilities ---

CHRON_LABEL_REGEX = re.compile(r"^\s*(\d+)(?:-(\d+))?(?:-(\d+))?(?:-(\d+))?\s*$")
# Group 1: Age/Epoch - Arbitrary length
# Group 2: Year (Optional)
# Group 3: Month (Optional) 
# Group 4: Day of Month (Optional)

def _chron_label_to_sortable_float(chron_label_string):
    """
    Converts a flexible chronological label (e.g., "3", "3-1200", "3-1200-7-15-2") 
    into a sortable float representation.
    Format: Age/Epoch-Year-Month-DayOfMonth-DayOfWeek (all components after Age are optional)
    Returns None on failure.
    """
    if not chron_label_string:
        return None

    match = CHRON_LABEL_REGEX.match(chron_label_string.strip())
    if not match:
        return None

    try:
        # 1. Age/Epoch (required)
        age_epoch = float(match.group(1))
        
        # 2. Year (optional, default 0)
        year = int(match.group(2)) if match.group(2) else 0
        
        # 3. Month (optional, default 1)
        month = int(match.group(3)) if match.group(3) else 1
        
        # 4. Day of Month (optional, default 1)
        day_of_month = int(match.group(4)) if match.group(4) else 1

        # Create sortable float: Age + fractional components
        year_fraction = year / 1000000.0  # Years get 6 decimal places
        month_fraction = (month - 1) / 12000000.0  # Months normalized to year fraction
        day_fraction = (day_of_month - 1) / 365000000.0  # Days normalized 
        
        return age_epoch + year_fraction + month_fraction + day_fraction

    except ValueError:
        return None
def _get_chron_index_component(sortable_float):
    """Extracts the integer chronological index component from the sortable float."""
    if sortable_float is None:
        return None
    # Truncate to the main integer index
    return int(sortable_float)

def _format_chron_display(age_epoch, year=0, month=1, day_of_month=1):
    """Formats chronological components into a display string."""
    parts = [str(age_epoch)]
    parts.append(str(year))
    parts.append(str(month))
    parts.append(str(day_of_month))
    return "-".join(parts)


class WorldBuilderArchive(tk.Tk):
    # --- Configuration Constants ---
    DEFAULT_ROOT_NAME = "Untitled World"
    CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)) if '__file__' in dir() else os.getcwd(), "storyboard.config")
    
    # Regex to enforce safe and clean file/folder names (letters, numbers, spaces, and hyphens)
    NAME_REGEX = re.compile(r"^[a-zA-Z0-9\s-]+$")
    
    # NEW: Map friendly display names to file extensions
    FILE_TYPE_MAP = {
        "Text Document": ".txt",
        "Table (.table)": ".table",
        "Chronological Timeline": ".timeline",
        "Image Viewer": ".image"
    }

    def __init__(self):
        super().__init__()
        self.title("Storyboard") 
        self.geometry("1200x800")
        
        # --- Application State Management ---
        self.file_path = None # Path to the persistent JSON file on disk
        self.root_name = self.DEFAULT_ROOT_NAME
        self.vfs = self._initialize_new_vfs(self.root_name)
        
        self.current_path = [self.root_name]
        self.active_file_path = None
        
        # NEW: Store the last successfully saved or loaded VFS state (JSON string) for comparison
        self._last_saved_vfs_state = self._get_current_vfs_json_string() 
        
        # --- UI Initialization ---
        self._create_icons()
        self._setup_layout()
        self._populate_vfs_tree()
        
        self.protocol("WM_DELETE_WINDOW", self._on_closing)
        
        # Prompt to reopen last file
        self._prompt_reopen_last_file()

    # --- Config File Management ---

    def _load_config(self):
        try:
            with open(self.CONFIG_FILE, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _save_config(self, filepath):
        config = self._load_config()
        config["last_opened_file"] = filepath
        try:
            with open(self.CONFIG_FILE, 'w') as f:
                json.dump(config, f, indent=2)
        except Exception:
            pass

    def _prompt_reopen_last_file(self):
        config = self._load_config()
        
        # Apply saved window size
        window_size = config.get("window_size", "1200x800")
        self.geometry(window_size)
        if config.get("fullscreen", False):
            try:
                self.state('zoomed')  # Windows
            except tk.TclError:
                self.attributes('-zoomed', True)  # Linux
        
        behavior = config.get("reopen_behavior", "ask")
        if behavior == "never":
            return
        last_file = config.get("last_opened_file", "")
        if last_file and os.path.isfile(last_file):
            if behavior == "always":
                self._load_file(last_file)
            elif behavior == "ask":
                if messagebox.askyesno("Reopen Last World", 
                                       f"Reopen '{os.path.basename(last_file)}'?"):
                    self._load_file(last_file)

    def _load_file(self, filepath):
        """Load a world file from the given path."""
        try:
            with open(filepath, 'r') as f:
                loaded_data = json.load(f)

            base_filename = os.path.basename(filepath)
            new_root_name = os.path.splitext(base_filename)[0]
            
            if not isinstance(loaded_data, dict) or loaded_data.get("type") != "dir":
                raise ValueError("Not a valid World Archive format.")

            self.file_path = filepath
            self.root_name = new_root_name
            self.vfs = {self.root_name: loaded_data}
            self.current_path = [self.root_name]
            self.active_file_path = None
            self._update_saved_state()
            self._populate_vfs_tree()
            self._clear_right_panel()
            self.title(f"Storyboard - {self.root_name}")
            
            # Save to config
            self._save_config(filepath)
        except (FileNotFoundError, json.JSONDecodeError, ValueError) as e:
            messagebox.showerror("Load Error", f"Failed to load: {e}")

    # --- VFS State Management for Unsaved Changes ---

    def _get_current_vfs_json_string(self):
        """Returns the current VFS content (root node) as a formatted JSON string for comparison."""
        # Use sort_keys=True for deterministic comparison
        return json.dumps(self.vfs.get(self.root_name, {}), indent=4, sort_keys=True)
    
    def _is_vfs_modified(self):
        """Compares current VFS state with the last saved/loaded state."""
        current_state = self._get_current_vfs_json_string()
        return current_state != self._last_saved_vfs_state

    def _update_saved_state(self):
        """Updates the internal saved state tracker to the current VFS state."""
        self._last_saved_vfs_state = self._get_current_vfs_json_string()

    # --- Core VFS Persistence & Lifecycle ---
    
    def _initialize_new_vfs(self, root_name):
        """Creates a new, empty VFS structure with the given root name."""
        default_vfs_structure = {"type": "dir", "children": {}} 
        self.root_name = root_name
        self.file_path = None
        self.current_path = [self.root_name]
        self.active_file_path = None
        return {self.root_name: default_vfs_structure}
    
    def _on_closing(self):
        """Executes final save operations before closing, only if VFS is modified."""
        # CRITICAL: Always save the latest editor content to VFS before checking save status
        self._save_editor_content_to_vfs() 
        
        # NEW: Only check if the VFS state has been modified since the last save/load.
        if self._is_vfs_modified():
            if self.file_path:
                # If a file is already open/saved, prompt to save changes
                if messagebox.askyesno("Save on Exit", f"Do you want to save changes to '{os.path.basename(self.file_path)}' before exiting?"):
                    self.save_world()
            else:
                # If VFS is modified but never saved, prompt for save as
                if messagebox.askyesno("Save on Exit", "Your current world is unsaved. Would you like to save it before exiting?"):
                    self.save_world_as()

        self.destroy()

    def _open_settings(self):
        """Open the settings dialog."""
        SettingsDialog(self)

    def _write_vfs_to_disk(self, filepath):
        """Serializes and writes the current VFS state to the predefined JSON file on disk."""
        if not filepath:
            messagebox.showerror("Save Error", "Cannot save: No file path defined.")
            return

        try:
            # Only save the contents of the root node
            vfs_to_save = self.vfs.get(self.root_name, {})
            with open(filepath, 'w') as f:
                json.dump(vfs_to_save, f, indent=4)
                
            # NEW: Update the last saved state upon successful write
            self._update_saved_state()
            self._save_config(filepath)
            self.title(f"Storyboard - {self.root_name} (Saved)") 
        except Exception as e:
            messagebox.showerror("Save Error", f"Failed to save VFS to disk at {filepath}: {e}")

    # --- New File Management (Save/Load) ---
    
    def load_world(self):
        """Opens a file dialog to load a world from a JSON file."""
        # Capture current changes before loading a new world
        self._save_editor_content_to_vfs() 
        
        # Ask for confirmation if VFS is modified and not saved
        if self._is_vfs_modified():
            if not messagebox.askyesno("Confirm Load", "Your current world has unsaved changes. Load a new world and discard changes?"):
                return
                
        filepath = filedialog.askopenfilename(
            defaultextension=".json",
            filetypes=[("World Archive Files", "*.json"), ("All Files", "*.*")],
            title="Load World Archive"
        )
        if not filepath:
            return

        try:
            with open(filepath, 'r') as f:
                loaded_data = json.load(f)

            # Determine the new root name from the file path
            base_filename = os.path.basename(filepath)
            new_root_name = os.path.splitext(base_filename)[0]
            
            # The loaded data must be a directory node structure
            if not isinstance(loaded_data, dict) or loaded_data.get("type") != "dir":
                raise ValueError("The file content is not a valid World Archive format.")

            # Update application state
            self.file_path = filepath
            self.root_name = new_root_name
            self.vfs = {self.root_name: loaded_data}
            self.current_path = [self.root_name]
            self.active_file_path = None
            
            # NEW: Update the last saved state after successful load
            self._update_saved_state()
            self._save_config(filepath)
            
            # Refresh UI
            self._populate_vfs_tree()
            self._clear_right_panel()
            self.title(f"Storyboard - {self.root_name}")
            
        except (FileNotFoundError, json.JSONDecodeError, ValueError) as e:
            messagebox.showerror("Load Error", f"Failed to load world from {filepath}: {e}")
            # Revert to default VFS if load fails
            self.vfs = self._initialize_new_vfs(self.DEFAULT_ROOT_NAME)
            self._update_saved_state() # Reset state tracking to the new empty VFS
            self._populate_vfs_tree()
            self._clear_right_panel()

    def save_world_as(self):
        """Opens a file dialog to save the current world to a specified JSON file."""
        # CRITICAL: Save editor content to VFS before writing VFS to disk
        self._save_editor_content_to_vfs() 
        
        filepath = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("World Archive Files", "*.json")],
            initialfile=f"{self.root_name}.json",
            title="Save World Archive As"
        )
        
        if not filepath:
            return

        # 1. Update root name based on the chosen file name
        base_filename = os.path.basename(filepath)
        new_root_name = os.path.splitext(base_filename)[0]

        # If the root name changed, we need to update the VFS key structure
        if new_root_name != self.root_name:
            old_root_node = self.vfs.pop(self.root_name, {"type": "dir", "children": {}})
            self.vfs = {new_root_name: old_root_node}
            self.root_name = new_root_name
            self.file_path = filepath
            
            # Refresh VFS structure and paths
            self._populate_vfs_tree()
            self.path_var.set(self._get_path_string(self.current_path))
            
        # 2. Perform the actual save (which updates the saved state)
        self._write_vfs_to_disk(filepath)
        self.file_path = filepath
        self.title(f"Storyboard - {self.root_name} (Saved)")

    def save_world(self):
        """Saves the current world to the last opened/saved file path."""
        # CRITICAL: Save editor content to VFS before writing VFS to disk
        self._save_editor_content_to_vfs() 
        
        if self.file_path:
            # If path exists, write VFS to that disk location (which updates the saved state)
            self._write_vfs_to_disk(self.file_path)
        else:
            # If no path exists (fresh app load), prompt for Save As
            self.save_world_as()

    # --- Guarded VFS Access Methods ---
    
    def _get_file_node_reference(self, path):
        """Traverses the VFS structure using the given path list."""
        node = self.vfs.get(self.root_name) 
        
        if len(path) == 1 and path[0] == self.root_name:
            return node 
            
        for name in path[1:]: 
            if "children" in node and name in node["children"]:
                node = node["children"][name]
            else:
                return None 
        return node
        
    def _get_file_content(self, path_list):
        """Retrieves the content string for a file node at the specified path."""
        node = self._get_file_node_reference(path_list)
        if node and node.get("type") == "file":
            return str(node.get("content", "")) 
        return ""

    def _set_file_content(self, path_list, content):
        """
        Updates the content field of a file node in the VFS.
        (No automatic disk save, but marks VFS as potentially modified)
        """
        node = self._get_file_node_reference(path_list)
        
        if node and node.get("type") == "file":
            node["content"] = str(content)
            # The VFS is now modified, but we don't need to explicitly update the title 
            # here, as the comparison happens in _on_closing, save_world, etc.
            return True
        return False
        
    # --- VFS Structure Modification Methods ---
    
    def _get_target_folder_path(self):
        """Determines the correct parent path for creating a new node."""
        path_list = self.current_path
        node = self._get_file_node_reference(path_list)

        if node and node.get("type") == "file":
            return path_list[:-1]

        return path_list

    def _create_node(self, parent_path, name, node_type, content=None):
        """Creates a new file or folder node."""
        parent_node = self._get_file_node_reference(parent_path)
        if not parent_node or parent_node.get("type") != "dir":
            messagebox.showerror("Error", f"Cannot create node: Invalid parent directory.")
            return False 
            
        if name in parent_node.get("children", {}):
            messagebox.showerror("Error", f"A file or folder named '{name}' already exists.")
            return False
        
        base_name = name.split('.')[0]
        if not self.NAME_REGEX.match(base_name):
            messagebox.showerror("Error", "Base name must only contain letters, numbers, spaces, and hyphens.")
            return False

        if node_type == "dir":
            new_node = {"type": "dir", "children": {}}
        elif node_type == "file":
            new_node = {"type": "file", "content": str(content) if content is not None else ""}
        else:
            return False 
        
        if "children" not in parent_node:
            parent_node["children"] = {}
            
        parent_node["children"][name] = new_node
        return True

    def _delete_node(self, path):
        """Handles the deletion of a file or folder node."""
        
        if len(path) == 1: 
            messagebox.showerror("Error", "Cannot delete the root directory.")
            return

        name_to_delete = path[-1]
        parent_path = path[:-1]
        parent_node = self._get_file_node_reference(parent_path)
        
        if not parent_node or parent_node.get("type") != "dir":
            messagebox.showerror("Error", "Invalid parent path.")
            return

        node_to_delete = parent_node.get("children", {}).get(name_to_delete)
        if not node_to_delete:
            messagebox.showerror("Error", f"'{name_to_delete}' not found.")
            return

        node_type = node_to_delete.get("type", "dir")
        
        # --- DELETION PRE-CHECKS ---
        if node_type == "dir":
            if node_to_delete.get("children"):
                if not messagebox.askyesno("Confirm Deletion", 
                                           f"Folder '{name_to_delete}' is not empty. Delete it and all its contents?"):
                    return False
            else:
                if not messagebox.askyesno("Confirm Deletion", 
                                           f"Are you sure you want to delete the empty folder '{name_to_delete}'?"):
                    return False

        elif node_type == "file":
            confirmation = simpledialog.askstring("Confirm File Deletion", 
                                                  f"To permanently delete the file '{name_to_delete}', please type 'CONFIRM' below:",
                                                  parent=self)
            
            if confirmation != 'CONFIRM':
                messagebox.showinfo("Deletion Canceled", "Deletion aborted. Confirmation phrase was not entered correctly.")
                return False
        
        # --- DELETION EXECUTION ---
        if self.active_file_path and self._get_path_string(self.active_file_path) == self._get_path_string(path):
            self.active_file_path = None
            self._clear_right_panel()

        # Remove tab for deleted file (or files inside deleted folder)
        path_string = self._get_path_string(path)
        self._open_tabs = [t for t in self._open_tabs
                          if not (self._get_path_string(t) == path_string or
                                  self._get_path_string(t).startswith(path_string + "/"))]
        self._rebuild_tab_bar()
        if self._open_tabs and not self.active_file_path:
            self._switch_to_tab(self._open_tabs[-1])

        open_paths = self._get_open_paths()
        del parent_node["children"][name_to_delete]
        
        self._populate_vfs_tree()
        self._restore_tree_state(open_paths, parent_path)

        return True

    def _rename_node(self, path):
        """Renames a file or folder node, preserving its position in the children dict."""
        if len(path) == 1:
            messagebox.showerror("Error", "Cannot rename the root directory.")
            return

        old_name = path[-1]
        parent_path = path[:-1]
        parent_node = self._get_file_node_reference(parent_path)
        if not parent_node or "children" not in parent_node:
            return

        node = parent_node["children"].get(old_name)
        if not node:
            return

        is_file = node.get("type") == "file"
        # For files, strip extension for editing, then re-append
        if is_file:
            base, ext = os.path.splitext(old_name)
        else:
            base, ext = old_name, ""

        new_base = simpledialog.askstring("Rename", f"New name for '{old_name}':",
                                          initialvalue=base, parent=self)
        if not new_base or new_base.strip() == base:
            return
        new_base = new_base.strip()

        if not self.NAME_REGEX.match(new_base):
            messagebox.showerror("Error", "Name must only contain letters, numbers, spaces, and hyphens.")
            return

        new_name = new_base + ext
        if new_name in parent_node["children"]:
            messagebox.showerror("Error", f"'{new_name}' already exists.")
            return

        # Rebuild children dict preserving order with new key
        new_children = {}
        for key, val in parent_node["children"].items():
            if key == old_name:
                new_children[new_name] = val
            else:
                new_children[key] = val
        parent_node["children"] = new_children

        # Update active file path if it was the renamed node
        if self.active_file_path and self._get_path_string(self.active_file_path) == self._get_path_string(path):
            self.active_file_path = parent_path + [new_name]

        # Update open tabs for renamed node
        old_path_string = self._get_path_string(path)
        new_path_string = self._get_path_string(parent_path + [new_name])
        for i, tab in enumerate(self._open_tabs):
            tab_str = self._get_path_string(tab)
            if tab_str == old_path_string:
                self._open_tabs[i] = parent_path + [new_name]
            elif tab_str.startswith(old_path_string + "/"):
                self._open_tabs[i] = parent_path + [new_name] + tab[len(path):]
        self._rebuild_tab_bar()

        open_paths = self._get_open_paths()
        self._populate_vfs_tree()
        self._restore_tree_state(open_paths, parent_path + [new_name])

    def _copy_node(self, path):
        """Deep-copies a file or folder node as a sibling with ' - Copy' suffix."""
        import copy

        if len(path) == 1:
            messagebox.showerror("Error", "Cannot copy the root directory.")
            return

        name = path[-1]
        parent_path = path[:-1]
        parent_node = self._get_file_node_reference(parent_path)
        if not parent_node or "children" not in parent_node:
            return

        node = parent_node["children"].get(name)
        if not node:
            return

        # Generate unique copy name
        base, ext = os.path.splitext(name) if node.get("type") == "file" else (name, "")
        copy_name = f"{base} - Copy{ext}"
        counter = 2
        while copy_name in parent_node["children"]:
            copy_name = f"{base} - Copy {counter}{ext}"
            counter += 1

        parent_node["children"][copy_name] = copy.deepcopy(node)

        open_paths = self._get_open_paths()
        self._populate_vfs_tree()
        self._restore_tree_state(open_paths, parent_path + [copy_name])

    def _get_path_string(self, path):
        """Converts a VFS path list (e.g., ['A', 'B']) to a string (e.g., 'A/B')."""
        return "/".join(path)

    # --- Treeview State Management ---

    def _get_open_paths(self):
        """Collects the path strings of all expanded nodes."""
        open_paths = set()
        def traverse(parent_id):
            for item_id in self.vfs_tree.get_children(parent_id):
                if self.vfs_tree.item(item_id, 'open'):
                    path_string = self.vfs_tree.item(item_id, 'values')[0]
                    open_paths.add(path_string)
                    traverse(item_id)
        traverse('') 
        return open_paths

    def _restore_tree_state(self, open_paths, path_to_select=None):
        """Restores the expansion state of the Treeview nodes."""
        item_to_select = None
        
        def traverse_and_restore(parent_id):
            nonlocal item_to_select
            for item_id in self.vfs_tree.get_children(parent_id):
                item_values = self.vfs_tree.item(item_id, 'values')
                if not item_values: continue
                
                path_string = item_values[0]
                
                if path_to_select and path_string == self._get_path_string(path_to_select):
                    item_to_select = item_id
                
                if path_string in open_paths:
                    self.vfs_tree.item(item_id, open=True)
                
                traverse_and_restore(item_id)
                
        traverse_and_restore('')

        if item_to_select:
            self.vfs_tree.selection_remove(self.vfs_tree.selection())
            self.vfs_tree.selection_set(item_to_select)
            self.vfs_tree.see(item_to_select)
            
            path_string = self.vfs_tree.item(item_to_select, 'values')[0]
            self.current_path = path_string.split('/')
            self.path_var.set(path_string)

    # --- UI Component Setup ---
        
    def _create_icons(self):
        """Generates simple, graphical folder and file icons using PIL."""
        from PIL import Image, ImageTk, ImageDraw
        size = (16, 16)
        icon_color = "#34568B" 
        
        # Folder Icon drawing
        folder_img = Image.new('RGBA', size, (0, 0, 0, 0))
        d = ImageDraw.Draw(folder_img)
        d.rectangle([2, 5, 14, 14], fill=icon_color, outline=icon_color) 
        d.polygon([(2, 5), (4, 2), (8, 2), (10, 5)], fill=icon_color)
        self.folder_icon = ImageTk.PhotoImage(folder_img)
        
        # File Icon drawing
        file_img = Image.new('RGBA', size, (0, 0, 0, 0))
        d = ImageDraw.Draw(file_img)
        d.polygon([(2, 2), (13, 2), (13, 14), (2, 14), (2, 2)], fill="white", outline=icon_color)
        d.line([(2, 2), (13, 2), (13, 14), (2, 14), (2, 2)], fill=icon_color, width=1)
        d.line([(5, 5), (10, 5)], fill=icon_color)
        d.line([(5, 8), (10, 8)], fill=icon_color)
        d.line([(5, 11), (10, 11)], fill=icon_color)
        self.file_icon = ImageTk.PhotoImage(file_img)

    def _setup_layout(self):
        """Configures the main window layout."""
        style = ttk.Style(self)
        style.theme_use("clam") 
        
        # --- Top Bar with Gear Icon ---
        top_bar = ttk.Frame(self)
        top_bar.pack(fill=tk.X, padx=5, pady=(5, 0))
        
        ttk.Label(top_bar, text="Storyboard", font=('Helvetica', 12, 'bold')).pack(side=tk.LEFT)
        
        gear_btn = ttk.Button(top_bar, text="⚙", width=3, command=self._open_settings)
        gear_btn.pack(side=tk.RIGHT)
        ttk.Button(top_bar, text="Save", command=self.save_world).pack(side=tk.RIGHT, padx=2)
        ttk.Button(top_bar, text="Save As...", command=self.save_world_as).pack(side=tk.RIGHT, padx=2)
        ttk.Button(top_bar, text="Load", command=self.load_world).pack(side=tk.RIGHT, padx=2)
        
        self.main_pane = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        self.main_pane.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # --- Left Panel ---
        self.left_frame = ttk.Frame(self.main_pane, padding="5 5 5 5")
        self.main_pane.add(self.left_frame, weight=10)
        
        self.path_var = tk.StringVar(value=self._get_path_string(self.current_path))
        ttk.Label(self.left_frame, textvariable=self.path_var, font=('Helvetica', 10, 'bold'), anchor='w').pack(fill=tk.X, pady=(0, 5))
        
        tree_frame = ttk.Frame(self.left_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        
        self.vfs_tree = ttk.Treeview(tree_frame, columns=('path_string'), show='tree')
        self.vfs_tree.column('#0', width=200, anchor='w')
        self.vfs_tree.heading('#0', text='Name')
        self.vfs_tree.column('path_string', width=0, stretch=tk.NO) 
        self.vfs_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.vfs_tree.bind('<<TreeviewSelect>>', self._on_tree_select)
        self.vfs_tree.bind('<Double-1>', self._on_tree_double_click)
        self.vfs_tree.bind('<ButtonRelease-3>', self._on_tree_right_click)
        
        # Drag-and-drop reordering
        self._drag_item = None
        self._drop_indicator = None  # Canvas line id for visual indicator
        self._drop_target_info = None  # (item, position) where position is 'before', 'after', or 'into'
        self.vfs_tree.bind('<ButtonPress-1>', self._on_drag_start)
        self.vfs_tree.bind('<B1-Motion>', self._on_drag_motion)
        self.vfs_tree.bind('<ButtonRelease-1>', self._on_drag_drop)
        
        tree_scroll = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.vfs_tree.yview)
        self.vfs_tree.configure(yscrollcommand=tree_scroll.set)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        # --- Right Panel ---
        self.right_frame = ttk.Frame(self.main_pane, padding="5 5 5 5")
        self.main_pane.add(self.right_frame, weight=70)

        # Tab bar for open files
        self._tab_bar = ttk.Frame(self.right_frame)
        self._tab_bar.pack(fill=tk.X, pady=(0, 3))
        self._editor_area = ttk.Frame(self.right_frame)
        self._editor_area.pack(fill=tk.BOTH, expand=True)
        self._open_tabs = []  # list of path_lists
        self._tab_buttons = {}  # path_string -> button widget
        self._popped_out_files = {}  # path_string -> Toplevel window
        
        self._vfs_panel_visible = True
        self._vfs_toggle_btn = ttk.Button(top_bar, text="◀", width=3, command=self._toggle_vfs_panel)
        self._vfs_toggle_btn.pack(side=tk.LEFT, padx=(10, 0))

        # Load auto-collapse setting
        config = self._load_config()
        self._auto_collapse_vfs = config.get("auto_collapse_vfs", False)
        
        self.active_editor = None

    def _populate_vfs_tree(self):
        """Rebuilds the entire Treeview display from the VFS dictionary."""
        for item in self.vfs_tree.get_children():
            self.vfs_tree.delete(item)

        def insert_node(parent_id, node_name, node_data, path_list):
            node_type = node_data.get("type", "dir")
            # Image assets need to be imported within the method scope if not defined globally
            from PIL import Image, ImageTk, ImageDraw # Re-importing locally to ensure availability
            
            size = (16, 16)
            icon_color = "#34568B" 
            
            # Simple icon logic redundancy to avoid PIL/Tkinter garbage collection issues in complex apps
            if node_type == "dir":
                icon = self.folder_icon
            else:
                icon = self.file_icon

            item_id = self.vfs_tree.insert(parent_id, 'end', 
                                           text=node_name, 
                                           image=icon,
                                           tags=("node",))
            
            self.vfs_tree.item(item_id, values=(self._get_path_string(path_list),))

            if node_type == "dir" and "children" in node_data:
                for child_name, child_data in node_data["children"].items():
                    new_path = path_list + [child_name]
                    insert_node(item_id, child_name, child_data, new_path)

            # Ensure root nodes are always open
            if len(path_list) == 1 and path_list[0] == self.root_name:
                 self.vfs_tree.item(item_id, open=True)

        root_content = self.vfs.get(self.root_name)
        if root_content:
            root_id = self.vfs_tree.insert('', 'end', 
                                           text=self.root_name, 
                                           image=self.folder_icon,
                                           tags=("node",))
            self.vfs_tree.item(root_id, values=(self._get_path_string([self.root_name]),))
            
            if "children" in root_content:
                for child_name, child_data in root_content["children"].items():
                    new_path = [self.root_name, child_name]
                    insert_node(root_id, child_name, child_data, new_path)

            self.vfs_tree.item(root_id, open=True) 
        
        self.path_var.set(self._get_path_string(self.current_path))


    def _on_tree_select(self, event):
        """Event handler for single-click selection in the Treeview."""
        selected_item = self.vfs_tree.selection()
        if not selected_item: return
            
        item_id = selected_item[0]
        item_values = self.vfs_tree.item(item_id, 'values')
        if item_values:
            path_string = item_values[0]
            self.current_path = path_string.split('/')
            self.path_var.set(path_string)


    def _on_tree_double_click(self, event):
        """Opens files in the editor or expands/collapses directories."""
        selected_item = self.vfs_tree.selection()
        if not selected_item: return
            
        item_id = selected_item[0]
        item_values = self.vfs_tree.item(item_id, 'values')
        if not item_values: return

        path_string = item_values[0]
        path_list = path_string.split('/')
        node = self._get_file_node_reference(path_list)
        
        if not node: return

        if node.get("type") == "dir":
            self.current_path = path_list
            self.path_var.set(path_string)
            is_open = self.vfs_tree.item(item_id, 'open')
            self.vfs_tree.item(item_id, open=not is_open)
        elif node.get("type") == "file":
            self._open_file_editor(path_list)

        return "break"


    # --- Right-Click Context Menu ---

    def _on_tree_right_click(self, event):
        """Shows a context menu on right-click with options based on node type."""
        item = self.vfs_tree.identify_row(event.y)
        if not item:
            return

        # Select the item under cursor
        self.vfs_tree.selection_set(item)
        self.vfs_tree.focus(item)

        item_values = self.vfs_tree.item(item, 'values')
        if not item_values:
            return

        path_string = item_values[0]
        path_list = path_string.split('/')
        node = self._get_file_node_reference(path_list)
        if not node:
            return

        is_root = len(path_list) == 1
        menu = tk.Menu(self, tearoff=0)

        if node.get("type") == "dir":
            menu.add_command(label="New Folder", command=lambda: self._ctx_create_folder(path_list))
            menu.add_command(label="New File", command=lambda: self._ctx_create_file(path_list))
            if not is_root:
                menu.add_separator()
                menu.add_command(label="Rename", command=lambda: self._rename_node(path_list))
                menu.add_command(label="Duplicate", command=lambda: self._copy_node(path_list))
                menu.add_separator()
                menu.add_command(label="Delete", command=lambda: self._delete_node(path_list))
        else:
            menu.add_command(label="Rename", command=lambda: self._rename_node(path_list))
            menu.add_command(label="Duplicate", command=lambda: self._copy_node(path_list))
            menu.add_separator()
            menu.add_command(label="New File in Folder", command=lambda: self._ctx_create_file(path_list[:-1]))
            menu.add_separator()
            menu.add_command(label="Delete", command=lambda: self._delete_node(path_list))

        popup_menu(menu, event.x_root, event.y_root)

    def _ctx_create_folder(self, parent_path):
        """Context menu action: create folder inside the given path."""
        self.current_path = parent_path
        self._open_create_folder_dialog()

    def _ctx_create_file(self, parent_path):
        """Context menu action: create file inside the given path."""
        self.current_path = parent_path
        self._open_create_file_dialog()

    # --- Drag-and-Drop Reordering ---

    def _on_drag_start(self, event):
        """Record the item being dragged."""
        item = self.vfs_tree.identify_row(event.y)
        if item:
            path_string = self.vfs_tree.item(item, 'values')[0] if self.vfs_tree.item(item, 'values') else None
            # Don't allow dragging the root
            if path_string and '/' in path_string:
                self._drag_item = item
            else:
                self._drag_item = None
        else:
            self._drag_item = None

    def _clear_drop_indicator(self):
        """Remove the visual drop indicator spacer."""
        if self._drop_indicator:
            try:
                self.vfs_tree.delete(self._drop_indicator)
            except Exception:
                pass
        # Clear 'drop_into' highlight from all items
        self.vfs_tree.tag_configure('drop_into', background='')
        for item in self._get_all_tree_items():
            tags = self.vfs_tree.item(item, 'tags')
            if 'drop_into' in tags:
                self.vfs_tree.item(item, tags=('node',))
        self._drop_indicator = None
        self._drop_target_info = None

    def _get_all_tree_items(self):
        """Recursively get all item IDs in the treeview."""
        items = []
        def collect(parent):
            for item in self.vfs_tree.get_children(parent):
                items.append(item)
                collect(item)
        collect('')
        return items

    def _on_drag_motion(self, event):
        """Show a visual insertion gap indicating drop position."""
        if not self._drag_item:
            return
        
        target = self.vfs_tree.identify_row(event.y)
        
        # Skip if hovering over the spacer itself
        if target and target == self._drop_indicator:
            return
        
        self._clear_drop_indicator()
        
        if not target or target == self._drag_item:
            self.vfs_tree.config(cursor="")
            return

        tgt_values = self.vfs_tree.item(target, 'values')
        src_values = self.vfs_tree.item(self._drag_item, 'values')
        if not tgt_values or not src_values:
            return

        # Prevent dropping into own subtree
        if tgt_values[0].startswith(src_values[0] + '/'):
            self.vfs_tree.config(cursor="no")
            return

        self.vfs_tree.config(cursor="hand2")

        bbox = self.vfs_tree.bbox(target)
        if not bbox:
            return

        x, y, w, h = bbox
        rel_y = event.y - y  # position within the target row

        tgt_path = tgt_values[0].split('/')
        tgt_node = self._get_file_node_reference(tgt_path)
        is_dir = tgt_node and tgt_node.get("type") == "dir"

        # Determine drop zone: top 25% = before, bottom 25% = after, middle 50% on folders = into
        if rel_y < h * 0.25:
            position = 'before'
            line_y = y
        elif rel_y > h * 0.75:
            position = 'after'
            line_y = y + h
        elif is_dir:
            position = 'into'
            line_y = None
        else:
            # For files, middle zone counts as 'after'
            position = 'after'
            line_y = y + h

        self._drop_target_info = (target, position)

        # Visual feedback: insert a spacer item to show the gap, or highlight for 'into'
        if position == 'into':
            self.vfs_tree.tag_configure('drop_into', background='#BBDEFB')
            self.vfs_tree.item(target, tags=('drop_into',))
            self._drop_indicator = None  # No spacer for 'into'
        else:
            parent_id = self.vfs_tree.parent(target)
            target_index = self.vfs_tree.index(target)
            insert_index = target_index if position == 'before' else target_index + 1
            self._drop_indicator = self.vfs_tree.insert(parent_id, insert_index,
                                                        text='━━━━━━━━━━━━━━━━━━━━',
                                                        tags=('spacer',))
            self.vfs_tree.tag_configure('spacer', foreground='#1976D2', background='#E3F2FD')

    def _on_drag_drop(self, event):
        """Handle drop based on the indicator position."""
        self.vfs_tree.config(cursor="")
        self._clear_drop_indicator()

        if not self._drag_item:
            return

        target = self.vfs_tree.identify_row(event.y)
        if not target or target == self._drag_item:
            self._drag_item = None
            return

        src_values = self.vfs_tree.item(self._drag_item, 'values')
        tgt_values = self.vfs_tree.item(target, 'values')
        if not src_values or not tgt_values:
            self._drag_item = None
            return

        src_path = src_values[0].split('/')
        tgt_path = tgt_values[0].split('/')

        # Prevent dropping into own subtree
        if tgt_values[0].startswith(src_values[0] + '/'):
            self._drag_item = None
            return

        # Recalculate position from event
        bbox = self.vfs_tree.bbox(target)
        if not bbox:
            self._drag_item = None
            return

        x, y, w, h = bbox
        rel_y = event.y - y
        tgt_node = self._get_file_node_reference(tgt_path)
        is_dir = tgt_node and tgt_node.get("type") == "dir"

        if rel_y < h * 0.25:
            position = 'before'
        elif rel_y > h * 0.75:
            position = 'after'
        elif is_dir:
            position = 'into'
        else:
            position = 'after'

        src_parent = src_path[:-1]
        tgt_parent = tgt_path[:-1]

        if position == 'into':
            # Move into the target folder
            self._move_node_to(src_path, tgt_path)
            new_selection = tgt_path + [src_path[-1]]
        elif src_parent == tgt_parent:
            # Same parent — just reorder
            if position == 'before':
                self._reorder_node(tgt_parent, src_path[-1], tgt_path[-1])
            else:
                self._reorder_node_after(tgt_parent, src_path[-1], tgt_path[-1])
            new_selection = src_path
        else:
            # Different parent — move to target's parent, then position
            self._move_node_to(src_path, tgt_parent)
            if self._get_file_node_reference(tgt_parent + [src_path[-1]]):
                if position == 'before':
                    self._reorder_node(tgt_parent, src_path[-1], tgt_path[-1])
                else:
                    self._reorder_node_after(tgt_parent, src_path[-1], tgt_path[-1])
            new_selection = tgt_parent + [src_path[-1]]

        open_paths = self._get_open_paths()
        self._populate_vfs_tree()
        self._restore_tree_state(open_paths, new_selection)
        self._drag_item = None

    def _reorder_node(self, parent_path, src_name, tgt_name):
        """Reorder src_name to appear before tgt_name in parent's children dict."""
        parent_node = self._get_file_node_reference(parent_path)
        if not parent_node or "children" not in parent_node:
            return
        children = parent_node["children"]
        if src_name not in children or tgt_name not in children:
            return
        # Rebuild ordered dict with src placed before tgt
        new_children = {}
        for key in children:
            if key == src_name:
                continue
            if key == tgt_name:
                new_children[src_name] = children[src_name]
            new_children[key] = children[key]
        # If tgt was last and src wasn't inserted yet
        if src_name not in new_children:
            new_children[src_name] = children[src_name]
        parent_node["children"] = new_children

    def _reorder_node_after(self, parent_path, src_name, tgt_name):
        """Reorder src_name to appear after tgt_name in parent's children dict."""
        parent_node = self._get_file_node_reference(parent_path)
        if not parent_node or "children" not in parent_node:
            return
        children = parent_node["children"]
        if src_name not in children or tgt_name not in children:
            return
        new_children = {}
        for key in children:
            if key == src_name:
                continue
            new_children[key] = children[key]
            if key == tgt_name:
                new_children[src_name] = children[src_name]
        if src_name not in new_children:
            new_children[src_name] = children[src_name]
        parent_node["children"] = new_children

    def _move_node_to(self, src_path, dest_parent_path):
        """Move a node from src_path into dest_parent_path folder."""
        src_name = src_path[-1]
        src_parent = self._get_file_node_reference(src_path[:-1])
        dest_parent = self._get_file_node_reference(dest_parent_path)

        if not src_parent or not dest_parent:
            return
        if src_name in dest_parent.get("children", {}):
            messagebox.showerror("Error", f"'{src_name}' already exists in the destination folder.")
            return

        node = src_parent["children"].pop(src_name)
        if "children" not in dest_parent:
            dest_parent["children"] = {}
        dest_parent["children"][src_name] = node

    # --- VFS Action Dialogs (Folder, File, Delete) ---

    def _open_create_folder_dialog(self):
        """Prompts for a new folder name and attempts creation, preserving tree state."""
        target_path = self._get_target_folder_path()
        open_paths = self._get_open_paths()
        
        new_name = simpledialog.askstring("New Folder", f"Enter new folder name in {target_path[-1]}:", parent=self)
        if new_name:
            if self._create_node(target_path, new_name, "dir"):
                new_path = target_path + [new_name]
                self._populate_vfs_tree()
                self._restore_tree_state(open_paths, new_path)


    def _open_create_file_dialog(self):
        """Opens a custom dialog for selecting file name and type, preserving tree state."""
        self._save_editor_content_to_vfs() 
        target_path = self._get_target_folder_path()
        
        # --- MODIFIED: Use friendly names based on the map keys ---
        friendly_types = list(self.FILE_TYPE_MAP.keys()) 
        dialog = NewFileCreationDialog(self, target_path[-1], friendly_types)
        
        if dialog.result and dialog.result['base_name']:
            base_name = dialog.result['base_name'].strip()
            
            # The dialog returns the friendly name. Look up the actual extension.
            friendly_type_selected = dialog.result['extension']
            extension = self.FILE_TYPE_MAP.get(friendly_type_selected, ".txt") # Default safety
            
            if not self.NAME_REGEX.match(base_name):
                 messagebox.showerror("Error", "Base name must only contain letters, numbers, spaces, and hyphens.")
                 return

            final_name = base_name + extension
            open_paths = self._get_open_paths()

            if self._create_node(target_path, final_name, "file"): 
                new_path = target_path + [final_name]
                self._populate_vfs_tree()
                self._restore_tree_state(open_paths, new_path)
        # --- END MODIFIED BLOCK ---


    def _delete_selected_node(self):
        """Retrieves the currently selected path and initiates the deletion process."""
        selected_item = self.vfs_tree.selection()
        if not selected_item:
            messagebox.showinfo("Select Item", "Please select a file or folder to delete.")
            return

        item_id = selected_item[0]
        item_values = self.vfs_tree.item(item_id, 'values')
        if not item_values:
             messagebox.showerror("Error", "Cannot identify selected item.")
             return
             
        path_string = item_values[0]
        path_list = path_string.split('/')
        
        self._delete_node(path_list)


    # --- Right Panel Editor Management ---

    def _toggle_vfs_panel(self):
        """Show or hide the VFS left panel."""
        if self._vfs_panel_visible:
            self.main_pane.forget(self.left_frame)
            self._vfs_toggle_btn.config(text="▶")
            self._vfs_panel_visible = False
        else:
            self.main_pane.insert(0, self.left_frame, weight=10)
            self._vfs_toggle_btn.config(text="◀")
            self._vfs_panel_visible = True

    def _clear_right_panel(self):
        """Removes the active editor widget from the editor area."""
        for widget in self._editor_area.winfo_children():
            widget.destroy()
        self.active_editor = None

    def _open_file_editor(self, path_list):
        """Initializes the correct editor widget (Text, CSV, or Timeline) for the new file."""
        
        file_name = path_list[-1]
        path_string = self._get_path_string(path_list)

        # If file is in a pop-out window, focus that window instead
        if path_string in self._popped_out_files:
            win = self._popped_out_files[path_string]
            win.lift()
            win.focus_force()
            return

        self._save_editor_content_to_vfs()

        # Add to open tabs if not already there
        if path_list not in self._open_tabs:
            self._open_tabs.append(list(path_list))

        self._rebuild_tab_bar()
        self._switch_to_tab(path_list)

        # Auto-collapse VFS panel if setting enabled
        if self._auto_collapse_vfs and self._vfs_panel_visible:
            self._toggle_vfs_panel()

    def _rebuild_tab_bar(self):
        """Rebuild the tab bar buttons."""
        for widget in self._tab_bar.winfo_children():
            widget.destroy()
        self._tab_buttons = {}
        self._tab_drag_src = None

        for tab_path in self._open_tabs:
            path_string = self._get_path_string(tab_path)
            file_name = tab_path[-1]
            btn = ttk.Button(self._tab_bar, text=file_name,
                           command=lambda p=list(tab_path): self._switch_to_tab(p))
            btn.pack(side=tk.LEFT, padx=1)
            btn.bind('<ButtonRelease-3>', lambda e, p=list(tab_path): self._tab_right_click(e, p))
            btn.bind('<ButtonPress-1>', lambda e, p=path_string: self._tab_drag_start(e, p))
            btn.bind('<B1-Motion>', self._tab_drag_motion)
            btn.bind('<ButtonRelease-1>', self._tab_drag_drop)
            self._tab_buttons[path_string] = btn

    def _tab_drag_start(self, event, path_string):
        """Start tab drag."""
        self._tab_drag_src = path_string
        self._tab_drag_start_x = event.x_root
        self._tab_drag_active = False
        self._tab_drag_indicator = None
        self._tab_drag_last_target = None

    def _tab_drag_motion(self, event):
        """Show cursor and insertion indicator during tab drag."""
        if not self._tab_drag_src:
            return
        if not self._tab_drag_active:
            if abs(event.x_root - self._tab_drag_start_x) < 8:
                return
            self._tab_drag_active = True
            event.widget.config(cursor="hand2")

        # Find which tab button we're over
        target_widget = self._tab_bar.winfo_containing(event.x_root, event.y_root)
        target_path = None
        for ps, btn in self._tab_buttons.items():
            if btn == target_widget:
                target_path = ps
                break

        if not target_path or target_path == self._tab_drag_src:
            if target_path == self._tab_drag_src and self._tab_drag_indicator:
                self._tab_drag_indicator.destroy()
                self._tab_drag_indicator = None
                self._tab_drag_last_target = None
            return

        # Determine left/right side of target
        btn = self._tab_buttons[target_path]
        btn_x = btn.winfo_rootx()
        btn_w = btn.winfo_width()
        side = "before" if (event.x_root - btn_x) < btn_w / 2 else "after"
        target_key = (target_path, side)

        if target_key == self._tab_drag_last_target:
            return
        self._tab_drag_last_target = target_key

        # Remove old indicator
        if self._tab_drag_indicator:
            self._tab_drag_indicator.destroy()
            self._tab_drag_indicator = None

        # Insert blank spacer indicator
        self._tab_drag_indicator = ttk.Frame(self._tab_bar, width=4)
        self._tab_drag_indicator.configure(style="TabSpacer.TFrame")
        style = ttk.Style()
        style.configure("TabSpacer.TFrame", background="#1976D2")
        self._tab_drag_indicator.pack_propagate(False)

        # Position relative to target button
        if side == "before":
            btn.pack_forget()
            self._tab_drag_indicator.pack(side=tk.LEFT, padx=1, fill=tk.Y, pady=2)
            btn.pack(side=tk.LEFT, padx=1)
            # Re-pack all buttons after target to maintain order
            self._repack_tabs_after(target_path)
        else:
            # Insert after target
            self._repack_tabs_after_with_indicator(target_path)

    def _repack_tabs_after(self, after_path):
        """Re-pack tabs that come after the given path to maintain order."""
        found = False
        for tab_path in self._open_tabs:
            ps = self._get_path_string(tab_path)
            if ps == after_path:
                found = True
                continue
            if found and ps in self._tab_buttons and ps != self._tab_drag_src:
                self._tab_buttons[ps].pack_forget()
                self._tab_buttons[ps].pack(side=tk.LEFT, padx=1)

    def _repack_tabs_after_with_indicator(self, after_path):
        """Re-pack indicator after target, then remaining tabs."""
        # Unpack everything after target, insert indicator, repack
        tabs_after = []
        found = False
        for tab_path in self._open_tabs:
            ps = self._get_path_string(tab_path)
            if ps == after_path:
                found = True
                continue
            if found and ps in self._tab_buttons:
                tabs_after.append(ps)

        for ps in tabs_after:
            self._tab_buttons[ps].pack_forget()

        self._tab_drag_indicator.pack_forget()
        self._tab_drag_indicator.pack(side=tk.LEFT, padx=1, fill=tk.Y, pady=2)

        for ps in tabs_after:
            if ps != self._tab_drag_src:
                self._tab_buttons[ps].pack(side=tk.LEFT, padx=1)

    def _tab_drag_drop(self, event):
        """Drop tab at new position."""
        if not self._tab_drag_src:
            return
        event.widget.config(cursor="")

        # Remove indicator
        if self._tab_drag_indicator:
            self._tab_drag_indicator.destroy()
            self._tab_drag_indicator = None

        if not self._tab_drag_active:
            self._tab_drag_src = None
            return

        # Find which button we're over
        target_widget = self._tab_bar.winfo_containing(event.x_root, event.y_root)
        target_path = None
        for ps, btn in self._tab_buttons.items():
            if btn == target_widget:
                target_path = ps
                break

        src_path = self._tab_drag_src
        self._tab_drag_src = None
        self._tab_drag_last_target = None

        if not target_path or target_path == src_path:
            self._rebuild_tab_bar()
            if self.active_file_path:
                active_str = self._get_path_string(self.active_file_path)
                for ps, btn in self._tab_buttons.items():
                    btn.state(['pressed'] if ps == active_str else ['!pressed'])
            return

        # Determine insert position
        btn = self._tab_buttons[target_path]
        btn_x = btn.winfo_rootx()
        btn_w = btn.winfo_width()
        side = "before" if (event.x_root - btn_x) < btn_w / 2 else "after"

        # Reorder _open_tabs
        src_idx = next((i for i, t in enumerate(self._open_tabs) if self._get_path_string(t) == src_path), None)
        tgt_idx = next((i for i, t in enumerate(self._open_tabs) if self._get_path_string(t) == target_path), None)
        if src_idx is None or tgt_idx is None:
            return

        tab = self._open_tabs.pop(src_idx)
        # Adjust target index after removal
        tgt_idx = next((i for i, t in enumerate(self._open_tabs) if self._get_path_string(t) == target_path), None)
        if tgt_idx is None:
            self._open_tabs.append(tab)
        else:
            insert_idx = tgt_idx if side == "before" else tgt_idx + 1
            self._open_tabs.insert(insert_idx, tab)

        self._rebuild_tab_bar()

        # Re-highlight active tab
        if self.active_file_path:
            active_str = self._get_path_string(self.active_file_path)
            for ps, btn in self._tab_buttons.items():
                btn.state(['pressed'] if ps == active_str else ['!pressed'])

    def _switch_to_tab(self, path_list):
        """Switch the editor area to show the given file."""
        self._save_editor_content_to_vfs()
        self._clear_right_panel()

        content = self._get_file_content(path_list)
        file_name = path_list[-1]

        editor_frame = ttk.Frame(self._editor_area)
        editor_frame.pack(fill=tk.BOTH, expand=True)

        if file_name.lower().endswith('.table'):
            self.active_editor = CSVGrid(editor_frame, content, name_regex=self.NAME_REGEX, controller=self)
        elif file_name.lower().endswith('.timeline'):
            self.active_editor = TimelineEditor(editor_frame, content, controller=self)
        elif file_name.lower().endswith('.image'):
            self.active_editor = ImageViewer(editor_frame, content, controller=self)
        else:
            self.active_editor = TextEditor(editor_frame, content, controller=self)

        self.active_editor.pack(fill=tk.BOTH, expand=True)
        self.active_file_path = path_list

        # Highlight active tab
        for ps, btn in self._tab_buttons.items():
            if ps == self._get_path_string(path_list):
                btn.state(['pressed'])
            else:
                btn.state(['!pressed'])

    def _tab_right_click(self, event, path_list):
        """Right-click menu on a tab."""
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="Pop Out", command=lambda: self._pop_out_tab(path_list))
        menu.add_separator()
        menu.add_command(label="Close", command=lambda: self._close_tab(path_list))
        menu.add_command(label="Close Others", command=lambda: self._close_other_tabs(path_list))
        popup_menu(menu, event.x_root, event.y_root)

    def _pop_out_tab(self, path_list):
        """Open a file in a separate pop-out window."""
        self._save_editor_content_to_vfs()
        file_name = path_list[-1]
        path_string = self._get_path_string(path_list)
        content = self._get_file_content(path_list)

        win = tk.Toplevel(self)
        self._popped_out_files[path_string] = win
        win.title(f"Storyboard - {file_name}")
        win.geometry("800x600")

        editor_frame = ttk.Frame(win, padding="5")
        editor_frame.pack(fill=tk.BOTH, expand=True)

        if file_name.lower().endswith('.table'):
            editor = CSVGrid(editor_frame, content, name_regex=self.NAME_REGEX, controller=self)
        elif file_name.lower().endswith('.timeline'):
            editor = TimelineEditor(editor_frame, content, controller=self)
        elif file_name.lower().endswith('.image'):
            editor = ImageViewer(editor_frame, content, controller=self)
        else:
            editor = TextEditor(editor_frame, content, controller=self)

        editor.pack(fill=tk.BOTH, expand=True)

        # Save content back to VFS when window closes and re-add as tab
        def on_close():
            if hasattr(editor, 'get_content') and editor.winfo_exists():
                self._set_file_content(path_list, editor.get_content())
            self._popped_out_files.pop(path_string, None)
            win.destroy()
            # Re-add as a tab and switch to it
            if path_list not in self._open_tabs:
                self._open_tabs.append(list(path_list))
            self._rebuild_tab_bar()
            self._switch_to_tab(path_list)

        win.protocol("WM_DELETE_WINDOW", on_close)

        # Close the tab in the main window
        self._close_tab(path_list)

    def _close_tab(self, path_list):
        """Close a tab and switch to an adjacent one."""
        path_string = self._get_path_string(path_list)

        # Save content if this is the active tab
        if self.active_file_path and self._get_path_string(self.active_file_path) == path_string:
            self._save_editor_content_to_vfs()

        # Remove from open tabs
        self._open_tabs = [t for t in self._open_tabs if self._get_path_string(t) != path_string]
        self._rebuild_tab_bar()

        # Switch to another tab or clear
        if self._open_tabs:
            if self.active_file_path and self._get_path_string(self.active_file_path) == path_string:
                self._switch_to_tab(self._open_tabs[-1])
        else:
            self._clear_right_panel()
            self.active_file_path = None

    def _close_other_tabs(self, keep_path_list):
        """Close all tabs except the specified one."""
        self._save_editor_content_to_vfs()
        keep_string = self._get_path_string(keep_path_list)
        self._open_tabs = [t for t in self._open_tabs if self._get_path_string(t) == keep_string]
        self._rebuild_tab_bar()
        self._switch_to_tab(keep_path_list)


    def _save_editor_content_to_vfs(self):
        """
        Retrieves content from the currently active editor and commits it to the VFS.
        """
        if not self.active_editor or not self.active_file_path:
            return

        # Check if the widget still exists before trying to access methods
        if not hasattr(self.active_editor, 'winfo_exists') or not self.active_editor.winfo_exists():
            return

        new_content = self.active_editor.get_content()
        self._set_file_content(self.active_file_path, new_content)


# --- Custom Dialog for File Creation (Unchanged logic, now accepts friendly names) ---

class NewFileCreationDialog(tk.Toplevel):
    """Modal dialog for users to input the base file name and select an allowed extension."""
    def __init__(self, parent, current_folder_name, allowed_file_types):
        super().__init__(parent)
        self.transient(parent)
        self.grab_set() 
        self.title("Create New File")
        self.parent = parent
        self.result = None 
        # allowed_file_types now holds the friendly display names (e.g., "Text Document")
        self.allowed_file_types = allowed_file_types 

        self.geometry("350x200")
        self.columnconfigure(0, weight=0)
        self.columnconfigure(1, weight=1)

        self._create_widgets(current_folder_name)
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        
        # Bind Enter and Escape keys
        self.bind('<Return>', lambda e: self.ok())
        self.bind('<Escape>', lambda e: self.cancel())
        
        self.wait_window(self)

    def _create_widgets(self, folder_name):
        ttk.Label(self, text=f"Folder:").grid(row=0, column=0, sticky="w", padx=10, pady=5)
        ttk.Label(self, text=folder_name, font=('Helvetica', 10, 'bold')).grid(row=0, column=1, sticky="w", padx=10, pady=5)
        
        ttk.Label(self, text=f"File Name (Base):").grid(row=1, column=0, sticky="w", padx=10, pady=5)
        self.name_entry = ttk.Entry(self)
        self.name_entry.grid(row=1, column=1, sticky="ew", padx=10, pady=5)
        
        ttk.Label(self, text="File Type:").grid(row=2, column=0, sticky="w", padx=10, pady=5)
        
        default_type = self.allowed_file_types[0] if self.allowed_file_types else "Text Document"
        self.file_type_var = tk.StringVar(value=default_type)
        
        if self.allowed_file_types:
            # Displays the friendly name, and stores the friendly name in file_type_var
            ttk.OptionMenu(self, self.file_type_var, default_type, *self.allowed_file_types).grid(row=2, column=1, sticky="ew", padx=10, pady=5)
        else:
            ttk.Label(self, text="No file types available.").grid(row=2, column=1, sticky="w", padx=10, pady=5)

        button_frame = ttk.Frame(self)
        button_frame.grid(row=3, column=0, columnspan=2, pady=10)
        
        ttk.Button(button_frame, text="OK", command=self.ok, width=10).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=self.cancel, width=10).pack(side=tk.LEFT, padx=5)
        
        self.name_entry.focus_set()
        self.bind("<Return>", lambda event: self.ok())
        self.bind("<Escape>", lambda event: self.cancel())


    def ok(self):
        base_name = self.name_entry.get().strip()
        # file_type_var contains the friendly name, which is mapped back in the caller
        file_type_selected = self.file_type_var.get() 

        if not base_name:
            messagebox.showerror("Error", "Please enter a file name.", parent=self)
            return

        self.result = {
            'base_name': base_name,
            'extension': file_type_selected
        }
        self.destroy()

    def cancel(self):
        self.result = None
        self.destroy()


class SettingsDialog(tk.Toplevel):
    """Settings dialog for application configuration."""
    def __init__(self, parent):
        super().__init__(parent)
        self.transient(parent)
        self.grab_set()
        self.title("Settings")
        self.parent = parent
        self.geometry("400x300")
        
        config = parent._load_config()
        
        # --- Settings Options ---
        container = ttk.Frame(self, padding="15")
        container.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(container, text="Settings", font=('Helvetica', 14, 'bold')).pack(anchor='w', pady=(0, 15))
        
        # Reopen last file on startup
        self.reopen_var = tk.StringVar(value=config.get("reopen_behavior", "ask"))
        reopen_frame = ttk.LabelFrame(container, text="On Startup", padding="10")
        reopen_frame.pack(fill=tk.X, pady=5)
        
        self._reopen_buttons = {}
        for value, label in [("always", "Always Reopen"), ("ask", "Ask to Reopen"), ("never", "Start Fresh")]:
            btn = ttk.Button(reopen_frame, text=label, 
                           command=lambda v=value: self._select_reopen(v))
            btn.pack(side=tk.LEFT, padx=5, pady=2)
            self._reopen_buttons[value] = btn
        
        self._update_reopen_buttons()
        
        # Window size
        size_frame = ttk.Frame(container)
        size_frame.pack(fill=tk.X, pady=5)
        ttk.Label(size_frame, text="Default window size:").pack(side=tk.LEFT)
        self.size_var = tk.StringVar(value=config.get("window_size", "1200x800"))
        ttk.Entry(size_frame, textvariable=self.size_var, width=12).pack(side=tk.LEFT, padx=10)
        
        # Fullscreen
        self.fullscreen_var = tk.BooleanVar(value=config.get("fullscreen", False))
        ttk.Checkbutton(container, text="Launch in fullscreen", 
                       variable=self.fullscreen_var).pack(anchor='w', pady=5)

        # Auto-collapse VFS
        self.auto_collapse_var = tk.BooleanVar(value=config.get("auto_collapse_vfs", False))
        ttk.Checkbutton(container, text="Auto-collapse file panel when opening a file",
                       variable=self.auto_collapse_var).pack(anchor='w', pady=5)
        
        # Buttons
        btn_frame = ttk.Frame(container)
        btn_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(15, 0))
        ttk.Button(btn_frame, text="Save", command=self._save).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="Cancel", command=self.destroy).pack(side=tk.RIGHT, padx=5)
        
        self.bind('<Escape>', lambda e: self.destroy())

    def _select_reopen(self, value):
        self.reopen_var.set(value)
        self._update_reopen_buttons()

    def _update_reopen_buttons(self):
        selected = self.reopen_var.get()
        style = ttk.Style()
        for value, btn in self._reopen_buttons.items():
            if value == selected:
                btn.state(['pressed'])
            else:
                btn.state(['!pressed'])

    def _save(self):
        config = self.parent._load_config()
        config["reopen_behavior"] = self.reopen_var.get()
        config["window_size"] = self.size_var.get()
        config["fullscreen"] = self.fullscreen_var.get()
        config["auto_collapse_vfs"] = self.auto_collapse_var.get()
        try:
            with open(self.parent.CONFIG_FILE, 'w') as f:
                json.dump(config, f, indent=2)
        except Exception:
            pass
        
        # Apply auto-collapse setting immediately
        self.parent._auto_collapse_vfs = self.auto_collapse_var.get()
        self.destroy()


# --- Link Utilities ---

def popup_menu(menu, x, y):
    """Post a context menu."""
    menu.tk_popup(x, y)

LINK_REGEX = re.compile(r'\[\[([^\]|]+)(?:\|([^\]]+))?\]\]')

def parse_links(text):
    """Extract links from text. Returns list of (start, end, path, display_text)."""
    results = []
    for m in LINK_REGEX.finditer(text):
        path = m.group(1)
        display = m.group(2) if m.group(2) else path.split('/')[-1]
        results.append((m.start(), m.end(), path, display))
    return results


class VFSFilePicker(tk.Toplevel):
    """Modal dialog to pick a file from the VFS tree."""
    def __init__(self, parent, vfs, root_name):
        super().__init__(parent)
        self.transient(parent)
        self.grab_set()
        self.title("Select File to Link")
        self.geometry("300x400")
        self.result = None

        self.tree = ttk.Treeview(self, show='tree')
        self.tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self._build_tree('', vfs.get(root_name, {}), root_name)
        self.tree.bind('<Double-1>', self._on_select)

        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Button(btn_frame, text="Select", command=self._on_select).pack(side=tk.RIGHT, padx=2)
        ttk.Button(btn_frame, text="Cancel", command=self.destroy).pack(side=tk.RIGHT, padx=2)

        self.bind('<Return>', lambda e: self._on_select())
        self.bind('<Escape>', lambda e: self.destroy())
        self.wait_window(self)

    def _build_tree(self, parent_id, node, name, path=""):
        current_path = f"{path}/{name}" if path else name
        item_id = self.tree.insert(parent_id, 'end', text=name, values=(current_path,))
        if node.get("type") == "dir":
            for child_name, child_node in node.get("children", {}).items():
                self._build_tree(item_id, child_node, child_name, current_path)

    def _on_select(self, event=None):
        sel = self.tree.selection()
        if not sel:
            return
        values = self.tree.item(sel[0], 'values')
        if values:
            path_string = values[0]
            # Check it's a file (no children in tree)
            if not self.tree.get_children(sel[0]):
                self.result = path_string
                self.destroy()


# --- Editor Widgets (Text, CSV, Timeline) ---

class TextEditor(ttk.Frame):
    """A rich text editor with bold, italic, underline formatting."""
    
    def __init__(self, master, initial_content="", controller=None):
        super().__init__(master)
        self.controller = controller
        
        # Formatting toolbar
        toolbar = ttk.Frame(self)
        toolbar.pack(fill=tk.X, pady=(0, 2))
        
        self._format_buttons = {}
        self._format_buttons['bold'] = ttk.Button(toolbar, text="B", width=3, command=lambda: (self._toggle_format('bold'), self.text_widget.focus_set()))
        self._format_buttons['bold'].pack(side=tk.LEFT, padx=1)
        self._add_tooltip(self._format_buttons['bold'], "Bold (Ctrl+B)")
        self._format_buttons['italic'] = ttk.Button(toolbar, text="I", width=3, command=lambda: (self._toggle_format('italic'), self.text_widget.focus_set()))
        self._format_buttons['italic'].pack(side=tk.LEFT, padx=1)
        self._add_tooltip(self._format_buttons['italic'], "Italic (Ctrl+I)")
        self._format_buttons['underline'] = ttk.Button(toolbar, text="U", width=3, command=lambda: (self._toggle_format('underline'), self.text_widget.focus_set()))
        self._format_buttons['underline'].pack(side=tk.LEFT, padx=1)
        self._add_tooltip(self._format_buttons['underline'], "Underline (Ctrl+U)")
        s_btn = ttk.Button(toolbar, text="S", width=3, command=lambda: (self._toggle_format('strikethrough'), self.text_widget.focus_set()))
        s_btn.pack(side=tk.LEFT, padx=1)
        self._add_tooltip(s_btn, "Strikethrough")
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=4)
        b_btn = ttk.Button(toolbar, text="• List", width=6, command=lambda: (self._toggle_bullet(), self.text_widget.focus_set()))
        b_btn.pack(side=tk.LEFT, padx=1)
        self._add_tooltip(b_btn, "Bullet List")
        n_btn = ttk.Button(toolbar, text="1. List", width=6, command=lambda: (self._toggle_numbered(), self.text_widget.focus_set()))
        n_btn.pack(side=tk.LEFT, padx=1)
        self._add_tooltip(n_btn, "Numbered List")
        
        # Find bar (initially hidden)
        self.find_frame = ttk.Frame(self)
        ttk.Label(self.find_frame, text="Find:").pack(side=tk.LEFT, padx=5)
        self.find_var = tk.StringVar()
        self.find_var.trace_add('write', lambda *args: self._do_find())
        self.find_entry = ttk.Entry(self.find_frame, textvariable=self.find_var, width=30)
        self.find_entry.pack(side=tk.LEFT, padx=5)
        ttk.Button(self.find_frame, text="✕", width=3, command=self._hide_find).pack(side=tk.LEFT)
        
        self.text_widget = tk.Text(self, wrap=tk.WORD, font=('Courier New', 10), undo=True)
        self.text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=2, pady=2)
        
        # Active format state for typing without selection
        self._active_formats = set()

        # Configure format tags
        self.text_widget.tag_configure('bold', font=('Courier New', 10, 'bold'))
        self.text_widget.tag_configure('italic', font=('Courier New', 10, 'italic'))
        self.text_widget.tag_configure('bold_italic', font=('Courier New', 10, 'bold italic'))
        self.text_widget.tag_configure('underline', underline=True)
        self.text_widget.tag_configure('strikethrough', overstrike=True)
        self.text_widget.tag_configure('link', foreground='#1565C0', underline=True)
        self.text_widget.tag_raise('bold_italic', 'bold')
        self.text_widget.tag_raise('bold_italic', 'italic')
        self.text_widget.tag_bind('link', '<Button-1>', self._on_link_click)
        self.text_widget.tag_bind('link', '<Enter>', lambda e: self.text_widget.config(cursor='hand2'))
        self.text_widget.tag_bind('link', '<Leave>', lambda e: self.text_widget.config(cursor=''))
        
        # Load content with markup
        self._load_markup(initial_content)
        self.text_widget.edit_reset()
        
        # Keyboard shortcuts
        self.text_widget.bind('<Control-b>', lambda e: self._toggle_format_key('bold'))
        self.text_widget.bind('<Control-i>', lambda e: self._toggle_format_key('italic'))
        self.text_widget.bind('<Control-u>', lambda e: self._toggle_format_key('underline'))
        self.text_widget.bind('<Control-z>', lambda e: self.text_widget.edit_undo())
        self.text_widget.bind('<Control-y>', lambda e: self.text_widget.edit_redo())
        self.text_widget.bind('<Control-a>', lambda e: self.text_widget.tag_add(tk.SEL, "1.0", tk.END))
        self.text_widget.bind('<Control-f>', lambda e: self._show_find())
        self.text_widget.bind('<Escape>', lambda e: self._hide_find())
        self.text_widget.bind('<Control-o>', lambda e: 'break')
        self.text_widget.bind('<Control-t>', lambda e: 'break')
        self.text_widget.bind('<Control-k>', lambda e: 'break')
        self.text_widget.bind('<Control-d>', lambda e: 'break')
        self.text_widget.bind('<ButtonRelease-3>', self._text_right_click)
        self.text_widget.bind('<Return>', self._on_enter)
        self.text_widget.bind('<KeyPress>', self._on_keypress)
        self.text_widget.bind('<Button-1>', self._on_click)
        self.text_widget.bind('<Tab>', self._on_tab)
        self.text_widget.bind('<BackSpace>', self._on_backspace)
            
        scrollbar = ttk.Scrollbar(self, command=self.text_widget.yview)
        self.text_widget.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def _renumber_line(self, line_num):
        """Recalculate and update the number on a numbered list line based on same-indent lines above."""
        line_text = self.text_widget.get(f"{line_num}.0", f"{line_num}.end")
        m = re.match(r'^(\t*)(\d+)\. ', line_text)
        if not m:
            return
        indent = m.group(1)
        indent_len = len(indent)
        # Count preceding same-indent numbered lines, skipping deeper-indented lines
        count = 1
        for prev in range(line_num - 1, 0, -1):
            prev_text = self.text_widget.get(f"{prev}.0", f"{prev}.end")
            pm = re.match(r'^(\t*)(\d+)\. ', prev_text)
            if pm:
                prev_indent_len = len(pm.group(1))
                if prev_indent_len == indent_len:
                    count += 1
                elif prev_indent_len < indent_len:
                    break  # hit a shallower level, stop
                # deeper indent: skip and keep looking
            else:
                # non-numbered line — stop unless it's blank or a bullet (which breaks the sequence)
                if prev_text.strip() == '' or re.match(r'^\s*• ', prev_text):
                    break
                break
        old_num = m.group(2)
        if str(count) != old_num:
            self.text_widget.delete(f"{line_num}.{indent_len}", f"{line_num}.{indent_len+len(old_num)}")
            self.text_widget.insert(f"{line_num}.{indent_len}", str(count))

    def _on_tab(self, event):
        """Indent bullet or numbered list line with Tab, or insert normal tab otherwise."""
        line = self.text_widget.get("insert linestart", "insert lineend")
        if re.match(r'^(\s*)(• |\d+\. )', line):
            self.text_widget.insert("insert linestart", "\t")
            if re.match(r'^(\s*)\d+\. ', line):
                line_num = int(self.text_widget.index("insert").split('.')[0])
                self._renumber_line(line_num)
            return 'break'

    def _on_backspace(self, event):
        """Outdent indented bullet/numbered list when backspacing the space after the prefix."""
        line_start = self.text_widget.index("insert linestart")
        cursor = self.text_widget.index("insert")
        m = re.match(r'^(\t+)(• |\d+\. )$', self.text_widget.get(line_start, cursor))
        if m:
            self.text_widget.delete(line_start, f"{line_start}+1c")
            if re.match(r'^\d+\. ', m.group(2)):
                line_num = int(self.text_widget.index("insert").split('.')[0])
                self._renumber_line(line_num)
            return 'break'

    def _on_shift_tab(self, event):
        """Outdent bullet point line with Shift-Tab."""
        line = self.text_widget.get("insert linestart", "insert lineend")
        m = re.match(r'^(  )(\s*• )', line)
        if m:
            self.text_widget.delete("insert linestart", "insert linestart+2c")
            return 'break'

    def _on_click(self, event):
        """Update active format state to match the format at the clicked position."""
        def update():
            idx = self.text_widget.index('insert-1c')
            tags = self.text_widget.tag_names(idx)
            self._active_formats = {t for t in ('bold', 'italic', 'underline') if t in tags}
            self._update_toolbar_state()
        self.text_widget.after(1, update)

    def _on_enter(self, event):
        """Continue bullet or numbered list prefix on new line, or remove prefix if line is empty."""
        line_start = self.text_widget.index("insert linestart")
        line_text = self.text_widget.get(line_start, "insert lineend")

        bullet_match = re.match(r'^(\s*)(• )', line_text)
        numbered_match = re.match(r'^(\t*)(\d+)\. ', line_text)

        if bullet_match:
            indent = bullet_match.group(1)
            # If the line is only the prefix (empty item), remove it and insert plain newline
            if line_text.strip() == '•':
                self.text_widget.delete(line_start, f"{line_start} lineend")
                return 'break'
            self.text_widget.insert('insert', f'\n{indent}• ')
            return 'break'
        elif numbered_match:
            indent = numbered_match.group(1)
            num = int(numbered_match.group(2))
            if line_text.strip() == f"{num}.":
                self.text_widget.delete(line_start, f"{line_start} lineend")
                return 'break'
            self.text_widget.insert('insert', f'\n{indent}1. ')
            # Now renumber the new line based on same-indent lines above it
            new_line_num = int(self.text_widget.index("insert").split('.')[0])
            self._renumber_line(new_line_num)
            return 'break'

    def _add_tooltip(self, widget, text):
        """Show a small tooltip label on hover after a short delay."""
        tip = None
        after_id = None
        def show(e):
            nonlocal tip, after_id
            def create():
                nonlocal tip
                tip = tk.Toplevel(widget)
                tip.wm_overrideredirect(True)
                tip.wm_geometry(f"+{e.x_root+10}+{e.y_root+20}")
                tk.Label(tip, text=text, background="#ffffe0", relief="solid", borderwidth=1,
                         font=('Helvetica', 8)).pack()
            after_id = widget.after(800, create)
        def hide(e):
            nonlocal tip, after_id
            if after_id:
                widget.after_cancel(after_id)
                after_id = None
            if tip:
                tip.destroy()
                tip = None
        widget.bind("<Enter>", show)
        widget.bind("<Leave>", hide)

    def _toggle_format_key(self, tag):
        """Keyboard shortcut handler — toggles format and returns 'break' to stop default behavior."""
        self._toggle_format(tag)
        return 'break'

    def _toggle_format(self, tag):
        """Toggle formatting on selection, or toggle active format state for future typing."""
        try:
            sel_start = self.text_widget.index(tk.SEL_FIRST)
            sel_end = self.text_widget.index(tk.SEL_LAST)
        except tk.TclError:
            # No selection — toggle active format state (not for strikethrough)
            if tag == 'strikethrough':
                return
            if tag in self._active_formats:
                self._active_formats.discard(tag)
            else:
                self._active_formats.add(tag)
            self._update_toolbar_state()
            return

        if tag in self.text_widget.tag_names(sel_start):
            self.text_widget.tag_remove(tag, sel_start, sel_end)
            if tag in ('bold', 'italic'):
                self.text_widget.tag_remove('bold_italic', sel_start, sel_end)
        else:
            self.text_widget.tag_add(tag, sel_start, sel_end)
            if tag == 'bold' and 'italic' in self.text_widget.tag_names(sel_start):
                self.text_widget.tag_add('bold_italic', sel_start, sel_end)
            elif tag == 'italic' and 'bold' in self.text_widget.tag_names(sel_start):
                self.text_widget.tag_add('bold_italic', sel_start, sel_end)

    def _update_toolbar_state(self):
        """Update toolbar button appearance to reflect active format state."""
        for tag, btn in getattr(self, '_format_buttons', {}).items():
            if tag in self._active_formats:
                btn.state(['pressed'])
            else:
                btn.state(['!pressed'])

    def _on_keypress(self, event):
        """Apply active formats to typed characters."""
        if not self._active_formats:
            return
        # Only handle printable characters, ignore control key combos
        if not event.char or event.char in ('\r', '\n') or event.state & 0x4:
            return
        # Insert the character manually with active tags applied
        tags = tuple(self._active_formats)
        if 'bold' in self._active_formats and 'italic' in self._active_formats:
            tags = tags + ('bold_italic',)
        self.text_widget.insert('insert', event.char, tags)
        return 'break'

    def _toggle_bullet(self):
        """Toggle bullet points on selected lines."""
        try:
            self.text_widget.index(tk.SEL_FIRST)
            self._toggle_line_prefix("• ", None)
        except tk.TclError:
            line = self.text_widget.get("insert linestart", "insert lineend")
            m_indent = re.match(r'^(\t*)', line)
            indent = m_indent.group(1)
            if re.match(r'^\t*• ', line):
                self.text_widget.delete("insert linestart", f"insert linestart+{len(indent)+2}c")
            else:
                self.text_widget.insert(f"insert linestart+{len(indent)}c", "• ")

    def _toggle_numbered(self):
        """Toggle numbered list on selected lines."""
        try:
            self.text_widget.index(tk.SEL_FIRST)
            self._toggle_line_prefix(None, "numbered")
        except tk.TclError:
            line = self.text_widget.get("insert linestart", "insert lineend")
            m_indent = re.match(r'^(\t*)', line)
            indent = m_indent.group(1)
            m = re.match(r'^\t*(\d+)\. ', line)
            if m:
                self.text_widget.delete("insert linestart", f"insert linestart+{len(indent)+len(m.group(1))+2}c")
            else:
                self.text_widget.insert(f"insert linestart+{len(indent)}c", "1. ")

    def _toggle_line_prefix(self, prefix, mode):
        """Add or remove line prefixes for lists, preserving formatting tags."""
        try:
            start_line = int(self.text_widget.index(tk.SEL_FIRST).split('.')[0])
            end_line = int(self.text_widget.index(tk.SEL_LAST).split('.')[0])
        except tk.TclError:
            start_line = int(self.text_widget.index(tk.INSERT).split('.')[0])
            end_line = start_line

        lines = []
        for i in range(start_line, end_line + 1):
            line = self.text_widget.get(f"{i}.0", f"{i}.end")
            lines.append(line)

        if mode == "numbered":
            all_numbered = all(re.match(r'^\d+\.\s', l) for l in lines if l.strip())
            for i, line_num in enumerate(range(start_line, end_line + 1)):
                line = self.text_widget.get(f"{line_num}.0", f"{line_num}.end")
                if all_numbered:
                    # Remove numbered prefix
                    m = re.match(r'^(\d+\.\s)', line)
                    if m:
                        self.text_widget.delete(f"{line_num}.0", f"{line_num}.{len(m.group(1))}")
                else:
                    # Remove existing prefix first
                    m = re.match(r'^([•]\s|\d+\.\s)', line)
                    if m:
                        self.text_widget.delete(f"{line_num}.0", f"{line_num}.{len(m.group(1))}")
                    # Insert new prefix
                    self.text_widget.insert(f"{line_num}.0", f"{i+1}. ")
        else:
            all_bulleted = all(l.startswith("• ") for l in lines if l.strip())
            for line_num in range(start_line, end_line + 1):
                line = self.text_widget.get(f"{line_num}.0", f"{line_num}.end")
                if all_bulleted:
                    # Remove bullet prefix
                    if line.startswith("• "):
                        self.text_widget.delete(f"{line_num}.0", f"{line_num}.2")
                else:
                    # Remove existing prefix first
                    m = re.match(r'^([•]\s|\d+\.\s)', line)
                    if m:
                        self.text_widget.delete(f"{line_num}.0", f"{line_num}.{len(m.group(1))}")
                    # Insert new prefix
                    self.text_widget.insert(f"{line_num}.0", "• ")

    def _load_markup(self, content):
        """Load content into the text widget. Supports JSON format and legacy markup."""
        self._links = {}
        if not content:
            return

        # Try JSON format first
        try:
            data = json.loads(content)
            if isinstance(data, dict) and "text" in data:
                self._load_json_format(data)
                return
        except (json.JSONDecodeError, ValueError):
            pass

        # Fallback: legacy markup format
        self._load_legacy_markup(content)

    def _load_json_format(self, data):
        """Load from JSON format: {text, tags, links}"""
        text = data["text"]
        self.text_widget.insert(tk.END, text)
        for entry in data.get("tags", []):
            tag = entry["tag"]
            start = f"1.0+{entry['start']}c"
            end = f"1.0+{entry['end']}c"
            if tag == "link":
                display = self.text_widget.get(start, end)
                self._links[display] = entry.get("path", display)
            self.text_widget.tag_add(tag, start, end)
            # Add bold_italic compound tag
            if tag == "bold":
                # Check if italic also covers this range
                for other in data.get("tags", []):
                    if other["tag"] == "italic":
                        overlap_start = max(entry["start"], other["start"])
                        overlap_end = min(entry["end"], other["end"])
                        if overlap_start < overlap_end:
                            self.text_widget.tag_add("bold_italic",
                                f"1.0+{overlap_start}c", f"1.0+{overlap_end}c")

    def _load_legacy_markup(self, content):
        """Parse old markdown-style markup content."""
        link_placeholders = []
        def replace_link(m):
            path = m.group(1)
            display = m.group(2) if m.group(2) else path.split('/')[-1]
            placeholder = f"\x00LINK{len(link_placeholders)}\x00"
            link_placeholders.append((display, path))
            return placeholder

        text = LINK_REGEX.sub(replace_link, content)

        markup_patterns = [
            ('strikethrough', r'~~', r'~~'),
            ('underline', r'__', r'__'),
            ('bold', r'\*\*', r'\*\*'),
            ('italic', r'(?<!\*)\*(?!\*)', r'(?<!\*)\*(?!\*)'),
        ]

        def parse_segment(s, inherited_tags):
            results = []
            best_match = None
            best_tag = None
            for tag, open_pat, close_pat in markup_patterns:
                if tag in inherited_tags:
                    continue
                full_pat = open_pat + r'(.+?)' + close_pat
                m = re.search(full_pat, s)
                if m:
                    if (best_match is None or
                        m.start() < best_match.start() or
                        (m.start() == best_match.start() and m.end() > best_match.end())):
                        best_match = m
                        best_tag = tag
            if best_match:
                if best_match.start() > 0:
                    results.extend(parse_segment(s[:best_match.start()], inherited_tags))
                results.extend(parse_segment(best_match.group(1), inherited_tags | {best_tag}))
                if best_match.end() < len(s):
                    results.extend(parse_segment(s[best_match.end():], inherited_tags))
                return results
            if s:
                results.append((s, inherited_tags))
            return results

        segments = parse_segment(text, set())

        for seg_text, tags in segments:
            parts = re.split(r'(\x00LINK\d+\x00)', seg_text)
            for part in parts:
                m = re.match(r'\x00LINK(\d+)\x00', part)
                if m:
                    idx = int(m.group(1))
                    display, path = link_placeholders[idx]
                    self._links[display] = path
                    tag_tuple = tuple(tags | {'link'})
                    self.text_widget.insert(tk.END, display, tag_tuple)
                elif part:
                    if 'bold' in tags and 'italic' in tags:
                        tag_tuple = tuple(tags | {'bold_italic'})
                    else:
                        tag_tuple = tuple(tags) if tags else ()
                    self.text_widget.insert(tk.END, part, tag_tuple)

    def _show_find(self):
        self.find_frame.pack(side=tk.TOP, fill=tk.X, pady=(0, 5), before=self.text_widget)
        self.find_entry.focus_set()
        self.find_entry.select_range(0, tk.END)
        
    def _hide_find(self):
        self.find_frame.pack_forget()
        self.text_widget.tag_remove("search", "1.0", tk.END)
        self.text_widget.focus_set()
        
    def _do_find(self):
        search_term = self.find_var.get()
        self.text_widget.tag_remove("search", "1.0", tk.END)
        if search_term:
            start = "1.0"
            while True:
                pos = self.text_widget.search(search_term, start, tk.END)
                if not pos:
                    break
                end = f"{pos}+{len(search_term)}c"
                self.text_widget.tag_add("search", pos, end)
                start = end
            self.text_widget.tag_config("search", background="yellow")
            first_pos = self.text_widget.search(search_term, "1.0", tk.END)
            if first_pos:
                self.text_widget.see(first_pos)

    def _text_right_click(self, event):
        """Right-click context menu for text editor."""
        idx = self.text_widget.index(f"@{event.x},{event.y}")
        menu = tk.Menu(self, tearoff=0)
        if 'link' in self.text_widget.tag_names(idx):
            menu.add_command(label="Remove Link", command=lambda: self._remove_link(idx))
            menu.add_separator()
        menu.add_command(label="Insert Link", command=self._insert_link)
        popup_menu(menu, event.x_root, event.y_root)

    def _remove_link(self, idx):
        """Remove the link tag from the link at idx, keeping the display text."""
        link_range = self.text_widget.tag_prevrange('link', f"{idx}+1c") or self.text_widget.tag_nextrange('link', idx)
        if link_range and self.text_widget.compare(link_range[0], '<=', idx) and self.text_widget.compare(link_range[1], '>=', idx):
            display = self.text_widget.get(link_range[0], link_range[1])
            self.text_widget.tag_remove('link', link_range[0], link_range[1])
            self._links.pop(display, None)

    def _insert_link(self):
        """Open file picker and insert a link at cursor position."""
        if not self.controller:
            return
        picker = VFSFilePicker(self, self.controller.vfs, self.controller.root_name)
        if picker.result:
            path = picker.result
            try:
                display = self.text_widget.get(tk.SEL_FIRST, tk.SEL_LAST)
                self.text_widget.delete(tk.SEL_FIRST, tk.SEL_LAST)
            except tk.TclError:
                display = path.split('/')[-1]
            if not hasattr(self, '_links'):
                self._links = {}
            self._links[display] = path
            self.text_widget.insert(tk.INSERT, display, ('link',))

    def _on_link_click(self, event):
        """Handle click on a link tag — find the link path and open the file."""
        if not self.controller:
            return
        index = self.text_widget.index(f"@{event.x},{event.y}")
        link_range = self.text_widget.tag_prevrange('link', index + '+1c')
        if not link_range:
            return
        display_text = self.text_widget.get(link_range[0], link_range[1])
        path = getattr(self, '_links', {}).get(display_text)
        if path:
            path_list = path.split('/')
            self.controller._open_file_editor(path_list)

    def get_content(self):
        """Serialize editor content as JSON with text and tag ranges."""
        end = self.text_widget.index(tk.END + "-1c")
        if self.text_widget.compare("1.0", ">=", end):
            return ""

        text = self.text_widget.get("1.0", end)
        format_tags = ('bold', 'italic', 'underline', 'strikethrough', 'link')
        tags_list = []

        for tag in format_tags:
            search_start = "1.0"
            while True:
                nr = self.text_widget.tag_nextrange(tag, search_start, end)
                if not nr:
                    break
                start_offset = len(self.text_widget.get("1.0", nr[0]))
                end_offset = len(self.text_widget.get("1.0", nr[1]))
                entry = {"tag": tag, "start": start_offset, "end": end_offset}
                if tag == "link":
                    display = self.text_widget.get(nr[0], nr[1])
                    entry["path"] = getattr(self, '_links', {}).get(display, display)
                tags_list.append(entry)
                search_start = nr[1]

        return json.dumps({"text": text, "tags": tags_list})

class TimelineEditor(ttk.Frame):
    """
    A hierarchical timeline editor with configurable time units and named periods.
    """
    def __init__(self, master, initial_content="", controller=None):
        super().__init__(master)
        self.controller = controller
        
        # Timeline configuration
        self.config_data = {
            "time_units": {
                "ages": {"count": 10, "names": {}, "years_per_age": {}},
                "years": {"count": 100, "names": {}},
                "months": {"count": 12, "names": {}}, 
                "days_of_month": {"count": 30, "names": {}},
                "days_of_week": {"count": 7, "names": {}}
            },
            "bc_ad_enabled": False,
            "bc_label": "BC",
            "ad_label": "AD",
            "day_week_offset": 0,
            "visible_units": {
                "ages": True,
                "years": True,
                "months": True,
                "days_of_week": True,
                "days_of_month": True
            },
            "events": []
        }
        
        # Current time position
        self.current_age = tk.IntVar(value=1)
        self.current_year = tk.IntVar(value=1)
        self.current_year.trace_add('write', self._handle_year_zero)
        self.current_month = tk.IntVar(value=1) 
        self.current_day_of_week = tk.IntVar(value=1)
        self.current_day_of_month = tk.IntVar(value=1)
        
        self._load_content(initial_content)
        self._create_widgets()
        self._populate_events()
        self._update_display()

    def _load_content(self, content):
        """Load timeline data from JSON content."""
        if content:
            try:
                data = json.loads(content)
                if isinstance(data, dict):
                    # Migrate old format to new format
                    if "time_units" in data:
                        self.config_data = data
                        # Remove legacy 'days' entry if it exists
                        if "days" in self.config_data["time_units"]:
                            del self.config_data["time_units"]["days"]
                        # Ensure all required time units exist
                        required_units = ["ages", "years", "months", "days_of_week", "days_of_month"]
                        for unit in required_units:
                            if unit not in self.config_data["time_units"]:
                                if unit == "days_of_week":
                                    self.config_data["time_units"][unit] = {"count": 7, "names": {}}
                                elif unit == "days_of_month":
                                    self.config_data["time_units"][unit] = {"count": 30, "names": {}}
                                else:
                                    self.config_data["time_units"][unit] = {"count": 10, "names": {}}
                        # Ensure BC/AD fields exist
                        if "bc_ad_enabled" not in self.config_data:
                            self.config_data["bc_ad_enabled"] = False
                        if "bc_label" not in self.config_data:
                            self.config_data["bc_label"] = "BC"
                        if "ad_label" not in self.config_data:
                            self.config_data["ad_label"] = "AD"
                        if "day_week_offset" not in self.config_data:
                            self.config_data["day_week_offset"] = 0
                        if "visible_units" not in self.config_data:
                            self.config_data["visible_units"] = {
                                "ages": True, "years": True, "months": True,
                                "days_of_week": True, "days_of_month": True
                            }
                    else:
                        # Very old format, use events only
                        self.config_data["events"] = data.get("events", [])
            except json.JSONDecodeError:
                pass

    def _create_widgets(self):
        """Create the timeline interface."""
        
        # Configuration Section
        config_header_frame = ttk.Frame(self)
        config_header_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.config_collapsed = tk.BooleanVar(value=True)  # Start collapsed
        self.config_toggle_btn = ttk.Button(config_header_frame, text="▶ Time Configuration", 
                                           command=self._toggle_config_panel)
        self.config_toggle_btn.pack(side=tk.LEFT)
        
        self.config_frame = ttk.Frame(self, padding="10")
        # Don't pack initially - will be packed/unpacked by toggle
        
        # Time unit configuration
        units_frame = ttk.Frame(self.config_frame)
        units_frame.pack(fill=tk.X)
        
        # Force specific display order
        unit_order = ["ages", "years", "months", "days_of_month", "days_of_week"]
        
        for i, unit in enumerate(unit_order):
            if unit in self.config_data["time_units"]:
                data = self.config_data["time_units"][unit]
                
                # Checkbox for visibility
                visible_var = tk.BooleanVar(value=self.config_data.get("visible_units", {}).get(unit, True))
                setattr(self, f"{unit}_visible_var", visible_var)
                visible_var.trace_add('write', lambda *args, u=unit: self._toggle_unit_visibility(u))
                checkbox = ttk.Checkbutton(units_frame, variable=visible_var)
                checkbox.grid(row=i, column=0, padx=5)
                setattr(self, f"{unit}_checkbox", checkbox)  # Store reference
                
                lbl = ttk.Label(units_frame, text=f"{unit.replace('_', ' ').title()}:")
                lbl.grid(row=i, column=1, sticky="w", padx=5)
                setattr(self, f"{unit}_label", lbl)
                
                count_var = tk.IntVar(value=data["count"])
                setattr(self, f"{unit}_count_var", count_var)
                count_var.trace_add('write', lambda *args: self._update_ranges())
                count_spinbox = ttk.Spinbox(units_frame, from_=1, to=999999, width=8, textvariable=count_var)
                count_spinbox.grid(row=i, column=2, padx=5)
                setattr(self, f"{unit}_count_spinbox", count_spinbox)
                
                # Special handling for day naming buttons with mutual exclusion
                if unit in ["days_of_week", "days_of_month"]:
                    btn = ttk.Button(units_frame, text=f"Name {unit.replace('_', ' ').title()}", 
                                   command=lambda u=unit: self._configure_day_names(u))
                    btn.grid(row=i, column=3, padx=5)
                    setattr(self, f"{unit}_name_btn", btn)
                elif unit == "ages":
                    btn = ttk.Button(units_frame, text="Configure Ages", 
                                   command=lambda u=unit: self._configure_ages())
                    btn.grid(row=i, column=3, padx=5)
                    setattr(self, f"{unit}_name_btn", btn)
                    # Epochal dating checkbox — hidden until epochal mode is active
                    epochal_var = tk.BooleanVar(value=self.config_data.get("bc_ad_enabled", False))
                    self.epochal_visible_var = epochal_var
                    self.epochal_checkbox = ttk.Checkbutton(units_frame, variable=epochal_var,
                                                            command=self._on_epochal_checkbox)
                    self.epochal_checkbox.grid(row=i, column=0, padx=5)
                    self.epochal_label = ttk.Label(units_frame, text="Epochal Dating:")
                    self.epochal_label.grid(row=i, column=1, sticky="w", padx=5)
                    # Show ages or epochal widgets based on current state
                    if self.config_data.get("bc_ad_enabled", False):
                        checkbox.grid_remove()
                        lbl.grid_remove()
                    else:
                        self.epochal_checkbox.grid_remove()
                        self.epochal_label.grid_remove()
                elif unit != "years":  # Skip creating button for years
                    btn = ttk.Button(units_frame, text=f"Name {unit.replace('_', ' ').title()}", 
                                   command=lambda u=unit: self._configure_names(u))
                    btn.grid(row=i, column=3, padx=5)
                    setattr(self, f"{unit}_name_btn", btn)
                
                # Add offset control for days of week
                if unit == "days_of_week":
                    ttk.Label(units_frame, text="Offset:", foreground="gray").grid(row=i, column=4, padx=5)
                    self.day_week_offset_var = tk.IntVar(value=self.config_data.get("day_week_offset", 0))
                    self.day_week_offset_var.trace_add('write', self._update_day_week_offset)
                    self.offset_spinbox = ttk.Spinbox(units_frame, from_=-99, to=99, width=6, 
                                                     textvariable=self.day_week_offset_var, state="disabled")
                    self.offset_spinbox.grid(row=i, column=5, padx=5)
        
        # BC/AD vars (controlled via Configure Ages dialog only)
        self.bc_ad_var = tk.BooleanVar(value=self.config_data.get("bc_ad_enabled", False))
        self.bc_var = tk.StringVar(value=self.config_data.get("bc_label", "BC"))
        self.bc_var.trace_add('write', self._update_bc_ad_labels)
        self.ad_var = tk.StringVar(value=self.config_data.get("ad_label", "AD"))
        self.ad_var.trace_add('write', self._update_bc_ad_labels)
        self.bc_years_var = tk.IntVar(value=self.config_data.get("bc_years", 100))
        self.bc_years_var.trace_add('write', self._update_bc_ad_years)
        self.ad_years_var = tk.IntVar(value=self.config_data.get("ad_years", 100))
        self.ad_years_var.trace_add('write', self._update_bc_ad_years)
        # Stub widget refs so existing code doesn't break
        self.bc_ad_checkbox = None
        self.bc_entry = None
        self.ad_entry = None
        self.bc_years_spinbox = None
        self.ad_years_spinbox = None

        # Time Scrubber Section  
        scrubber_frame = ttk.LabelFrame(self, text="Time Navigator", padding="10")
        scrubber_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Current time display
        self.time_display = ttk.Label(scrubber_frame, text="", font=('Helvetica', 14, 'bold'))
        self.time_display.pack(pady=5)
        
        # Master timeline scrubber
        master_frame = ttk.Frame(scrubber_frame)
        master_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(master_frame, text="Master Timeline:").pack(side=tk.LEFT, padx=(0, 5))
        self.master_timeline_var = tk.IntVar(value=0)
        self.master_timeline_scale = ttk.Scale(master_frame, from_=0, to=1000000, orient=tk.HORIZONTAL,
                                              variable=self.master_timeline_var, command=self._update_from_master_timeline)
        self.master_timeline_scale.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.master_timeline_scale.bind("<MouseWheel>", lambda e: self._scroll_master_timeline(e))
        
        # Update master timeline range
        self._update_master_timeline_range()
        
        # Hierarchical scrubbers
        controls_frame = ttk.Frame(scrubber_frame)
        controls_frame.pack(fill=tk.X)
        self.controls_frame = controls_frame  # Store reference for visibility management
        
        # Age scrubber
        ttk.Label(controls_frame, text="Age:").grid(row=0, column=0, padx=5)
        self.age_scale = ttk.Scale(controls_frame, from_=1, to=10, orient=tk.HORIZONTAL,
                                  variable=self.current_age, command=self._update_age_change)
        self.age_scale.grid(row=0, column=1, sticky="ew", padx=5)
        self.age_scale.bind("<MouseWheel>", lambda e: self._scroll_scale(e, self.current_age))
        
        # Year scrubber
        ttk.Label(controls_frame, text="Year:").grid(row=1, column=0, padx=5)
        year_count = self.config_data["time_units"]["years"]["count"]
        if self.config_data.get("bc_ad_enabled", False):
            # Use separate BC and AD year ranges
            bc_years = self.config_data.get("bc_years", 100)
            ad_years = self.config_data.get("ad_years", 100)
            year_from = -bc_years
            year_to = ad_years
        else:
            year_from = 1
            year_to = year_count
        self.year_scale = ttk.Scale(controls_frame, from_=year_from, to=year_to, orient=tk.HORIZONTAL,
                                   variable=self.current_year, command=self._update_day_of_month)
        self.year_scale.grid(row=1, column=1, sticky="ew", padx=5)
        self.year_scale.bind("<MouseWheel>", lambda e: self._scroll_scale(e, self.current_year))
        
        # Month scrubber  
        ttk.Label(controls_frame, text="Month:").grid(row=2, column=0, padx=5)
        self.month_scale = ttk.Scale(controls_frame, from_=1, to=12, orient=tk.HORIZONTAL,
                                    variable=self.current_month, command=self._update_day_of_month)
        self.month_scale.grid(row=2, column=1, sticky="ew", padx=5)
        self.month_scale.bind("<MouseWheel>", lambda e: self._scroll_scale(e, self.current_month))
        
        # Day of month scrubber
        ttk.Label(controls_frame, text="Day of Month:").grid(row=3, column=0, padx=5)
        self.day_month_scale = ttk.Scale(controls_frame, from_=1, to=30, orient=tk.HORIZONTAL, 
                                        variable=self.current_day_of_month, command=self._update_day_of_month)
        self.day_month_scale.grid(row=3, column=1, sticky="ew", padx=5)
        self.day_month_scale.bind("<MouseWheel>", lambda e: self._scroll_scale(e, self.current_day_of_month))
        
        controls_frame.columnconfigure(1, weight=1)
        
        # Events Section
        events_frame = ttk.LabelFrame(self, text="Timeline Events", padding="10")
        events_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Hotkey legend
        legend_frame = ttk.Frame(events_frame)
        legend_frame.pack(fill=tk.X, pady=(0, 5))
        
        legend_text = "Hotkeys: Enter=Edit Event | Shift+Enter=New Event | Del=Delete Event | Right-Click=Go to Event Date"
        ttk.Label(legend_frame, text=legend_text, font=('Helvetica', 8), foreground='gray').pack()
        
        # Event management buttons
        btn_frame = ttk.Frame(events_frame)
        btn_frame.pack(fill=tk.X, pady=(0,5))
        
        ttk.Button(btn_frame, text="Add Event", command=self._add_event).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Edit Event", command=self._edit_event).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Delete Event", command=self._delete_event).pack(side=tk.LEFT, padx=2)
        
        # Events tree with scrollbar
        tree_frame = ttk.Frame(events_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        tree_frame.pack_propagate(False)
        
        self.events_tree = ttk.Treeview(tree_frame, columns=('Start Time', 'End Time', 'Description'), show='tree headings')
        self.events_tree.heading('#0', text='Event Name')
        self.events_tree.heading('Start Time', text='Start Time')
        self.events_tree.heading('End Time', text='End Time')
        self.events_tree.heading('Description', text='Description')
        
        events_scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.events_tree.yview)
        events_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.events_tree.configure(yscrollcommand=events_scrollbar.set)
        self.events_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Bind hotkeys to the events tree
        self.events_tree.bind('<Return>', self._hotkey_edit_event)
        self.events_tree.bind('<Shift-Return>', self._hotkey_add_event)
        self.events_tree.bind('<Delete>', self._hotkey_delete_event)
        self.events_tree.bind('<ButtonRelease-3>', self._on_event_right_click)
        
        # Explicitly bind arrow keys to ensure navigation works
        self.events_tree.bind('<Up>', self._navigate_up)
        self.events_tree.bind('<Down>', self._navigate_down)
        self.events_tree.bind('<Left>', self._navigate_left)
        self.events_tree.bind('<Right>', self._navigate_right)
        
        self.events_tree.focus_set()  # Allow tree to receive key events

        # Initialize BC/AD state after all widgets are created
        self._toggle_bc_ad()
        # Restore epochal label if already configured
        if self.config_data.get("bc_ad_enabled", False):
            ages_checkbox = getattr(self, "ages_checkbox", None)
            ages_label = getattr(self, "ages_label", None)
            if ages_checkbox: ages_checkbox.grid_remove()
            if ages_label: ages_label.grid_remove()
            ec = getattr(self, "epochal_checkbox", None)
            el = getattr(self, "epochal_label", None)
            if ec: ec.grid()
            if el: el.grid()
            ages_count_spinbox = getattr(self, "ages_count_spinbox", None)
            ages_name_btn = getattr(self, "ages_name_btn", None)
            if ages_count_spinbox: ages_count_spinbox.config(state="disabled")
            # Force years enabled under epochal dating
            self.config_data["visible_units"]["years"] = True
            years_visible_var = getattr(self, "years_visible_var", None)
            if years_visible_var: years_visible_var.set(True)
            years_checkbox = getattr(self, "years_checkbox", None)
            years_count_spinbox = getattr(self, "years_count_spinbox", None)
            if years_checkbox: years_checkbox.config(state="disabled")
            if years_count_spinbox: years_count_spinbox.config(state="disabled")
        self._update_navigator_visibility()
        
        # Initialize visibility states for all units
        unit_order = ["ages", "years", "months", "days_of_month", "days_of_week"]
        for unit in unit_order:
            if unit in self.config_data["time_units"]:
                self._toggle_unit_visibility(unit)

    def _toggle_config_panel(self):
        """Toggle the visibility of the configuration panel."""
        if self.config_collapsed.get():
            # Expand
            self.config_frame.pack(fill=tk.X, padx=5, pady=(0, 5))
            self.config_toggle_btn.config(text="▼ Time Configuration")
            self.config_collapsed.set(False)
        else:
            # Collapse
            self.config_frame.pack_forget()
            self.config_toggle_btn.config(text="▶ Time Configuration")
            self.config_collapsed.set(True)

    def _update_ranges(self):
        """Update scrubber ranges based on configuration."""
        self.age_scale.config(to=self.ages_count_var.get())
        
        # Update year range based on BC/AD setting
        if self.config_data.get("bc_ad_enabled", False):
            bc_years = self.config_data.get("bc_years", 100)
            ad_years = self.config_data.get("ad_years", 100)
            self.year_scale.config(from_=-bc_years, to=ad_years)
            # Ensure current year is not 0
            if self.current_year.get() == 0:
                self.current_year.set(1)
        else:
            # Check if ages are enabled and get years for current age
            visible_units = self.config_data.get("visible_units", {})
            if visible_units.get("ages", True):
                current_age = int(self.current_age.get())
                years_in_current_age = self.config_data["time_units"]["ages"].get("years_per_age", {}).get(str(current_age), 100)
                self.year_scale.config(from_=1, to=years_in_current_age)
            else:
                year_count = self.years_count_var.get()
                self.year_scale.config(from_=1, to=year_count)
            
        self.month_scale.config(to=self.months_count_var.get())
        self.day_month_scale.config(to=self.days_of_month_count_var.get())
        
        # Update config data
        self.config_data["time_units"]["ages"]["count"] = self.ages_count_var.get()
        self.config_data["time_units"]["years"]["count"] = self.years_count_var.get()
        self.config_data["time_units"]["months"]["count"] = self.months_count_var.get()
        self.config_data["time_units"]["days_of_week"]["count"] = self.days_of_week_count_var.get()
        self.config_data["time_units"]["days_of_month"]["count"] = self.days_of_month_count_var.get()
        
        # Update Time Navigator display
        self._update_display()
        # Recalculate day of week based on new configuration
        self._update_day_of_month()

    def _update_bc_ad_labels(self, *args):
        """Update BC/AD labels in real-time as user types."""
        if self.config_data.get("bc_ad_enabled", False):
            self.config_data["bc_label"] = self.bc_var.get()
            self.config_data["ad_label"] = self.ad_var.get()
            self._update_display()

    def _update_bc_ad_years(self, *args):
        """Update BC/AD years in config when spinbox values change."""
        if self.config_data.get("bc_ad_enabled", False):
            self.config_data["bc_years"] = self.bc_years_var.get()
            self.config_data["ad_years"] = self.ad_years_var.get()
            self._update_ranges()

    def _toggle_unit_visibility(self, unit):
        """Toggle visibility of time unit and update UI state."""
        visible_var = getattr(self, f"{unit}_visible_var")
        visible = visible_var.get()
        
        # Update config
        if "visible_units" not in self.config_data:
            self.config_data["visible_units"] = {}
        self.config_data["visible_units"][unit] = visible
        
        # Enable/disable controls
        state = "normal" if visible else "disabled"
        count_spinbox = getattr(self, f"{unit}_count_spinbox", None)
        name_btn = getattr(self, f"{unit}_name_btn", None)
        
        if count_spinbox:
            count_spinbox.config(state=state)
        if name_btn and unit != "years" and unit != "ages":  # Don't disable Name Years or Configure Ages button
            name_btn.config(state=state)
        
        # Special handling for days of week offset
        if unit == "days_of_week" and hasattr(self, 'offset_spinbox'):
            if visible:
                # Check if both days of week and days of month are enabled, and days are named
                visible_units = self.config_data.get("visible_units", {})
                days_of_month_enabled = visible_units.get("days_of_month", True)
                day_names = self.config_data["time_units"]["days_of_week"]["names"]
                has_day_names = any(name.strip() for name in day_names.values())
                
                offset_state = "normal" if (days_of_month_enabled and has_day_names) else "disabled"
                self.offset_spinbox.config(state=offset_state)
            else:
                self.offset_spinbox.config(state="disabled")
        
        # Also update offset when days of month visibility changes
        if unit == "days_of_month" and hasattr(self, 'offset_spinbox'):
            visible_units = self.config_data.get("visible_units", {})
            days_of_week_enabled = visible_units.get("days_of_week", True)
            day_names = self.config_data["time_units"]["days_of_week"]["names"]
            has_day_names = any(name.strip() for name in day_names.values())
            
            offset_state = "normal" if (visible and days_of_week_enabled and has_day_names) else "disabled"
            self.offset_spinbox.config(state=offset_state)
        
        # Update navigator display
        self._update_navigator_visibility()
        self._update_display()

    def _update_navigator_visibility(self):
        """Update visibility of navigator controls based on configuration."""
        visible_units = self.config_data.get("visible_units", {})
        ages_enabled = visible_units.get("ages", True)
        years_enabled = visible_units.get("years", True)
        
        # Store widget pairs for easier management
        widget_pairs = []
        if hasattr(self, 'age_scale') and ages_enabled:
            # Find age label - show when Ages checkbox is checked
            for widget in self.controls_frame.winfo_children():
                if isinstance(widget, ttk.Label) and widget.cget("text") == "Age:":
                    widget_pairs.append(("ages", widget, self.age_scale))
                    break
        
        if hasattr(self, 'year_scale') and years_enabled:
            # Find year label - show when Years checkbox is checked
            for widget in self.controls_frame.winfo_children():
                if isinstance(widget, ttk.Label) and widget.cget("text") == "Year:":
                    widget_pairs.append(("years", widget, self.year_scale))
                    break
        
        if hasattr(self, 'month_scale'):
            # Find month label - show when Months checkbox is checked
            for widget in self.controls_frame.winfo_children():
                if isinstance(widget, ttk.Label) and widget.cget("text") == "Month:":
                    if visible_units.get("months", True):
                        widget_pairs.append(("months", widget, self.month_scale))
                    break
        
        if hasattr(self, 'day_month_scale'):
            # Find day of month label - show when Days of Month checkbox is checked
            for widget in self.controls_frame.winfo_children():
                if isinstance(widget, ttk.Label) and widget.cget("text") == "Day of Month:":
                    if visible_units.get("days_of_month", True):
                        widget_pairs.append(("days_of_month", widget, self.day_month_scale))
                    break
        
        # Hide all widgets first
        for widget in self.controls_frame.winfo_children():
            widget.grid_remove()
        
        # Show visible widgets in condensed layout
        row = 0
        for unit, label, scale in widget_pairs:
            label.grid(row=row, column=0, padx=5)
            scale.grid(row=row, column=1, sticky="ew", padx=5)
            row += 1

    def _update_master_timeline_range(self):
        """Calculate and set the range for the master timeline scrubber."""
        months_per_year = self.config_data["time_units"]["months"]["count"]
        days_per_month = self.config_data["time_units"]["days_of_month"]["count"]
        
        if self.config_data.get("bc_ad_enabled", False):
            # For BC/AD, calculate total range from BC years to AD years, accounting for no year 0
            bc_years = self.config_data.get("bc_years", 100)
            ad_years = self.config_data.get("ad_years", 100)
            
            # Set range from negative BC days to positive AD days (minus 1 to account for no year 0)
            min_days = -bc_years * months_per_year * days_per_month
            max_days = (ad_years - 1) * months_per_year * days_per_month + (months_per_year * days_per_month - 1)
            self.master_timeline_scale.config(from_=min_days, to=max_days)
        else:
            # For ages system, calculate as before
            ages_count = self.config_data["time_units"]["ages"]["count"]
            total_days = 0
            for age in range(1, ages_count + 1):
                years_in_age = self.config_data["time_units"]["ages"].get("years_per_age", {}).get(str(age), 100)
                total_days += years_in_age * months_per_year * days_per_month
            
            self.master_timeline_scale.config(from_=0, to=max(total_days - 1, 1))

    def _get_cumulative_days(self):
        """Get current cumulative days from timeline position."""
        day_of_month = int(self.current_day_of_month.get())
        month = int(self.current_month.get())
        year = int(self.current_year.get())
        days_per_month = self.config_data["time_units"]["days_of_month"]["count"]
        months_per_year = self.config_data["time_units"]["months"]["count"]
        
        if self.config_data.get("bc_ad_enabled", False):
            # For BC/AD, account for skipping year 0
            if year > 0:
                # AD years: subtract 1 from year to account for no year 0
                adjusted_year = year - 1
                cumulative_days = (adjusted_year * months_per_year * days_per_month + 
                                  (month - 1) * days_per_month + (day_of_month - 1))
            else:
                # BC years: use year directly (already negative)
                cumulative_days = (year * months_per_year * days_per_month + 
                                  (month - 1) * days_per_month + (day_of_month - 1))
        else:
            # For ages system, calculate as before
            age = int(self.current_age.get())
            
            # Calculate cumulative years from all previous ages
            cumulative_years_from_ages = 0
            for prev_age in range(1, age):
                years_in_prev_age = self.config_data["time_units"]["ages"].get("years_per_age", {}).get(str(prev_age), 100)
                cumulative_years_from_ages += years_in_prev_age
            
            year_offset = year - 1 if year > 0 else year
            cumulative_days = (cumulative_years_from_ages * months_per_year * days_per_month +
                              year_offset * months_per_year * days_per_month + 
                              (month - 1) * days_per_month + (day_of_month - 1))
        
        return cumulative_days

    def _set_from_cumulative_days(self, cumulative_days):
        """Set timeline position from cumulative days."""
        days_per_month = self.config_data["time_units"]["days_of_month"]["count"]
        months_per_year = self.config_data["time_units"]["months"]["count"]
        days_per_year = months_per_year * days_per_month
        
        remaining_days = cumulative_days
        
        if self.config_data.get("bc_ad_enabled", False):
            # BC/AD system
            if remaining_days < 0:
                # BC years
                year = remaining_days // days_per_year
                remaining_days = remaining_days % days_per_year
            else:
                # AD years (add 1 to account for no year 0)
                year = (remaining_days // days_per_year) + 1
                remaining_days = remaining_days % days_per_year
            
            age = 1  # Not used in BC/AD mode
        else:
            # Ages system - find the age
            age = 1
            ages_count = self.config_data["time_units"]["ages"]["count"]
            for current_age in range(1, ages_count + 1):
                years_in_age = self.config_data["time_units"]["ages"].get("years_per_age", {}).get(str(current_age), 100)
                days_in_age = years_in_age * days_per_year
                
                if remaining_days < days_in_age:
                    age = current_age
                    break
                remaining_days -= days_in_age
            
            # Find year within age
            year = (remaining_days // days_per_year) + 1
            remaining_days = remaining_days % days_per_year
        
        # Find month within year
        month = (remaining_days // days_per_month) + 1
        remaining_days = remaining_days % days_per_month
        
        # Find day within month
        day_of_month = remaining_days + 1
        
        # Update scrubbers without triggering callbacks
        self.current_age.set(age)
        self.current_year.set(year)
        self.current_month.set(month)
        self.current_day_of_month.set(day_of_month)

    def _update_from_master_timeline(self, *args):
        """Update individual scrubbers from master timeline position."""
        self._updating_from_master = True
        cumulative_days = int(self.master_timeline_var.get())
        self._set_from_cumulative_days(cumulative_days)
        
        # Update year range for the new age
        visible_units = self.config_data.get("visible_units", {})
        if visible_units.get("ages", True) and not self.config_data.get("bc_ad_enabled", False):
            current_age = int(self.current_age.get())
            years_in_current_age = self.config_data["time_units"]["ages"].get("years_per_age", {}).get(str(current_age), 100)
            self.year_scale.config(from_=1, to=years_in_current_age)
        
        self._update_day_of_month()
        self._updating_from_master = False

    def _scroll_master_timeline(self, event):
        """Handle mouse wheel scrolling on master timeline."""
        current = self.master_timeline_var.get()
        new_value = current + 1 if event.delta > 0 else current - 1
        
        min_val = self.master_timeline_scale.cget('from')
        max_val = self.master_timeline_scale.cget('to')
        
        if min_val <= new_value <= max_val:
            self.master_timeline_var.set(new_value)
            self._update_from_master_timeline()

    def _update_age_change(self, *args):
        """Handle age changes and update year range accordingly."""
        # Update year range for the new age
        visible_units = self.config_data.get("visible_units", {})
        if visible_units.get("ages", True) and not self.config_data.get("bc_ad_enabled", False):
            current_age = int(self.current_age.get())
            years_in_current_age = self.config_data["time_units"]["ages"].get("years_per_age", {}).get(str(current_age), 100)
            self.year_scale.config(from_=1, to=years_in_current_age)
            
            # Reset year to 1 if current year exceeds the new age's year limit
            if self.current_year.get() > years_in_current_age:
                self.current_year.set(1)
        
        # Update master timeline range since age configuration affects total timeline
        self._update_master_timeline_range()
        self._update_day_of_month()

    def _scroll_scale(self, event, var):
        """Handle mouse wheel scrolling on scale widgets."""
        current = var.get()
        new_value = current + 1 if event.delta > 0 else current - 1
        
        # Special handling for year scrolling when BC/AD is enabled
        if var == self.current_year and self.config_data.get("bc_ad_enabled", False):
            if current == 1 and event.delta < 0:  # Going from 1 AD to BC
                new_value = -1  # Skip year 0, go to 1 BC
            elif current == -1 and event.delta > 0:  # Going from 1 BC to AD
                new_value = 1  # Skip year 0, go to 1 AD
        
        # Get the scale widget's min/max values
        if var == self.current_age:
            scale = self.age_scale
        elif var == self.current_year:
            scale = self.year_scale
        elif var == self.current_month:
            scale = self.month_scale
        elif var == self.current_day_of_month:
            scale = self.day_month_scale
        else:
            return
            
        min_val = scale.cget('from')
        max_val = scale.cget('to')
        
        if min_val <= new_value <= max_val:
            var.set(new_value)
            # Call appropriate update method based on which variable changed
            if var == self.current_age:
                self._update_age_change()
            else:
                self._update_day_of_month()

    def _update_day_week_offset(self, *args):
        """Update day week offset and recalculate day of week."""
        self.config_data["day_week_offset"] = self.day_week_offset_var.get()
        self._update_day_of_month()

    def _update_day_of_month(self, *args):
        """Update day of month and calculate corresponding day of week."""
        day_of_month = int(self.current_day_of_month.get())
        month = int(self.current_month.get())
        year = int(self.current_year.get())
        age = int(self.current_age.get())
        days_per_week = self.config_data["time_units"]["days_of_week"]["count"]
        days_per_month = self.config_data["time_units"]["days_of_month"]["count"]
        months_per_year = self.config_data["time_units"]["months"]["count"]
        offset = self.config_data.get("day_week_offset", 0)
        
        # Calculate cumulative days from start of timeline
        if self.config_data.get("bc_ad_enabled", False):
            # For BC/AD, account for skipping year 0
            if year > 0:
                # AD years: subtract 1 from year to account for no year 0
                adjusted_year = year - 1
                cumulative_days = (adjusted_year * months_per_year * days_per_month + 
                                  (month - 1) * days_per_month + (day_of_month - 1))
            else:
                # BC years: use year directly (already negative)
                cumulative_days = (year * months_per_year * days_per_month + 
                                  (month - 1) * days_per_month + (day_of_month - 1))
        else:
            # For ages system, calculate as before
            age_offset = age - 1
            year_offset = year - 1 if year > 0 else year  # Handle BC years
            
            # Calculate cumulative years from all previous ages
            cumulative_years_from_ages = 0
            for prev_age in range(1, age):
                years_in_prev_age = self.config_data["time_units"]["ages"].get("years_per_age", {}).get(str(prev_age), 100)
                cumulative_years_from_ages += years_in_prev_age
            
            cumulative_days = (cumulative_years_from_ages * months_per_year * days_per_month +
                              year_offset * months_per_year * days_per_month + 
                              (month - 1) * days_per_month + (day_of_month - 1))
        
        day_of_week = ((cumulative_days + offset) % days_per_week) + 1
        self.current_day_of_week.set(day_of_week)
        
        self._update_display()
        
        # Update master timeline to reflect current position (avoid recursion)
        if not hasattr(self, '_updating_from_master') or not self._updating_from_master:
            cumulative_days = self._get_cumulative_days()
            self.master_timeline_var.set(cumulative_days)

    def _handle_year_zero(self, *args):
        """Skip year 0 when BC/AD is enabled."""
        if self.config_data.get("bc_ad_enabled", False):
            year = self.current_year.get()
            if year == 0:
                # If moving from negative to positive, go to 1
                # If moving from positive to negative, go to -1
                # Default to 1 if uncertain
                self.current_year.set(1)

    def _toggle_bc_ad(self):
        """Toggle BC/AD functionality and update entry states."""
        enabled = self.bc_ad_var.get()
        self.config_data["bc_ad_enabled"] = enabled
        
        if not enabled and self.current_year.get() <= 0:
            self.current_year.set(1)
        
        if enabled:
            self.config_data["bc_label"] = self.bc_var.get()
            self.config_data["ad_label"] = self.ad_var.get()
            self.config_data["bc_years"] = self.bc_years_var.get()
            self.config_data["ad_years"] = self.ad_years_var.get()
        
        self._update_ranges()
        self._update_display()
        self._populate_events()

    def _on_epochal_checkbox(self):
        """When epochal checkbox is unchecked, disable epochal dating and restore ages checkbox."""
        if not self.epochal_visible_var.get():
            self.config_data["bc_ad_enabled"] = False
            self.bc_ad_var.set(False)
            ages_checkbox = getattr(self, "ages_checkbox", None)
            ages_label = getattr(self, "ages_label", None)
            if ages_checkbox: ages_checkbox.grid()
            if ages_label: ages_label.grid()
            ec = getattr(self, "epochal_checkbox", None)
            el = getattr(self, "epochal_label", None)
            if ec: ec.grid_remove()
            if el: el.grid_remove()
            if self.current_year.get() <= 0:
                self.current_year.set(1)
            # Re-enable years checkbox now that epochal is off
            years_checkbox = getattr(self, "years_checkbox", None)
            years_count_spinbox = getattr(self, "years_count_spinbox", None)
            if years_checkbox:
                years_checkbox.config(state="normal")
            years_visible_var = getattr(self, "years_visible_var", None)
            years_visible = years_visible_var.get() if years_visible_var else True
            if years_count_spinbox:
                years_count_spinbox.config(state="normal" if years_visible else "disabled")
            self._update_ranges()
            self._update_master_timeline_range()
            self._update_navigator_visibility()
            self._update_display()
            self._populate_events()

    def _configure_ages(self):
        """Open dialog to configure ages with BC/AD settings."""
        dialog = AgeConfigDialog(self, self.config_data["time_units"]["ages"], self.config_data)
        if dialog.result:
            self.config_data["time_units"]["ages"]["names"] = dialog.result["names"]
            self.config_data["time_units"]["ages"]["years_per_age"] = dialog.result["years_per_age"]
            self.config_data.update(dialog.result["bc_ad_config"])
            epochal = self.config_data.get("bc_ad_enabled", False)
            self.bc_ad_var.set(epochal)
            self.bc_var.set(self.config_data.get("bc_label", "BC"))
            self.ad_var.set(self.config_data.get("ad_label", "AD"))

            # Update ages checkbox label and state based on dating system chosen
            ages_checkbox = getattr(self, "ages_checkbox", None)
            ages_label = getattr(self, "ages_label", None)
            ages_count_spinbox = getattr(self, "ages_count_spinbox", None)
            ages_name_btn = getattr(self, "ages_name_btn", None)
            years_checkbox = getattr(self, "years_checkbox", None)
            years_count_spinbox = getattr(self, "years_count_spinbox", None)

            if epochal:
                # Epochal: show epochal checkbox, hide ages checkbox
                ages_checkbox = getattr(self, "ages_checkbox", None)
                ages_label = getattr(self, "ages_label", None)
                if ages_checkbox: ages_checkbox.grid_remove()
                if ages_label: ages_label.grid_remove()
                ec = getattr(self, "epochal_checkbox", None)
                el = getattr(self, "epochal_label", None)
                if ec: ec.grid()
                if el: el.grid()
                ev = getattr(self, "epochal_visible_var", None)
                if ev: ev.set(True)
                if ages_count_spinbox:
                    ages_count_spinbox.config(state="disabled")
                if ages_name_btn:
                    ages_name_btn.config(state="normal")
                self.config_data["visible_units"]["ages"] = False
                ages_visible_var = getattr(self, "ages_visible_var", None)
                if ages_visible_var: ages_visible_var.set(False)
                # Force years enabled under epochal dating
                self.config_data["visible_units"]["years"] = True
                years_visible_var = getattr(self, "years_visible_var", None)
                if years_visible_var: years_visible_var.set(True)
                if years_checkbox:
                    years_checkbox.config(state="disabled")
                if years_count_spinbox:
                    years_count_spinbox.config(state="disabled")
            else:
                # Ages: show ages checkbox, hide epochal checkbox
                ages_checkbox = getattr(self, "ages_checkbox", None)
                ages_label = getattr(self, "ages_label", None)
                if ages_checkbox: ages_checkbox.grid()
                if ages_label: ages_label.grid()
                ec = getattr(self, "epochal_checkbox", None)
                el = getattr(self, "epochal_label", None)
                if ec: ec.grid_remove()
                if el: el.grid_remove()
                ev = getattr(self, "epochal_visible_var", None)
                if ev: ev.set(False)
                if ages_name_btn:
                    ages_name_btn.config(state="normal")  # always enabled
                # Force ages enabled by default
                self.config_data["visible_units"]["ages"] = True
                ages_visible_var = getattr(self, "ages_visible_var", None)
                if ages_visible_var: ages_visible_var.set(True)
                # Release years checkbox (may have been locked by epochal)
                if years_checkbox:
                    years_checkbox.config(state="normal")
                years_visible_var = getattr(self, "years_visible_var", None)
                years_visible = years_visible_var.get() if years_visible_var else True
                if years_count_spinbox:
                    years_count_spinbox.config(state="normal" if years_visible else "disabled")

            self._toggle_bc_ad()
            self._update_ranges()
            self._update_master_timeline_range()
            self._update_navigator_visibility()
            self._update_display()
            self._populate_events()

    def _configure_bc_ad(self):
        """Open dialog to configure BC/AD settings."""
        dialog = BCADConfigDialog(self, self.config_data)
        if dialog.result:
            self.config_data.update(dialog.result)
            self.bc_ad_var.set(self.config_data.get("bc_ad_enabled", False))
            self.bc_var.set(self.config_data.get("bc_label", "BC"))
            self.ad_var.set(self.config_data.get("ad_label", "AD"))
            self._toggle_bc_ad()
            self._update_ranges()
            self._update_display()
            self._populate_events()

    def _configure_day_names(self, unit):
        """Configure names for days with mutual exclusion."""
        other_unit = "days_of_month" if unit == "days_of_week" else "days_of_week"
        
        # Check if the other day type has any names
        other_names = self.config_data["time_units"][other_unit]["names"]
        if any(name.strip() for name in other_names.values()):
            other_display = other_unit.replace('_', ' ').title()
            messagebox.showwarning("Mutual Exclusion", 
                                 f"Cannot rename {unit.replace('_', ' ').title()} because {other_display} already have custom names. "
                                 f"Clear {other_display} names first.")
            return
        
        # Proceed with normal naming dialog
        self._configure_names(unit)
        
        # Enable/disable offset control for days of week
        if unit == "days_of_week":
            day_names = self.config_data["time_units"]["days_of_week"]["names"]
            visible_units = self.config_data.get("visible_units", {})
            days_of_month_enabled = visible_units.get("days_of_month", True)
            days_of_week_enabled = visible_units.get("days_of_week", True)
            has_day_names = any(name.strip() for name in day_names.values())
            
            if (has_day_names and days_of_month_enabled and days_of_week_enabled):
                self.offset_spinbox.config(state="normal")
            else:
                self.offset_spinbox.config(state="disabled")

    def _configure_names(self, unit):
        """Open dialog to configure names for time units."""
        dialog = TimeUnitNamingDialog(self, unit, self.config_data["time_units"][unit])
        if dialog.result:
            self.config_data["time_units"][unit]["names"] = dialog.result
            self._update_display()
            self._populate_events()  # Update events display with new names

    def _get_time_name(self, unit, value):
        """Get the name for a time unit value, or return the number."""
        names = self.config_data["time_units"][unit]["names"]
        name = names.get(str(value), "")
        
        # Handle BC/AD for years
        if unit == "years":
            if self.config_data.get("bc_ad_enabled", False):
                if value <= 0:
                    return f"{abs(value)} {self.config_data.get('bc_label', 'BC')}"
                else:
                    return f"{value} {self.config_data.get('ad_label', 'AD')}"
            elif name.strip():
                return name
            else:
                return f"Year {value}"
        
        # Add prefixes for ages and days of month when not renamed
        if name.strip():
            return name
        else:
            if unit == "ages":
                return f"Age {value}"
            elif unit == "days_of_month":
                return f"Day {value}"
            else:
                return str(value)

    def _update_display(self, *args):
        """Update the time display with current values."""
        visible_units = self.config_data.get("visible_units", {})
        display_parts = []
        
        if visible_units.get("ages", True):
            age_name = self._get_time_name("ages", int(self.current_age.get()))
            display_parts.append(age_name)
            
        # Show years if Years is enabled
        if visible_units.get("years", True):
            year_name = self._get_time_name("years", int(self.current_year.get()))
            display_parts.append(year_name)
            
        if visible_units.get("months", True):
            month_name = self._get_time_name("months", int(self.current_month.get()))
            display_parts.append(month_name)
            
        if visible_units.get("days_of_month", True):
            day_month_name = self._get_time_name("days_of_month", int(self.current_day_of_month.get()))
            display_parts.append(day_month_name)
            
        # Day of week goes at the end if it has custom names AND days of week are visible
        if (visible_units.get("days_of_week", True) and 
            any(name.strip() for name in self.config_data["time_units"]["days_of_week"]["names"].values())):
            day_week_name = self._get_time_name("days_of_week", int(self.current_day_of_week.get()))
            display_parts.append(day_week_name)
        
        display_text = " / ".join(display_parts) if display_parts else "No time units visible"
        self.time_display.config(text=display_text)
        
        # Highlight matching events
        self._highlight_matching_events()

    def _on_event_right_click(self, event):
        """Right-click context menu on timeline events."""
        item = self.events_tree.identify_row(event.y)
        if not item:
            return
        self.events_tree.selection_set(item)
        self.events_tree.focus(item)

        # Get the event
        evt = self._get_event_by_id(item)

        menu = tk.Menu(self, tearoff=0)

        # Show follow link options from name and description
        all_links = parse_links(evt.get("name", "")) + parse_links(evt.get("description", ""))
        if all_links and self.controller:
            for _, _, path, display in all_links:
                menu.add_command(label=f"Open: {display}",
                               command=lambda p=path: self.controller._open_file_editor(p.split('/')))
            menu.add_separator()

        menu.add_command(label="Edit Event", command=lambda: self._hotkey_edit_event(None))
        menu.add_command(label="Delete Event", command=lambda: self._hotkey_delete_event(None))
        popup_menu(menu, event.x_root, event.y_root)

    def _insert_event_link(self, item_id):
        """Open edit dialog for the event to insert a link in description."""
        self._hotkey_edit_event(None)

    def _on_event_click(self, event):
        """Move scrubbers to match the clicked event's start date."""
        selection = self.events_tree.selection()
        if not selection:
            return
        
        item_id = selection[0]
        
        try:
            evt = self._get_event_by_id(item_id)
            start_time = evt.get("start_time", {})
        except (IndexError, KeyError):
            return
        
        # Move scrubbers to the event's start time
        if start_time:
            self.current_age.set(start_time.get("age", 1))
            self.current_year.set(start_time.get("year", 1))
            self.current_month.set(start_time.get("month", 1))
            self.current_day_of_month.set(start_time.get("day_of_month", 1))
            self._update_age_change()  # This will update year range and other calculations

    def _navigate_up(self, event):
        """Handle up arrow key navigation."""
        selection = self.events_tree.selection()
        if selection:
            current = selection[0]
            prev_item = self.events_tree.prev(current)
            if prev_item:
                self.events_tree.selection_set(prev_item)
                self.events_tree.see(prev_item)
        return 'break'

    def _navigate_down(self, event):
        """Handle down arrow key navigation."""
        selection = self.events_tree.selection()
        if selection:
            current = selection[0]
            next_item = self.events_tree.next(current)
            if next_item:
                self.events_tree.selection_set(next_item)
                self.events_tree.see(next_item)
        return 'break'

    def _navigate_left(self, event):
        """Handle left arrow key navigation (collapse)."""
        selection = self.events_tree.selection()
        if selection:
            current = selection[0]
            if self.events_tree.item(current, 'open'):
                self.events_tree.item(current, open=False)
            else:
                parent = self.events_tree.parent(current)
                if parent:
                    self.events_tree.selection_set(parent)
                    self.events_tree.see(parent)
        return 'break'

    def _navigate_right(self, event):
        """Handle right arrow key navigation (expand)."""
        selection = self.events_tree.selection()
        if selection:
            current = selection[0]
            if self.events_tree.get_children(current):
                if not self.events_tree.item(current, 'open'):
                    self.events_tree.item(current, open=True)
                else:
                    first_child = self.events_tree.get_children(current)[0]
                    self.events_tree.selection_set(first_child)
                    self.events_tree.see(first_child)
        return 'break'

    def _hotkey_edit_event(self, event):
        """Hotkey handler for editing selected event (Enter)."""
        self._edit_event()
        return 'break'  # Prevent default behavior

    def _hotkey_add_event(self, event):
        """Hotkey handler for adding new event (Shift+Enter)."""
        self._add_event()
        return 'break'

    def _hotkey_add_sub_event(self, event):
        """Hotkey handler for adding sub-event (Ctrl+Enter)."""
        self._add_sub_event()
        return 'break'

    def _hotkey_delete_event(self, event):
        """Hotkey handler for deleting event (Delete)."""
        self._delete_event()
        return 'break'

    def _add_event(self):
        """Add a new timeline event. Auto-nests as sub-event if within a parent's date range."""
        current_time = {
            "age": int(self.current_age.get()),
            "year": int(self.current_year.get()),
            "month": int(self.current_month.get()),
            "day_of_week": int(self.current_day_of_week.get()),
            "day_of_month": int(self.current_day_of_month.get())
        }
        
        dialog = TimelineEventDialog(self, current_time)
        if dialog.result:
            new_start = self._get_event_sort_key(dialog.result)
            new_end = None
            if dialog.result.get("end_time"):
                et = dialog.result["end_time"]
                new_end = (et.get("age", 0), et.get("year", 0), et.get("month", 0),
                          et.get("day_of_month", 0), et.get("day_of_week", 0))
            parent_list = self._find_deepest_parent(self.config_data["events"], new_start, new_end)
            parent_list.append(dialog.result)
            self._populate_events()

    def _find_deepest_parent(self, events_list, new_start, new_end):
        """Recursively find the deepest event list where the new event is fully contained."""
        for evt in events_list:
            if evt.get("end_time"):
                evt_start = self._get_event_sort_key(evt)
                evt_end = (evt["end_time"].get("age", 0), evt["end_time"].get("year", 0),
                          evt["end_time"].get("month", 0), evt["end_time"].get("day_of_month", 0),
                          evt["end_time"].get("day_of_week", 0))
                # Only nest if fully contained (start and end both within parent range)
                if evt_start <= new_start <= evt_end:
                    if new_end is None or new_end <= evt_end:
                        if "sub_events" not in evt:
                            evt["sub_events"] = []
                        return self._find_deepest_parent(evt["sub_events"], new_start, new_end)
        return events_list

    def _get_event_by_id(self, item_id):
        """Resolve a tree item_id (e.g. '0_1_2') to the event dict."""
        parts = item_id.split("_")
        evt = self.config_data["events"][int(parts[0])]
        for p in parts[1:]:
            evt = evt.get("sub_events", [])[int(p)]
        return evt

    def _delete_event_by_id(self, item_id):
        """Delete an event by its tree item_id."""
        parts = item_id.split("_")
        if len(parts) == 1:
            del self.config_data["events"][int(parts[0])]
        else:
            parent = self.config_data["events"][int(parts[0])]
            for p in parts[1:-1]:
                parent = parent["sub_events"][int(p)]
            del parent["sub_events"][int(parts[-1])]

    def _add_sub_event(self):
        """Add a sub-event to the selected main event."""
        selection = self.events_tree.selection()
        if not selection:
            messagebox.showinfo("Selection Required", "Please select a main event to add a sub-event to.")
            return
        
        item_id = selection[0]
        # Check if this is a main event (not already a sub-event)
        parent_id = self.events_tree.parent(item_id)
        if parent_id:
            messagebox.showinfo("Invalid Selection", "Sub-events can only be added to main events, not to other sub-events.")
            return
        
        event_index = int(item_id) if item_id.isdigit() else None
        if event_index is not None and event_index < len(self.config_data["events"]):
            current_time = {
                "age": int(self.current_age.get()),
                "year": int(self.current_year.get()),
                "month": int(self.current_month.get()),
                "day_of_week": int(self.current_day_of_week.get()),
                "day_of_month": int(self.current_day_of_month.get())
            }
            
            dialog = TimelineEventDialog(self, current_time, title="Add Sub-Event")
            if dialog.result:
                # Add sub_events list if it doesn't exist
                if "sub_events" not in self.config_data["events"][event_index]:
                    self.config_data["events"][event_index]["sub_events"] = []
                
                self.config_data["events"][event_index]["sub_events"].append(dialog.result)
                self._populate_events()

    def _edit_event(self):
        """Edit selected event or sub-event."""
        selection = self.events_tree.selection()
        if not selection:
            messagebox.showinfo("Selection Required", "Please select an event to edit.")
            return
        
        item_id = selection[0]
        
        try:
            event = self._get_event_by_id(item_id)
        except (IndexError, KeyError):
            return

        # Handle backward compatibility
        if "time" in event and "start_time" not in event:
            event["start_time"] = event["time"]
            del event["time"]
        
        current_time = event.get("start_time", {
            "age": int(self.current_age.get()),
            "year": int(self.current_year.get()),
            "month": int(self.current_month.get()),
            "day_of_week": int(self.current_day_of_week.get()),
            "day_of_month": int(self.current_day_of_month.get())
        })
        
        dialog = TimelineEventDialog(self, current_time, event)
        if dialog.result:
            # Preserve existing sub-events
            existing_sub_events = event.get("sub_events", [])
            dialog.result["sub_events"] = existing_sub_events
            
            # Replace event in the tree
            parts = item_id.split("_")
            if len(parts) == 1:
                self.config_data["events"][int(parts[0])] = dialog.result
            else:
                parent = self.config_data["events"][int(parts[0])]
                for p in parts[1:-1]:
                    parent = parent["sub_events"][int(p)]
                parent["sub_events"][int(parts[-1])] = dialog.result
            self._populate_events()
        
    def _delete_event(self):
        """Delete selected event or sub-event.""" 
        selection = self.events_tree.selection()
        if not selection:
            messagebox.showinfo("Selection Required", "Please select an event to delete.")
            return
        
        item_id = selection[0]
        
        try:
            evt = self._get_event_by_id(item_id)
        except (IndexError, KeyError):
            return

        event_name = evt.get("name", "")
        sub_events_count = len(evt.get("sub_events", []))
        
        if sub_events_count > 0:
            message = f"Are you sure you want to delete '{event_name}' and its {sub_events_count} sub-event(s)?"
        else:
            message = f"Are you sure you want to delete '{event_name}'?"
        
        if messagebox.askyesno("Confirm Delete", message):
            self._delete_event_by_id(item_id)
            self._populate_events()

    def _populate_events(self):
        """Populate the events tree with chronological sorting and sub-events."""
        for item in self.events_tree.get_children():
            self.events_tree.delete(item)
        
        # Sort events chronologically by start time
        sorted_events = sorted(enumerate(self.config_data["events"]), 
                              key=lambda x: self._get_event_sort_key(x[1]))
            
        for original_index, event in sorted_events:
            # Handle backward compatibility - convert old 'time' to 'start_time'
            if "time" in event and "start_time" not in event:
                event["start_time"] = event["time"]
                del event["time"]
            
            start_time = event.get('start_time', {})
            end_time = event.get('end_time')
            
            start_time_str = self._format_event_time_display(start_time)
            end_time_str = self._format_event_time_display(end_time) if end_time else ""
                
            desc_display = LINK_REGEX.sub(lambda m: "⇗ " + (m.group(2) or m.group(1).split('/')[-1]), event.get('description', ''))
            name_display = LINK_REGEX.sub(lambda m: "⇗ " + (m.group(2) or m.group(1).split('/')[-1]), event['name'])
            main_item = self.events_tree.insert('', 'end', text=name_display, iid=str(original_index),
                                               values=(start_time_str, end_time_str, desc_display[:50]))
            
            self._populate_sub_events(main_item, event.get('sub_events', []), str(original_index))

    def _populate_sub_events(self, parent_item, sub_events, id_prefix):
        """Recursively populate sub-events."""
        for sub_index, sub_event in enumerate(sub_events):
            sub_start_time = sub_event.get('start_time', {})
            sub_end_time = sub_event.get('end_time')
            
            sub_start_time_str = self._format_event_time_display(sub_start_time)
            sub_end_time_str = self._format_event_time_display(sub_end_time) if sub_end_time else ""
            
            sub_desc_display = LINK_REGEX.sub(lambda m: "⇗ " + (m.group(2) or m.group(1).split('/')[-1]), sub_event.get('description', ''))
            item_id = f"{id_prefix}_{sub_index}"
            sub_name_display = LINK_REGEX.sub(lambda m: "⇗ " + (m.group(2) or m.group(1).split('/')[-1]), sub_event['name'])
            sub_item = self.events_tree.insert(parent_item, 'end', text=sub_name_display, 
                                   iid=item_id,
                                   values=(sub_start_time_str, sub_end_time_str, sub_desc_display[:50]))
            
            # Recurse into nested sub-events
            nested_subs = sub_event.get('sub_events', [])
            if nested_subs:
                self._populate_sub_events(sub_item, nested_subs, item_id)
        
        if sub_events:
            self.events_tree.item(parent_item, open=True)

    def _get_event_sort_key(self, event):
        """Generate a sort key for chronological ordering."""
        start_time = event.get('start_time', {})
        
        # Create a sortable tuple (age, year, month, day_of_month, day_of_week)
        age = start_time.get('age', 0)
        year = start_time.get('year', 0)
        month = start_time.get('month', 0)
        day_of_month = start_time.get('day_of_month', 0)
        day_of_week = start_time.get('day_of_week', 0)
        
        return (age, year, month, day_of_month, day_of_week)

    def _highlight_matching_events(self):
        """Highlight events that match the current scrubber position."""
        current_time = {
            "age": int(self.current_age.get()),
            "year": int(self.current_year.get()),
            "month": int(self.current_month.get()),
            "day_of_week": int(self.current_day_of_week.get()),
            "day_of_month": int(self.current_day_of_month.get())
        }
        
        self.events_tree.tag_configure('highlighted', background='lightblue')
        
        # Recursively clear and check all tree items
        def process_tree_items(parent_id, events_list, id_prefix=""):
            for idx, event in enumerate(events_list):
                item_id = f"{id_prefix}{idx}" if not id_prefix else f"{id_prefix}_{idx}"
                if not id_prefix:
                    item_id = str(idx)
                
                # Clear highlight
                try:
                    self.events_tree.item(item_id, tags=())
                except Exception:
                    continue
                
                # Check match
                start_time = event.get('start_time', {})
                end_time = event.get('end_time')
                if self._times_match(current_time, start_time) or (end_time and self._time_in_range(current_time, start_time, end_time)):
                    self.events_tree.item(item_id, tags=('highlighted',))
                
                # Recurse into sub-events
                sub_events = event.get('sub_events', [])
                if sub_events:
                    process_tree_items(item_id, sub_events, item_id)
        
        process_tree_items('', self.config_data["events"])

    def _times_match(self, time1, time2):
        """Check if two time dictionaries match."""
        visible_units = self.config_data.get("visible_units", {})
        
        if visible_units.get("ages", True) and time1.get("age") != time2.get("age"):
            return False
        # Check years if Years is enabled
        if visible_units.get("years", True) and time1.get("year") != time2.get("year"):
            return False
        if visible_units.get("months", True) and time1.get("month") != time2.get("month"):
            return False
        if visible_units.get("days_of_month", True) and time1.get("day_of_month") != time2.get("day_of_month"):
            return False
        if visible_units.get("days_of_week", True) and time1.get("day_of_week") != time2.get("day_of_week"):
            return False
            
        return True

    def _time_in_range(self, current_time, start_time, end_time):
        """Check if current time is within the range of start and end times."""
        current_sort_key = self._get_event_sort_key({"start_time": current_time})
        start_sort_key = self._get_event_sort_key({"start_time": start_time})
        end_sort_key = self._get_event_sort_key({"start_time": end_time})
        
        return start_sort_key <= current_sort_key <= end_sort_key

    def _format_event_time_display(self, time_data):
        """Format time data for event display using the same format as navigator."""
        visible_units = self.config_data.get("visible_units", {})
        display_parts = []
        
        if visible_units.get("ages", True):
            age_name = self._get_time_name("ages", time_data.get('age', 1))
            display_parts.append(age_name)
            
        # Show years if Years is enabled
        if visible_units.get("years", True):
            year_name = self._get_time_name("years", time_data.get('year', 1))
            display_parts.append(year_name)
            
        if visible_units.get("months", True):
            month_name = self._get_time_name("months", time_data.get('month', 1))
            display_parts.append(month_name)
            
        if visible_units.get("days_of_month", True):
            day_month_name = self._get_time_name("days_of_month", time_data.get('day_of_month', 1))
            display_parts.append(day_month_name)
            
        # Day of week at the end if it has custom names
        if (visible_units.get("days_of_week", True) and 
            any(name.strip() for name in self.config_data["time_units"]["days_of_week"]["names"].values())):
            day_week_name = self._get_time_name("days_of_week", time_data.get('day_of_week', 1))
            display_parts.append(day_week_name)
        
        return " / ".join(display_parts) if display_parts else "No time units visible"

    def get_content(self):
        """Return the timeline data as JSON."""
        return json.dumps(self.config_data, indent=4)


class AgeConfigDialog(tk.Toplevel):
    """Dialog for configuring ages with BC/AD settings."""
    def __init__(self, parent, unit_data, config_data):
        super().__init__(parent)
        self.transient(parent)
        self.grab_set()
        self.title("Configure Ages")
        self.result = None
        self.unit_data = unit_data
        self.config_data = config_data
        
        self.geometry("500x400")
        self._create_widgets()
        
        # Bind Enter and Escape keys
        self.bind('<Return>', lambda e: self._ok())
        self.bind('<Escape>', lambda e: self._cancel())
        
        self.wait_window(self)

    def _create_widgets(self):
        container = ttk.Frame(self)
        container.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Scrollable frame for age entries
        canvas = tk.Canvas(container, height=250)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Headers
        ttk.Label(scrollable_frame, text="Dating System", font=('Helvetica', 10, 'bold')).grid(row=0, column=0, columnspan=5, pady=10)
        
        # Radio buttons for dating system choice
        self.dating_system = tk.StringVar(value="ages" if not self.config_data.get("bc_ad_enabled", False) else "epochal")
        ttk.Radiobutton(scrollable_frame, text="Ages/Epochs (Age 1, Age 2...)", 
                       variable=self.dating_system, value="ages", 
                       command=self._toggle_dating_system).grid(row=1, column=0, columnspan=5, sticky="w", pady=5)
        ttk.Radiobutton(scrollable_frame, text="Epochal Dating (BC/AD style)", 
                       variable=self.dating_system, value="epochal", 
                       command=self._toggle_dating_system).grid(row=2, column=0, columnspan=5, sticky="w", pady=5)
        
        # Ages configuration (shown when ages system selected)
        self.ages_frame = ttk.Frame(scrollable_frame)
        self.ages_frame.grid(row=3, column=0, columnspan=5, sticky="ew", pady=10)
        
        ttk.Label(self.ages_frame, text="Age", font=('Helvetica', 9, 'bold')).grid(row=0, column=0, padx=5, pady=5)
        ttk.Label(self.ages_frame, text="Name", font=('Helvetica', 9, 'bold')).grid(row=0, column=1, padx=5, pady=5)
        ttk.Label(self.ages_frame, text="Years", font=('Helvetica', 9, 'bold')).grid(row=0, column=2, padx=5, pady=5)
        
        # Epochal configuration (shown when epochal system selected)  
        self.epochal_frame = ttk.Frame(scrollable_frame)
        self.epochal_frame.grid(row=4, column=0, columnspan=5, sticky="ew", pady=10)
        
        ttk.Label(self.epochal_frame, text="Before Label:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.bc_var = tk.StringVar(value=self.config_data.get("bc_label", "BC"))
        ttk.Entry(self.epochal_frame, textvariable=self.bc_var, width=10).grid(row=0, column=1, padx=5, pady=5)
        
        ttk.Label(self.epochal_frame, text="BC Years:").grid(row=0, column=2, padx=5, pady=5, sticky="w")
        self.bc_years_var = tk.IntVar(value=self.config_data.get("bc_years", 100))
        ttk.Spinbox(self.epochal_frame, from_=1, to=999999, width=8, textvariable=self.bc_years_var).grid(row=0, column=3, padx=5, pady=5)
        
        ttk.Label(self.epochal_frame, text="After Label:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.ad_var = tk.StringVar(value=self.config_data.get("ad_label", "AD"))
        ttk.Entry(self.epochal_frame, textvariable=self.ad_var, width=10).grid(row=1, column=1, padx=5, pady=5)
        
        ttk.Label(self.epochal_frame, text="AD Years:").grid(row=1, column=2, padx=5, pady=5, sticky="w")
        self.ad_years_var = tk.IntVar(value=self.config_data.get("ad_years", 100))
        ttk.Spinbox(self.epochal_frame, from_=1, to=999999, width=8, textvariable=self.ad_years_var).grid(row=1, column=3, padx=5, pady=5)
        
        self.name_vars = {}
        self.years_vars = {}
        
        for i in range(1, self.unit_data["count"] + 1):
            # Age number and name (for ages system)
            ttk.Label(self.ages_frame, text=f"{i}:").grid(row=i, column=0, padx=5, pady=2, sticky="w")
            name_var = tk.StringVar(value=self.unit_data["names"].get(str(i), ""))
            self.name_vars[str(i)] = name_var
            ttk.Entry(self.ages_frame, textvariable=name_var, width=20).grid(row=i, column=1, padx=5, pady=2)
            
            # Years per age
            years_var = tk.IntVar(value=self.unit_data.get("years_per_age", {}).get(str(i), 100))
            self.years_vars[str(i)] = years_var
            ttk.Spinbox(self.ages_frame, from_=1, to=999999, width=8, textvariable=years_var).grid(row=i, column=2, padx=5, pady=2)
        
        self._toggle_dating_system()
        
        canvas.pack(side="top", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Buttons
        btn_frame = ttk.Frame(container)
        btn_frame.pack(side="bottom", fill=tk.X, pady=(10, 0))
        ttk.Button(btn_frame, text="OK", command=self._ok).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="Cancel", command=self._cancel).pack(side=tk.RIGHT, padx=5)

    def _toggle_dating_system(self):
        """Toggle between ages and epochal dating systems."""
        if self.dating_system.get() == "ages":
            self.ages_frame.grid()
            self.epochal_frame.grid_remove()
        else:
            self.ages_frame.grid_remove()
            self.epochal_frame.grid()

    def _ok(self):
        names = {k: v.get().strip() for k, v in self.name_vars.items()}
        years_per_age = {k: v.get() for k, v in self.years_vars.items()}
        
        if self.dating_system.get() == "epochal":
            # Epochal dating system
            bc_ad_config = {
                "bc_ad_enabled": True,
                "bc_label": self.bc_var.get(),
                "ad_label": self.ad_var.get(),
                "bc_years": self.bc_years_var.get(),
                "ad_years": self.ad_years_var.get()
            }
        else:
            # Ages dating system
            bc_ad_config = {
                "bc_ad_enabled": False,
                "bc_label": "BC",
                "ad_label": "AD"
            }
        
        self.result = {
            "names": names,
            "years_per_age": years_per_age,
            "bc_ad_config": bc_ad_config
        }
        self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()


class BCADConfigDialog(tk.Toplevel):
    """Dialog for configuring BC/AD settings."""
    def __init__(self, parent, config_data):
        super().__init__(parent)
        self.transient(parent)
        self.grab_set()
        self.title("BC/AD Configuration")
        self.result = None
        self.config_data = config_data
        
        self.geometry("300x150")
        self._create_widgets()
        
        # Bind Enter and Escape keys
        self.bind('<Return>', lambda e: self._ok())
        self.bind('<Escape>', lambda e: self._cancel())
        
        self.wait_window(self)

    def _create_widgets(self):
        # Enable checkbox
        self.bc_ad_var = tk.BooleanVar(value=self.config_data.get("bc_ad_enabled", False))
        ttk.Checkbutton(self, text="Enable BC/AD Dating", variable=self.bc_ad_var, 
                       command=self._toggle_entries).grid(row=0, column=0, columnspan=2, sticky="w", padx=10, pady=10)
        
        # BC Label
        ttk.Label(self, text="BC Label:").grid(row=1, column=0, sticky="w", padx=10, pady=5)
        self.bc_var = tk.StringVar(value=self.config_data.get("bc_label", "BC"))
        self.bc_entry = ttk.Entry(self, width=10, textvariable=self.bc_var)
        self.bc_entry.grid(row=1, column=1, padx=10, pady=5)
        
        # AD Label
        ttk.Label(self, text="AD Label:").grid(row=2, column=0, sticky="w", padx=10, pady=5)
        self.ad_var = tk.StringVar(value=self.config_data.get("ad_label", "AD"))
        self.ad_entry = ttk.Entry(self, width=10, textvariable=self.ad_var)
        self.ad_entry.grid(row=2, column=1, padx=10, pady=5)
        
        # Buttons
        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=3, column=0, columnspan=2, pady=10)
        ttk.Button(btn_frame, text="OK", command=self._ok).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Cancel", command=self._cancel).pack(side=tk.LEFT, padx=5)
        
        self._toggle_entries()

    def _toggle_entries(self):
        state = "normal" if self.bc_ad_var.get() else "disabled"
        self.bc_entry.config(state=state)
        self.ad_entry.config(state=state)

    def _ok(self):
        self.result = {
            "bc_ad_enabled": self.bc_ad_var.get(),
            "bc_label": self.bc_var.get(),
            "ad_label": self.ad_var.get()
        }
        self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()


class TimeUnitNamingDialog(tk.Toplevel):
    """Dialog for naming time units."""
    def __init__(self, parent, unit_type, unit_data):
        super().__init__(parent)
        self.transient(parent)
        self.grab_set()
        self.title(f"Configure {unit_type.title()} Names")
        self.result = None
        self.unit_data = unit_data
        
        self.geometry("400x400")
        self._create_widgets()
        
        # Bind Enter and Escape keys
        self.bind('<Return>', lambda e: self._ok())
        self.bind('<Escape>', lambda e: self._cancel())
        
        self.wait_window(self)

    def _create_widgets(self):
        # Main container with proper packing
        container = ttk.Frame(self)
        container.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Scrollable frame for name entries
        canvas = tk.Canvas(container, height=250)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        self.name_vars = {}
        for i in range(1, self.unit_data["count"] + 1):
            ttk.Label(scrollable_frame, text=f"{i}:").grid(row=i-1, column=0, padx=5, pady=2, sticky="w")
            var = tk.StringVar(value=self.unit_data["names"].get(str(i), ""))
            self.name_vars[str(i)] = var
            ttk.Entry(scrollable_frame, textvariable=var, width=20).grid(row=i-1, column=1, padx=5, pady=2)
        
        canvas.pack(side="top", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Buttons frame - separate from scrollable area
        btn_frame = ttk.Frame(container)
        btn_frame.pack(side="bottom", fill=tk.X, pady=(10, 0))
        
        ttk.Button(btn_frame, text="OK", command=self._ok).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="Cancel", command=self._cancel).pack(side=tk.RIGHT, padx=5)

    def _ok(self):
        # Include all entries, empty ones will revert to numbers
        self.result = {k: v.get().strip() for k, v in self.name_vars.items()}
        self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()


class TimelineEventDialog(tk.Toplevel):
    """Dialog for creating timeline events."""
    def __init__(self, parent, current_time, existing_event=None, title=None):
        super().__init__(parent)
        self.transient(parent)
        self.grab_set()
        
        # Set title based on context
        if title:
            self.title(title)
        elif existing_event:
            self.title("Edit Timeline Event")
        else:
            self.title("Add Timeline Event")
            
        self.result = None
        self.current_time = current_time
        self.existing_event = existing_event
        self.parent_editor = parent
        
        # Store reference to events tree for focus management
        self.events_tree = parent.events_tree
        
        self.geometry("600x400")
        self._create_widgets()
        
        # Ensure dialog gets focus
        self.focus_set()
        self.lift()
        self.attributes('-topmost', True)
        self.after(100, lambda: self.attributes('-topmost', False))
        
        # Bind Enter and Escape keys
        self.bind('<Return>', lambda e: self._ok())
        self.bind('<Escape>', lambda e: self._cancel())
        
        self.wait_window(self)

    def _create_widgets(self):
        # Event name
        ttk.Label(self, text="Event Name:").grid(row=0, column=0, sticky="w", padx=10, pady=5)
        name_frame = ttk.Frame(self)
        name_frame.grid(row=0, column=1, columnspan=2, padx=10, pady=5, sticky="ew")
        self.name_text = tk.Text(name_frame, width=40, height=1)
        self.name_text.pack(fill=tk.X)
        self.name_text.tag_configure('link', foreground='#1565C0', underline=True)
        self.name_text.bind('<ButtonRelease-3>', self._name_right_click)
        self._name_links = {}
        if self.existing_event:
            self._load_name_with_links(self.existing_event.get("name", ""))
        
        # Description
        ttk.Label(self, text="Description:").grid(row=1, column=0, sticky="nw", padx=10, pady=5)
        desc_frame = ttk.Frame(self)
        desc_frame.grid(row=1, column=1, columnspan=2, padx=10, pady=5, sticky="ew")
        self.desc_text = tk.Text(desc_frame, width=40, height=3)
        self.desc_text.pack(fill=tk.X)
        self.desc_text.tag_configure('link', foreground='#1565C0', underline=True)
        if self.existing_event:
            self._load_desc_with_links(self.existing_event.get("description", ""))
        self.desc_text.bind('<ButtonRelease-3>', self._desc_right_click)
        
        # Start time controls
        start_frame = ttk.LabelFrame(self, text="Start Time", padding="10")
        start_frame.grid(row=2, column=0, columnspan=3, sticky="ew", padx=10, pady=5)
        
        start_time = self.existing_event.get("start_time", self.current_time) if self.existing_event else self.current_time
        self._create_time_controls(start_frame, "start", start_time)
        
        # End time controls
        end_frame = ttk.LabelFrame(self, text="End Time (Optional)", padding="10")
        end_frame.grid(row=3, column=0, columnspan=3, sticky="ew", padx=10, pady=5)
        
        self.end_time_enabled = tk.BooleanVar(value=bool(self.existing_event and self.existing_event.get("end_time")))
        ttk.Checkbutton(end_frame, text="Set end time", variable=self.end_time_enabled, 
                       command=self._toggle_end_time).grid(row=0, column=0, columnspan=6, sticky="w", pady=5)
        
        end_time = self.existing_event.get("end_time", self.current_time) if self.existing_event else self.current_time
        self._create_time_controls(end_frame, "end", end_time, row_offset=1)
        
        # Buttons
        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=4, column=0, columnspan=3, pady=10)
        
        ttk.Button(btn_frame, text="OK", command=self._ok).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Cancel", command=self._cancel).pack(side=tk.LEFT, padx=5)
        
        self._toggle_end_time()

    def _create_time_controls(self, parent, prefix, time_data, row_offset=0):
        """Create time input controls for start or end time."""
        visible_units = self.parent_editor.config_data.get("visible_units", {})
        col = 0
        
        if visible_units.get("ages", True):
            ttk.Label(parent, text="Age:").grid(row=row_offset, column=col, padx=5)
            var = tk.IntVar(value=time_data.get('age', 1))
            setattr(self, f"{prefix}_age_var", var)
            age_count = self.parent_editor.config_data["time_units"]["ages"]["count"]
            ttk.Spinbox(parent, from_=1, to=age_count, width=8, textvariable=var).grid(row=row_offset+1, column=col, padx=5)
            col += 1
            
        if visible_units.get("years", True):
            ttk.Label(parent, text="Year:").grid(row=row_offset, column=col, padx=5)
            var = tk.IntVar(value=time_data.get('year', 1))
            setattr(self, f"{prefix}_year_var", var)
            
            if self.parent_editor.config_data.get("bc_ad_enabled", False):
                bc_years = self.parent_editor.config_data.get("bc_years", 100)
                ad_years = self.parent_editor.config_data.get("ad_years", 100)
                ttk.Spinbox(parent, from_=-bc_years, to=ad_years, width=8, textvariable=var).grid(row=row_offset+1, column=col, padx=5)
            elif visible_units.get("ages", True):
                # Use years from current age
                current_age = time_data.get('age', 1)
                years_in_age = self.parent_editor.config_data["time_units"]["ages"].get("years_per_age", {}).get(str(current_age), 100)
                ttk.Spinbox(parent, from_=1, to=years_in_age, width=8, textvariable=var).grid(row=row_offset+1, column=col, padx=5)
            else:
                year_count = self.parent_editor.config_data["time_units"]["years"]["count"]
                ttk.Spinbox(parent, from_=1, to=year_count, width=8, textvariable=var).grid(row=row_offset+1, column=col, padx=5)
            col += 1
            
        if visible_units.get("months", True):
            ttk.Label(parent, text="Month:").grid(row=row_offset, column=col, padx=5)
            var = tk.IntVar(value=time_data.get('month', 1))
            setattr(self, f"{prefix}_month_var", var)
            month_count = self.parent_editor.config_data["time_units"]["months"]["count"]
            ttk.Spinbox(parent, from_=1, to=month_count, width=8, textvariable=var).grid(row=row_offset+1, column=col, padx=5)
            col += 1
            
        if visible_units.get("days_of_month", True):
            ttk.Label(parent, text="Day:").grid(row=row_offset, column=col, padx=5)
            var = tk.IntVar(value=time_data.get('day_of_month', 1))
            setattr(self, f"{prefix}_day_of_month_var", var)
            day_count = self.parent_editor.config_data["time_units"]["days_of_month"]["count"]
            ttk.Spinbox(parent, from_=1, to=day_count, width=8, textvariable=var).grid(row=row_offset+1, column=col, padx=5)
            col += 1

    def _toggle_end_time(self):
        """Toggle end time controls."""
        state = "normal" if self.end_time_enabled.get() else "disabled"
        # Find all spinboxes in the end time frame and enable/disable them
        for widget in self.children.values():
            if isinstance(widget, ttk.LabelFrame) and "End Time" in widget.cget("text"):
                for child in widget.winfo_children():
                    if isinstance(child, ttk.Spinbox):
                        child.config(state=state)

    def _get_time_data(self, prefix):
        """Extract time data from the controls."""
        time_data = {}
        visible_units = self.parent_editor.config_data.get("visible_units", {})
        
        if visible_units.get("ages", True) and hasattr(self, f"{prefix}_age_var"):
            time_data["age"] = getattr(self, f"{prefix}_age_var").get()
        # Include years if Ages OR Years is enabled (since ages need years)
        if visible_units.get("years", True) and hasattr(self, f"{prefix}_year_var"):
            time_data["year"] = getattr(self, f"{prefix}_year_var").get()
        if visible_units.get("months", True) and hasattr(self, f"{prefix}_month_var"):
            time_data["month"] = getattr(self, f"{prefix}_month_var").get()
        if visible_units.get("days_of_month", True) and hasattr(self, f"{prefix}_day_of_month_var"):
            day_of_month = getattr(self, f"{prefix}_day_of_month_var").get()
            time_data["day_of_month"] = day_of_month
            
            # Calculate day of week using the same method as the main timeline
            month = time_data.get("month", 1)
            year = time_data.get("year", 1)
            age = time_data.get("age", 1)
            
            days_per_week = self.parent_editor.config_data["time_units"]["days_of_week"]["count"]
            days_per_month = self.parent_editor.config_data["time_units"]["days_of_month"]["count"]
            months_per_year = self.parent_editor.config_data["time_units"]["months"]["count"]
            offset = self.parent_editor.config_data.get("day_week_offset", 0)
            
            # Calculate cumulative years from all previous ages
            cumulative_years_from_ages = 0
            for prev_age in range(1, age):
                years_in_prev_age = self.parent_editor.config_data["time_units"]["ages"].get("years_per_age", {}).get(str(prev_age), 100)
                cumulative_years_from_ages += years_in_prev_age
            
            year_offset = year - 1 if year > 0 else year
            cumulative_days = (cumulative_years_from_ages * months_per_year * days_per_month +
                              year_offset * months_per_year * days_per_month + 
                              (month - 1) * days_per_month + (day_of_month - 1))
            day_of_week = ((cumulative_days + offset) % days_per_week) + 1
            time_data["day_of_week"] = day_of_week
        elif visible_units.get("days_of_week", True):
            # If days of month is not visible but days of week is, use default
            time_data["day_of_week"] = 1
            
        return time_data

    def _load_name_with_links(self, content):
        """Load name with links rendered as styled text."""
        pos = 0
        while pos < len(content):
            m = LINK_REGEX.search(content[pos:])
            if m:
                if m.start() > 0:
                    self.name_text.insert(tk.END, content[pos:pos + m.start()])
                path = m.group(1)
                display = m.group(2) if m.group(2) else path.split('/')[-1]
                self._name_links[display] = path
                self.name_text.insert(tk.END, display, ('link',))
                pos += m.end()
            else:
                self.name_text.insert(tk.END, content[pos:])
                break

    def _name_right_click(self, event):
        """Right-click on name to insert link."""
        idx = self.name_text.index(f"@{event.x},{event.y}")
        menu = tk.Menu(self, tearoff=0)
        if 'link' in self.name_text.tag_names(idx):
            menu.add_command(label="Remove Link", command=lambda: self._remove_name_link(idx))
            menu.add_separator()
        menu.add_command(label="Insert Link", command=self._insert_name_link)
        popup_menu(menu, event.x_root, event.y_root)

    def _remove_name_link(self, idx):
        widget = self.name_text
        lr = widget.tag_prevrange('link', f"{idx}+1c") or widget.tag_nextrange('link', idx)
        if lr and widget.compare(lr[0], '<=', idx) and widget.compare(lr[1], '>=', idx):
            widget.tag_remove('link', lr[0], lr[1])
            self._name_links.pop(widget.get(lr[0], lr[1]), None)

    def _remove_desc_link(self, idx):
        widget = self.desc_text
        lr = widget.tag_prevrange('link', f"{idx}+1c") or widget.tag_nextrange('link', idx)
        if lr and widget.compare(lr[0], '<=', idx) and widget.compare(lr[1], '>=', idx):
            widget.tag_remove('link', lr[0], lr[1])
            if not hasattr(self, '_desc_links'):
                self._desc_links = {}
            self._desc_links.pop(widget.get(lr[0], lr[1]), None)

    def _insert_name_link(self):
        """Insert a link into the name field."""
        controller = self.parent_editor.controller if hasattr(self.parent_editor, 'controller') else None
        if not controller:
            return
        picker = VFSFilePicker(self, controller.vfs, controller.root_name)
        if not picker.result:
            return
        path = picker.result
        try:
            display = self.name_text.get(tk.SEL_FIRST, tk.SEL_LAST)
            self.name_text.delete(tk.SEL_FIRST, tk.SEL_LAST)
        except tk.TclError:
            display = path.split('/')[-1]
        self._name_links[display] = path
        self.name_text.insert(tk.INSERT, display, ('link',))

    def _get_name_content(self):
        """Get name with links serialized as [[path|display]]."""
        content = ""
        index = "1.0"
        end = self.name_text.index(tk.END + "-1c")
        while self.name_text.compare(index, "<", end):
            link_range = self.name_text.tag_nextrange('link', index)
            if link_range:
                if self.name_text.compare(index, "<", link_range[0]):
                    content += self.name_text.get(index, link_range[0])
                display = self.name_text.get(link_range[0], link_range[1])
                path = self._name_links.get(display, display)
                content += f"[[{path}|{display}]]"
                index = link_range[1]
            else:
                content += self.name_text.get(index, end)
                break
        return content.strip()

    def _load_desc_with_links(self, content):
        """Load description with links rendered as styled text."""
        self._desc_links = {}
        pos = 0
        while pos < len(content):
            m = LINK_REGEX.search(content[pos:])
            if m:
                # Plain text before link
                if m.start() > 0:
                    self.desc_text.insert(tk.END, content[pos:pos + m.start()])
                # Link text
                path = m.group(1)
                display = m.group(2) if m.group(2) else path.split('/')[-1]
                self._desc_links[display] = path
                self.desc_text.insert(tk.END, display, ('link',))
                pos += m.end()
            else:
                self.desc_text.insert(tk.END, content[pos:])
                break

    def _insert_desc_link(self):
        """Insert a link into the description field."""
        controller = self.parent_editor.controller if hasattr(self.parent_editor, 'controller') else None
        if not controller:
            return
        picker = VFSFilePicker(self, controller.vfs, controller.root_name)
        if not picker.result:
            return
        path = picker.result
        try:
            display = self.desc_text.get(tk.SEL_FIRST, tk.SEL_LAST)
            self.desc_text.delete(tk.SEL_FIRST, tk.SEL_LAST)
        except tk.TclError:
            display = path.split('/')[-1]
        if not hasattr(self, '_desc_links'):
            self._desc_links = {}
        self._desc_links[display] = path
        self.desc_text.insert(tk.INSERT, display, ('link',))

    def _desc_right_click(self, event):
        """Right-click on description to insert link."""
        idx = self.desc_text.index(f"@{event.x},{event.y}")
        menu = tk.Menu(self, tearoff=0)
        if 'link' in self.desc_text.tag_names(idx):
            menu.add_command(label="Remove Link", command=lambda: self._remove_desc_link(idx))
            menu.add_separator()
        menu.add_command(label="Insert Link", command=self._insert_desc_link)
        popup_menu(menu, event.x_root, event.y_root)

    def _get_desc_content(self):
        """Get description with links serialized as [[path|display]]."""
        if not hasattr(self, '_desc_links') or not self._desc_links:
            return self.desc_text.get("1.0", tk.END).strip()
        
        content = ""
        index = "1.0"
        end = self.desc_text.index(tk.END + "-1c")
        
        while self.desc_text.compare(index, "<", end):
            link_range = self.desc_text.tag_nextrange('link', index)
            if link_range:
                # Plain text before link
                if self.desc_text.compare(index, "<", link_range[0]):
                    content += self.desc_text.get(index, link_range[0])
                # Link text
                display = self.desc_text.get(link_range[0], link_range[1])
                path = self._desc_links.get(display, display)
                content += f"[[{path}|{display}]]"
                index = link_range[1]
            else:
                content += self.desc_text.get(index, end)
                break
        return content.strip()

    def _ok(self):
        name = self._get_name_content()
        if not name:
            messagebox.showerror("Error", "Event name is required.")
            return
            
        result_data = {
            "name": name,
            "description": self._get_desc_content(),
            "start_time": self._get_time_data("start")
        }
        
        if self.end_time_enabled.get():
            result_data["end_time"] = self._get_time_data("end")
        
        self.result = result_data
        self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()
    
    def destroy(self):
        """Override destroy to return focus to events tree."""
        super().destroy()
        # Return focus to events tree after dialog is destroyed
        if hasattr(self, 'events_tree') and self.events_tree.winfo_exists():
            def restore_focus():
                self.events_tree.focus_force()  # Force focus instead of focus_set
                self.events_tree.update()  # Ensure UI updates
                # Ensure there's a selection for arrow key navigation
                if not self.events_tree.selection():
                    # Select the first item if nothing is selected
                    children = self.events_tree.get_children()
                    if children:
                        self.events_tree.selection_set(children[0])
                        self.events_tree.see(children[0])
            self.events_tree.after(50, restore_focus)  # Longer delay
class EventCreationDialog(tk.Toplevel):
    """Modal dialog for structured input of a single timeline event."""
    def __init__(self, parent, initial_data=None):
        super().__init__(parent)
        self.transient(parent)
        self.grab_set() 
        self.title("Edit Timeline Event" if initial_data else "Add New Timeline Event")
        self.result = None
        self.initial_data = initial_data if initial_data else {}

        self.geometry("500x300")
        self.columnconfigure(1, weight=1)

        self._create_widgets()
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        self.wait_window(self)

    def _create_widgets(self):
        # New Guidance Text for Fictional Chronology
        guidance_text = "e.g., '3' (Age), '3-1200' (Age-Year), '3-1200-7-15' (Age-Year-Month-Day)"
        
        def create_field(row, label_text, key, is_description=False, guidance=""):
            # Label
            label_frame = ttk.Frame(self)
            label_frame.grid(row=row, column=0, sticky="w", padx=10, pady=5)
            ttk.Label(label_frame, text=f"{label_text}:").pack(side=tk.TOP, anchor=tk.W)
            if guidance:
                 # Small guidance text for dates
                 ttk.Label(label_frame, text=guidance, font=('Helvetica', 8, 'italic'), foreground='gray').pack(side=tk.TOP, anchor=tk.W)
            
            # Input Widget
            if is_description:
                widget = tk.Text(self, wrap=tk.WORD, height=5, width=30, font=('Helvetica', 10))
                widget.grid(row=row, column=1, sticky="ew", padx=10, pady=5)
                widget.insert(tk.END, self.initial_data.get(key, ""))
            else:
                var = tk.StringVar(value=self.initial_data.get(key, ""))
                widget = ttk.Entry(self, textvariable=var)
                widget.grid(row=row, column=1, sticky="ew", padx=10, pady=5)
                widget.var = var 
            
            return widget

        self.name_entry = create_field(0, "Event Name", "name")
        self.start_entry = create_field(1, "Start Chronology", "start", guidance=guidance_text)
        self.end_entry = create_field(2, "End Chronology (Optional)", "end", guidance=guidance_text)
        self.desc_text = create_field(3, "Description", "description", is_description=True)
        
        button_frame = ttk.Frame(self)
        button_frame.grid(row=4, column=0, columnspan=2, pady=10)
        
        ttk.Button(button_frame, text="Save", command=self.ok, width=10).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=self.cancel, width=10).pack(side=tk.LEFT, padx=5)
        
        self.name_entry.focus_set()
        self.bind("<Return>", lambda event: self.ok())
        self.bind("<Escape>", lambda event: self.cancel())

    def ok(self):
        name = self.name_entry.var.get().strip()
        start = self.start_entry.var.get().strip()
        end = self.end_entry.var.get().strip()
        description = self.desc_text.get("1.0", tk.END).strip()

        if not name or not start:
            messagebox.showerror("Error", "Event Name and Start Chronology are required.", parent=self)
            return
            
        # Basic Chronology check (detailed validation happens in TimelineEditor)
        if _chron_label_to_sortable_float(start) is None:
             messagebox.showerror("Format Error", "Start Chronology is improperly formatted. Use format: Age or Age-Year-Month-Day (e.g., '3' or '3-1200-7-15').", parent=self)
             return
             
        if end and _chron_label_to_sortable_float(end) is None:
             messagebox.showerror("Format Error", "End Chronology is improperly formatted. Use format: Age or Age-Year-Month-Day (e.g., '3' or '3-1200-7-15').", parent=self)
             return


        self.result = {
            'name': name,
            'start': start,
            'end': end,
            'description': description
        }
        self.destroy()

    def cancel(self):
        self.result = None
        self.destroy()


class ImageViewer(ttk.Frame):
    """Displays an image from disk with pin/marker overlays."""

    PIN_RADIUS = 6

    def __init__(self, master, initial_content="", controller=None):
        super().__init__(master)
        self.controller = controller
        self.image_ref = None
        self._orig_image = None
        self._markers = []
        self._img_offset = (0, 0)  # top-left of displayed image on canvas
        self._img_scale = 1.0

        # Parse content (JSON with path+markers, or plain path for backward compat)
        self._parse_content(initial_content)

        # Controls
        toolbar = ttk.Frame(self)
        toolbar.pack(fill=tk.X, pady=(0, 5))

        ttk.Label(toolbar, text="Image path:").pack(side=tk.LEFT, padx=(0, 5))
        self.path_var = tk.StringVar(value=self._image_path)
        self.path_entry = ttk.Entry(toolbar, textvariable=self.path_var, width=50, state="readonly")
        self.path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        self._fit_mode = tk.BooleanVar(value=True)
        self._fit_btn = ttk.Button(toolbar, text="Full Size", command=self._toggle_fit)
        self._fit_btn.pack(side=tk.LEFT, padx=2)

        ttk.Label(self, text="Right-click: place/edit pins & labels | Shift+drag: reposition",
                 font=('Helvetica', 8), foreground='gray').pack(fill=tk.X, padx=5)

        # Scrollable canvas
        canvas_frame = ttk.Frame(self)
        canvas_frame.pack(fill=tk.BOTH, expand=True)
        self.canvas = tk.Canvas(canvas_frame, bg="#2b2b2b")
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vscroll = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL, command=self.canvas.yview)
        vscroll.pack(side=tk.RIGHT, fill=tk.Y)
        hscroll = ttk.Scrollbar(self, orient=tk.HORIZONTAL, command=self.canvas.xview)
        hscroll.pack(fill=tk.X)
        self.canvas.configure(xscrollcommand=hscroll.set, yscrollcommand=vscroll.set)

        # Bindings - use Button-3 for right-click (works on both Windows and Linux)
        self.canvas.bind('<Button-3>', self._on_right_click)
        self.canvas.bind('<Motion>', self._on_hover)
        self._tooltip = None
        self._hover_pin = None
        self._drag_label_idx = None
        self._blink_after = None
        self.canvas.bind('<Shift-ButtonPress-1>', self._on_shift_drag_start)
        self.canvas.bind('<Shift-B1-Motion>', self._on_shift_drag_motion)
        self.canvas.bind('<Shift-ButtonRelease-1>', self._on_shift_drag_end)

        self.after(50, self._initial_load)

    def _initial_load(self):
        """On first open, prompt for image if no path is set."""
        if not self.path_var.get().strip():
            self._browse()
        self._load_image()

    def _parse_content(self, content):
        """Parse stored content - JSON format or plain path for backward compat."""
        content = content.strip()
        if not content:
            self._image_path = ""
            self._markers = []
            self._labels = []
            return
        try:
            data = json.loads(content)
            if isinstance(data, dict) and "path" in data:
                self._image_path = data.get("path", "")
                self._markers = data.get("markers", [])
                self._labels = data.get("labels", [])
                return
        except (json.JSONDecodeError, ValueError):
            pass
        # Plain string fallback
        self._image_path = content
        self._markers = []
        self._labels = []

    def _get_save_dir(self):
        """Get the directory of the .json save file."""
        if self.controller and self.controller.file_path:
            return os.path.dirname(os.path.abspath(self.controller.file_path))
        return None

    def _browse(self):
        """Browse for an image file relative to the save directory."""
        save_dir = self._get_save_dir()
        if not save_dir:
            messagebox.showwarning("No Save File", "Please save the world file first so images can be located relative to it.")
            return
        filepath = filedialog.askopenfilename(
            initialdir=save_dir,
            filetypes=[("Image Files", "*.png *.jpg *.jpeg *.gif *.bmp *.webp"), ("All Files", "*.*")],
            title="Select Image"
        )
        if filepath:
            rel_path = os.path.relpath(filepath, save_dir)
            self.path_var.set(rel_path)
            self._load_image()

    def _load_image(self):
        """Load and display the image."""
        from PIL import Image, ImageTk
        # Cancel any running animation
        if hasattr(self, '_anim_after') and self._anim_after:
            self.after_cancel(self._anim_after)
            self._anim_after = None
        self.canvas.delete("all")
        self.image_ref = None

        save_dir = self._get_save_dir()
        rel_path = self.path_var.get().strip()
        if not save_dir or not rel_path:
            self.canvas.create_text(200, 100, text="No image path set" if not rel_path else "Save file first to resolve path",
                                   fill="gray", font=('Helvetica', 12))
            return

        abs_path = os.path.normpath(os.path.join(save_dir, rel_path))
        if not os.path.isfile(abs_path):
            self.canvas.create_text(200, 100, text=f"File not found:\n{rel_path}",
                                   fill="gray", font=('Helvetica', 12))
            return

        try:
            img = Image.open(abs_path)
            self._orig_image = img
            self._anim_frames = None
            self._anim_index = 0
            self._anim_after = None

            # Check for animated GIF
            if getattr(img, 'is_animated', False):
                self._load_animated(img, abs_path)
            else:
                self._display_image(img)
        except Exception as e:
            self.canvas.create_text(200, 100, text=f"Error loading image:\n{e}",
                                   fill="red", font=('Helvetica', 10))

    def _load_animated(self, img, abs_path):
        """Load all frames of an animated GIF and pre-render them."""
        from PIL import Image, ImageTk
        frames = []
        durations = []
        try:
            while True:
                frames.append(img.copy().convert("RGBA"))
                durations.append(img.info.get('duration', 100))
                img.seek(img.tell() + 1)
        except EOFError:
            pass
        self._anim_raw_frames = frames
        self._anim_durations = durations
        self._anim_index = 0
        self._anim_photo_frames = None
        # Display first frame normally to set up canvas, then start animation
        self._display_image(frames[0])
        self._pre_render_anim_frames(frames)
        self._anim_image_id = self.canvas.find_withtag("bg_image")[0] if self.canvas.find_withtag("bg_image") else None
        self._animate()

    def _pre_render_anim_frames(self, frames):
        """Pre-resize and convert all frames to PhotoImage for smooth playback."""
        from PIL import Image, ImageTk
        self._anim_photo_frames = []
        for frame in frames:
            if self._fit_mode.get():
                cw = self.canvas.winfo_width() or 400
                ch = self.canvas.winfo_height() or 400
                ratio = min(cw / frame.width, ch / frame.height, 1.0)
                new_size = (max(1, int(frame.width * ratio)), max(1, int(frame.height * ratio)))
                resized = frame.resize(new_size, Image.LANCZOS)
                self._anim_photo_frames.append(ImageTk.PhotoImage(resized))
            else:
                self._anim_photo_frames.append(ImageTk.PhotoImage(frame))

    def _animate(self):
        """Cycle to next frame without clearing canvas."""
        if not self._anim_photo_frames:
            return
        self._anim_index = (self._anim_index + 1) % len(self._anim_photo_frames)
        photo = self._anim_photo_frames[self._anim_index]
        self.image_ref = photo  # Prevent GC
        if self._anim_image_id:
            self.canvas.itemconfig(self._anim_image_id, image=photo)
        delay = self._anim_durations[self._anim_index] or 100
        self._anim_after = self.after(delay, self._animate)

    def _display_image(self, img):
        """Display image with current fit mode and overlay pins."""
        from PIL import Image, ImageTk
        self.canvas.delete("all")
        if self._fit_mode.get():
            self.canvas.update_idletasks()
            cw = self.canvas.winfo_width() or 400
            ch = self.canvas.winfo_height() or 400
            ratio = min(cw / img.width, ch / img.height, 1.0)
            new_size = (max(1, int(img.width * ratio)), max(1, int(img.height * ratio)))
            display_img = img.resize(new_size, Image.LANCZOS)
            self.image_ref = ImageTk.PhotoImage(display_img)
            ox = (cw - new_size[0]) // 2
            oy = (ch - new_size[1]) // 2
            self._img_offset = (ox, oy)
            self._img_scale = ratio
            self.canvas.create_image(ox, oy, anchor="nw", image=self.image_ref, tags=("bg_image",))
            self.canvas.configure(scrollregion=(0, 0, cw, ch))
        else:
            self.image_ref = ImageTk.PhotoImage(img)
            self._img_offset = (0, 0)
            self._img_scale = 1.0
            self.canvas.create_image(0, 0, anchor="nw", image=self.image_ref, tags=("bg_image",))
            self.canvas.configure(scrollregion=(0, 0, img.width, img.height))
        self._draw_markers()

    def _toggle_fit(self):
        """Toggle between fit-to-window and full size."""
        self._fit_mode.set(not self._fit_mode.get())
        self._fit_btn.config(text="Full Size" if self._fit_mode.get() else "Fit to Window")
        self.canvas.xview_moveto(0)
        self.canvas.yview_moveto(0)
        if hasattr(self, '_anim_raw_frames') and self._anim_raw_frames:
            # Re-render animated frames for new mode
            if hasattr(self, '_anim_after') and self._anim_after:
                self.after_cancel(self._anim_after)
                self._anim_after = None
            self._display_image(self._anim_raw_frames[0])
            self._pre_render_anim_frames(self._anim_raw_frames)
            self._anim_image_id = self.canvas.find_withtag("bg_image")[0] if self.canvas.find_withtag("bg_image") else None
            self._anim_index = 0
            self._animate()
        elif self._orig_image:
            self._display_image(self._orig_image)

    def _draw_markers(self):
        """Draw all pin markers on the canvas at scaled positions."""
        self.canvas.delete("pins")
        if hasattr(self, '_blink_after') and self._blink_after:
            self.after_cancel(self._blink_after)
            self._blink_after = None
        if not self._orig_image:
            return
        iw, ih = self._orig_image.width, self._orig_image.height
        ox, oy = self._img_offset
        scale = self._img_scale
        r = self.PIN_RADIUS
        has_blink = False

        for i, marker in enumerate(self._markers):
            cx = ox + marker["x"] * iw * scale
            cy = oy + marker["y"] * ih * scale
            color = marker.get("color", "#FF0000")
            tags = ("pins", f"pin_{i}")
            if marker.get("blink"):
                tags = ("pins", "blink_pin", f"pin_{i}")
                has_blink = True
            self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r,
                                   fill=color, outline="white", width=2, tags=tags)
            label = marker.get("label", "")
            if label:
                self.canvas.create_text(cx, cy - r - 8, text=label,
                                       fill="white", font=('Helvetica', 8, 'bold'), tags=tags)

        if has_blink:
            self._blink_visible = True
            self._blink_after = self.after(500, self._blink_pins)
        self._draw_labels()

    def _blink_pins(self):
        """Toggle visibility of blinking pins."""
        self._blink_visible = not self._blink_visible
        state = "normal" if self._blink_visible else "hidden"
        self.canvas.itemconfigure("blink_pin", state=state)
        self._blink_after = self.after(500, self._blink_pins)

    def _draw_labels(self):
        """Draw all floating text labels on the canvas."""
        self.canvas.delete("labels")
        if not self._orig_image:
            return
        iw, ih = self._orig_image.width, self._orig_image.height
        ox, oy = self._img_offset
        scale = self._img_scale

        for i, label in enumerate(self._labels):
            cx = ox + label["x"] * iw * scale
            cy = oy + label["y"] * ih * scale
            color = label.get("color", "#FFFFFF")
            size = max(1, int(label.get("size", 12) * scale))
            text = label.get("text", "")
            border = label.get("border", False)
            font = ('Helvetica', size, 'bold')

            if border:
                # Draw background rectangle
                tid = self.canvas.create_text(cx, cy, text=text, fill=color, font=font,
                                            anchor="center", tags=("labels", f"label_{i}"))
                bbox = self.canvas.bbox(tid)
                if bbox:
                    pad = 4
                    bg_color = label.get("bg_color", "#000000")
                    border_color = label.get("border_color", "#FFFFFF")
                    self.canvas.create_rectangle(bbox[0] - pad, bbox[1] - pad,
                                               bbox[2] + pad, bbox[3] + pad,
                                               fill=bg_color, outline=border_color, width=1,
                                               tags=("labels", f"labelbg_{i}"))
                    self.canvas.tag_raise(tid)
            else:
                self.canvas.create_text(cx, cy, text=text, fill=color, font=font,
                                       anchor="center", tags=("labels", f"label_{i}"))

    def _canvas_to_image_coords(self, cx, cy):
        """Convert canvas pixel coords to normalized image coords (0-1)."""
        if not self._orig_image:
            return None, None
        ox, oy = self._img_offset
        scale = self._img_scale
        iw, ih = self._orig_image.width, self._orig_image.height
        x = (cx - ox) / (iw * scale)
        y = (cy - oy) / (ih * scale)
        if 0 <= x <= 1 and 0 <= y <= 1:
            return x, y
        return None, None

    def _find_pin_at(self, cx, cy):
        """Find marker index at canvas position, or None."""
        if not self._orig_image:
            return None
        ox, oy = self._img_offset
        scale = self._img_scale
        iw, ih = self._orig_image.width, self._orig_image.height
        r = self.PIN_RADIUS + 4
        for i, marker in enumerate(self._markers):
            px = ox + marker["x"] * iw * scale
            py = oy + marker["y"] * ih * scale
            if abs(cx - px) <= r and abs(cy - py) <= r:
                return i
        return None

    def _on_hover(self, event):
        """Show tooltip with note when hovering over a pin (800ms delay)."""
        cx = self.canvas.canvasx(event.x)
        cy = self.canvas.canvasy(event.y)
        pin_idx = self._find_pin_at(cx, cy)

        if pin_idx == self._hover_pin:
            return

        # Cancel pending tooltip
        if hasattr(self, '_hover_after') and self._hover_after:
            self.after_cancel(self._hover_after)
            self._hover_after = None

        # Destroy old tooltip
        if self._tooltip:
            self._tooltip.destroy()
            self._tooltip = None
        self._hover_pin = pin_idx

        if pin_idx is None:
            return

        marker = self._markers[pin_idx]
        lines = []
        if marker.get("label"):
            lines.append(marker["label"])
        if marker.get("note"):
            lines.append(marker["note"])
        if not lines:
            return

        def show_tip():
            tip = tk.Toplevel(self)
            tip.wm_overrideredirect(True)
            tip.wm_geometry(f"+{event.x_root + 12}+{event.y_root + 12}")
            lbl = tk.Label(tip, text="\n".join(lines), background="#ffffe0",
                          relief="solid", borderwidth=1, font=('Helvetica', 9),
                          justify=tk.LEFT, wraplength=250)
            lbl.pack()
            self._tooltip = tip

        self._hover_after = self.after(800, show_tip)

    def _on_shift_drag_start(self, event):
        """Start dragging a pin or label if shift+click is on one."""
        cx = self.canvas.canvasx(event.x)
        cy = self.canvas.canvasy(event.y)
        self._drag_label_idx = None
        self._drag_pin_idx = None
        pin_idx = self._find_pin_at(cx, cy)
        if pin_idx is not None:
            self._drag_pin_idx = pin_idx
            self.canvas.config(cursor="fleur")
            return
        label_idx = self._find_label_at(cx, cy)
        if label_idx is not None:
            self._drag_label_idx = label_idx
            self.canvas.config(cursor="fleur")

    def _on_shift_drag_motion(self, event):
        """Move the pin or label to follow the cursor."""
        if self._drag_pin_idx is None and self._drag_label_idx is None:
            return
        cx = self.canvas.canvasx(event.x)
        cy = self.canvas.canvasy(event.y)
        x, y = self._canvas_to_image_coords(cx, cy)
        if x is None:
            return
        if self._drag_pin_idx is not None:
            self._markers[self._drag_pin_idx]["x"] = x
            self._markers[self._drag_pin_idx]["y"] = y
            self._draw_markers()
        elif self._drag_label_idx is not None:
            self._labels[self._drag_label_idx]["x"] = x
            self._labels[self._drag_label_idx]["y"] = y
            self._draw_labels()

    def _on_shift_drag_end(self, event):
        """Finish dragging."""
        self._drag_label_idx = None
        self._drag_pin_idx = None
        self.canvas.config(cursor="")

    def _on_right_click(self, event):
        """Right-click: place pin/label on image, or edit/delete existing."""
        cx = self.canvas.canvasx(event.x)
        cy = self.canvas.canvasy(event.y)

        pin_idx = self._find_pin_at(cx, cy)
        label_idx = self._find_label_at(cx, cy)
        menu = tk.Menu(self, tearoff=0)

        if pin_idx is not None:
            marker = self._markers[pin_idx]
            if marker.get("link") and self.controller:
                menu.add_command(label=f"Open: {marker.get('label', marker['link'])}",
                               command=lambda: self.controller._open_file_editor(marker["link"].split('/')))
                menu.add_separator()
            menu.add_command(label="Edit Pin", command=lambda: self._edit_pin(pin_idx))
            menu.add_command(label="Delete Pin", command=lambda: self._delete_pin(pin_idx))
        elif label_idx is not None:
            lbl = self._labels[label_idx]
            if lbl.get("link") and self.controller:
                menu.add_command(label=f"Open: {lbl['link'].split('/')[-1]}",
                               command=lambda: self.controller._open_file_editor(lbl["link"].split('/')))
                menu.add_separator()
            menu.add_command(label="Edit Label", command=lambda: self._edit_label(label_idx))
            menu.add_command(label="Delete Label", command=lambda: self._delete_label(label_idx))
        else:
            x, y = self._canvas_to_image_coords(cx, cy)
            if x is not None:
                menu.add_command(label="Place Pin Here", command=lambda: self._add_pin(x, y))
                menu.add_command(label="Place Label Here", command=lambda: self._add_label(x, y))
            else:
                return

        popup_menu(menu, event.x_root, event.y_root)

    def _find_label_at(self, cx, cy):
        """Find label index at canvas position, or None."""
        if not self._orig_image:
            return None
        ox, oy = self._img_offset
        scale = self._img_scale
        iw, ih = self._orig_image.width, self._orig_image.height
        for i, label in enumerate(self._labels):
            lx = ox + label["x"] * iw * scale
            ly = oy + label["y"] * ih * scale
            size = label.get("size", 12)
            # Approximate hit area based on text size
            half_w = max(len(label.get("text", "")) * size * 0.35, 20)
            half_h = size
            if abs(cx - lx) <= half_w and abs(cy - ly) <= half_h:
                return i
        return None

    def _add_pin(self, x, y):
        """Add a new pin at normalized coords and open edit dialog."""
        marker = {"x": x, "y": y, "label": "", "note": "", "link": "", "color": "#FF0000"}
        dialog = PinEditDialog(self, marker, self.controller)
        if dialog.result:
            self._markers.append(dialog.result)
            self._draw_markers()

    def _edit_pin(self, idx):
        """Edit an existing pin."""
        dialog = PinEditDialog(self, self._markers[idx], self.controller)
        if dialog.result:
            self._markers[idx] = dialog.result
            self._draw_markers()

    def _delete_pin(self, idx):
        """Delete a pin."""
        if messagebox.askyesno("Delete Pin", f"Delete pin '{self._markers[idx].get('label', 'Unnamed')}'?"):
            del self._markers[idx]
            self._draw_markers()

    def _add_label(self, x, y):
        """Add a new floating text label."""
        label = {"x": x, "y": y, "text": "", "color": "#000000", "size": 12, "border": False, "bg_color": "#000000", "border_color": "#FFFFFF"}
        dialog = LabelEditDialog(self, label)
        if dialog.result:
            self._labels.append(dialog.result)
            self._draw_labels()

    def _edit_label(self, idx):
        """Edit an existing label."""
        dialog = LabelEditDialog(self, self._labels[idx])
        if dialog.result:
            self._labels[idx] = dialog.result
            self._draw_labels()

    def _delete_label(self, idx):
        """Delete a label."""
        if messagebox.askyesno("Delete Label", f"Delete label '{self._labels[idx].get('text', '')}'?"):
            del self._labels[idx]
            self._draw_labels()

    def get_content(self):
        """Return JSON with image path, markers, and labels."""
        return json.dumps({"path": self.path_var.get().strip(), "markers": self._markers, "labels": self._labels})


class PinEditDialog(tk.Toplevel):
    """Dialog for editing a pin's label, note, link, and color."""
    def __init__(self, parent, marker, controller=None):
        super().__init__(parent)
        self.transient(parent)
        self.grab_set()
        self.title("Edit Pin")
        self.result = None
        self.controller = controller
        self.geometry("400x250")

        ttk.Label(self, text="Label:").grid(row=0, column=0, sticky="w", padx=10, pady=5)
        self.label_var = tk.StringVar(value=marker.get("label", ""))
        ttk.Entry(self, textvariable=self.label_var, width=30).grid(row=0, column=1, sticky="ew", padx=10, pady=5)

        ttk.Label(self, text="Note:").grid(row=1, column=0, sticky="nw", padx=10, pady=5)
        self.note_text = tk.Text(self, width=30, height=3)
        self.note_text.grid(row=1, column=1, sticky="ew", padx=10, pady=5)
        self.note_text.insert("1.0", marker.get("note", ""))

        ttk.Label(self, text="Link:").grid(row=2, column=0, sticky="w", padx=10, pady=5)
        link_frame = ttk.Frame(self)
        link_frame.grid(row=2, column=1, sticky="ew", padx=10, pady=5)
        self.link_var = tk.StringVar(value=marker.get("link", ""))
        ttk.Entry(link_frame, textvariable=self.link_var, width=22).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(link_frame, text="Pick", command=self._pick_link).pack(side=tk.LEFT, padx=(5, 0))

        ttk.Label(self, text="Color:").grid(row=3, column=0, sticky="w", padx=10, pady=5)
        color_frame = ttk.Frame(self)
        color_frame.grid(row=3, column=1, sticky="ew", padx=10, pady=5)
        self.color_var = tk.StringVar(value=marker.get("color", "#FF0000"))
        self.color_preview = tk.Label(color_frame, width=3, bg=self.color_var.get())
        self.color_preview.pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(color_frame, text="Choose", command=self._pick_color).pack(side=tk.LEFT)

        # Store original coords
        self._x = marker.get("x", 0)
        self._y = marker.get("y", 0)

        self.blink_var = tk.BooleanVar(value=marker.get("blink", False))
        ttk.Checkbutton(self, text="Blink", variable=self.blink_var).grid(row=4, column=0, columnspan=2, sticky="w", padx=10, pady=5)

        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=5, column=0, columnspan=2, pady=10)
        ttk.Button(btn_frame, text="OK", command=self._ok).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Cancel", command=self._cancel).pack(side=tk.LEFT, padx=5)

        self.columnconfigure(1, weight=1)
        self.bind('<Return>', lambda e: self._ok())
        self.bind('<Escape>', lambda e: self._cancel())
        self.wait_window(self)

    def _pick_link(self):
        """Open VFS file picker to select a link target."""
        if not self.controller:
            return
        picker = VFSFilePicker(self, self.controller.vfs, self.controller.root_name)
        if picker.result:
            self.link_var.set(picker.result)

    def _pick_color(self):
        """Open color chooser."""
        from tkinter import colorchooser
        color = colorchooser.askcolor(initialcolor=self.color_var.get(), parent=self)
        if color[1]:
            self.color_var.set(color[1])
            self.color_preview.config(bg=color[1])

    def _ok(self):
        self.result = {
            "x": self._x, "y": self._y,
            "label": self.label_var.get().strip(),
            "note": self.note_text.get("1.0", tk.END).strip(),
            "link": self.link_var.get().strip(),
            "color": self.color_var.get(),
            "blink": self.blink_var.get()
        }
        self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()


class LabelEditDialog(tk.Toplevel):
    """Dialog for editing a floating text label."""
    _last_color = "#000000"
    _last_size = 12
    _last_border = False
    _last_bg_color = "#000000"
    _last_border_color = "#FFFFFF"

    def __init__(self, parent, label_data):
        super().__init__(parent)
        self.transient(parent)
        self.grab_set()
        self.title("Edit Label")
        self.result = None
        self._parent = parent
        self.geometry("350x300")

        self._load_defaults_from_config()

        self._x = label_data.get("x", 0)
        self._y = label_data.get("y", 0)
        is_new = not label_data.get("text", "")

        ttk.Label(self, text="Text:").grid(row=0, column=0, sticky="w", padx=10, pady=5)
        self.text_var = tk.StringVar(value=label_data.get("text", ""))
        ttk.Entry(self, textvariable=self.text_var, width=30).grid(row=0, column=1, sticky="ew", padx=10, pady=5)

        ttk.Label(self, text="Size:").grid(row=1, column=0, sticky="w", padx=10, pady=5)
        self.size_var = tk.IntVar(value=LabelEditDialog._last_size if is_new else label_data.get("size", 12))
        ttk.Spinbox(self, from_=6, to=72, width=6, textvariable=self.size_var).grid(row=1, column=1, sticky="w", padx=10, pady=5)

        ttk.Label(self, text="Text Color:").grid(row=2, column=0, sticky="w", padx=10, pady=5)
        self.color_var = tk.StringVar(value=LabelEditDialog._last_color if is_new else label_data.get("color", "#000000"))
        self._color_btn(self, self.color_var, 2)

        self.border_var = tk.BooleanVar(value=LabelEditDialog._last_border if is_new else label_data.get("border", False))
        ttk.Checkbutton(self, text="Show border/background", variable=self.border_var,
                       command=self._toggle_border_options).grid(row=3, column=0, columnspan=2, sticky="w", padx=10, pady=5)

        self.bg_label = ttk.Label(self, text="Background:")
        self.bg_label.grid(row=4, column=0, sticky="w", padx=10, pady=5)
        self.bg_color_var = tk.StringVar(value=LabelEditDialog._last_bg_color if is_new else label_data.get("bg_color", "#000000"))
        self.bg_frame = self._color_btn(self, self.bg_color_var, 4)

        self.bc_label = ttk.Label(self, text="Border Color:")
        self.bc_label.grid(row=5, column=0, sticky="w", padx=10, pady=5)
        self.border_color_var = tk.StringVar(value=LabelEditDialog._last_border_color if is_new else label_data.get("border_color", "#FFFFFF"))
        self.bc_frame = self._color_btn(self, self.border_color_var, 5)

        ttk.Label(self, text="Link:").grid(row=6, column=0, sticky="w", padx=10, pady=5)
        link_frame = ttk.Frame(self)
        link_frame.grid(row=6, column=1, sticky="ew", padx=10, pady=5)
        self.link_var = tk.StringVar(value=label_data.get("link", ""))
        ttk.Entry(link_frame, textvariable=self.link_var, width=22).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(link_frame, text="Pick", command=self._pick_link).pack(side=tk.LEFT, padx=(5, 0))

        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=7, column=0, columnspan=2, pady=10)
        ttk.Button(btn_frame, text="OK", command=self._ok).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Cancel", command=self._cancel).pack(side=tk.LEFT, padx=5)

        self.columnconfigure(1, weight=1)
        self.bind('<Return>', lambda e: self._ok())
        self.bind('<Escape>', lambda e: self._cancel())
        self._toggle_border_options()
        self.wait_window(self)

    def _load_defaults_from_config(self):
        controller = getattr(self._parent, 'controller', None)
        if controller:
            config = controller._load_config()
            d = config.get("label_defaults", {})
            if d:
                LabelEditDialog._last_color = d.get("color", LabelEditDialog._last_color)
                LabelEditDialog._last_size = d.get("size", LabelEditDialog._last_size)
                LabelEditDialog._last_border = d.get("border", LabelEditDialog._last_border)
                LabelEditDialog._last_bg_color = d.get("bg_color", LabelEditDialog._last_bg_color)
                LabelEditDialog._last_border_color = d.get("border_color", LabelEditDialog._last_border_color)

    def _save_defaults_to_config(self):
        controller = getattr(self._parent, 'controller', None)
        if controller:
            config = controller._load_config()
            config["label_defaults"] = {
                "color": self.color_var.get(),
                "size": self.size_var.get(),
                "border": self.border_var.get(),
                "bg_color": self.bg_color_var.get(),
                "border_color": self.border_color_var.get()
            }
            try:
                with open(controller.CONFIG_FILE, 'w') as f:
                    json.dump(config, f, indent=2)
            except Exception:
                pass

    def _pick_link(self):
        """Open VFS file picker to select a link target."""
        controller = getattr(self._parent, 'controller', None)
        if not controller:
            return
        picker = VFSFilePicker(self, controller.vfs, controller.root_name)
        if picker.result:
            self.link_var.set(picker.result)

    def _toggle_border_options(self):
        if self.border_var.get():
            self.bg_label.grid()
            self.bg_frame.grid()
            self.bc_label.grid()
            self.bc_frame.grid()
        else:
            self.bg_label.grid_remove()
            self.bg_frame.grid_remove()
            self.bc_label.grid_remove()
            self.bc_frame.grid_remove()

    def _color_btn(self, parent, var, row):
        """Create a color preview + choose button in the given row."""
        frame = ttk.Frame(parent)
        frame.grid(row=row, column=1, sticky="ew", padx=10, pady=5)
        preview = tk.Label(frame, width=3, bg=var.get())
        preview.pack(side=tk.LEFT, padx=(0, 5))
        def pick():
            from tkinter import colorchooser
            color = colorchooser.askcolor(initialcolor=var.get(), parent=self)
            if color[1]:
                var.set(color[1])
                preview.config(bg=color[1])
        ttk.Button(frame, text="Choose", command=pick).pack(side=tk.LEFT)
        return frame

    def _ok(self):
        text = self.text_var.get().strip()
        if not text:
            messagebox.showerror("Error", "Text is required.", parent=self)
            return
        LabelEditDialog._last_color = self.color_var.get()
        LabelEditDialog._last_size = self.size_var.get()
        LabelEditDialog._last_border = self.border_var.get()
        LabelEditDialog._last_bg_color = self.bg_color_var.get()
        LabelEditDialog._last_border_color = self.border_color_var.get()
        self._save_defaults_to_config()

        self.result = {
            "x": self._x, "y": self._y,
            "text": text,
            "color": self.color_var.get(),
            "size": self.size_var.get(),
            "border": self.border_var.get(),
            "bg_color": self.bg_color_var.get(),
            "border_color": self.border_color_var.get(),
            "link": self.link_var.get().strip()
        }
        self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()


class CSVGrid(ttk.Frame):
    """A tabular data editor for CSV files. (Unchanged for brevity)"""
    def __init__(self, master, initial_content="", name_regex=None, controller=None):
        super().__init__(master)
        self.name_regex = name_regex 
        self.controller = controller 
        self.cell_editor = None 
        
        self.grid_container = ttk.Frame(self)
        self.grid_container.pack(fill=tk.BOTH, expand=True)

        self._load_data_and_ui(initial_content)


    def _load_data_and_ui(self, content):
        for widget in self.grid_container.winfo_children():
            widget.destroy()
            
        self.data = self._parse_csv(content) 
        
        if not self.data or not self.data[0]:
            self.data = [["Col 1", "Col 2"], ["", ""]]
        
        self.header = self.data[0]
        self.rows = self.data[1:]
        self._ensure_blank_row()
        
        self._setup_grid_ui()


    def _parse_csv(self, content):
        if not content.strip():
            return []
        
        import csv
        from io import StringIO
        
        try:
            reader = csv.reader(StringIO(content))
            parsed_data = [row for row in reader]
        except:
            # Fallback to simple split if CSV parsing fails
            lines = content.strip().split('\n')
            parsed_data = [line.split(',') for line in lines]
            
        if parsed_data:
            header_len = len(parsed_data[0])
            for i in range(len(parsed_data)):
                while len(parsed_data[i]) < header_len:
                    parsed_data[i].append("") 
                if len(parsed_data[i]) > header_len:
                    parsed_data[i] = parsed_data[i][:header_len]
        
        return parsed_data

    def _is_checkbox_value(self, value):
        return str(value).strip().upper() in ("TRUE", "FALSE", "☑", "☐")

    def _get_checkbox_display(self, value):
        v = str(value).strip().upper()
        if v in ("TRUE", "☑"):
            return "☑"
        if v in ("FALSE", "☐"):
            return "☐"
        return value

    def _toggle_checkbox(self, value):
        v = str(value).strip().upper()
        return "TRUE" if v in ("FALSE", "☐") else "FALSE"

    def _get_cell_display(self, value):
        """Get display value for a cell, handling checkboxes and links."""
        if self._is_checkbox_value(value):
            return self._get_checkbox_display(value)
        m = LINK_REGEX.match(str(value).strip())
        if m:
            display = m.group(2) if m.group(2) else m.group(1).split('/')[-1]
            return f"⇗ {display}"
        return value

    def _setup_grid_ui(self):
        # Hotkey legend
        legend_frame = ttk.Frame(self.grid_container)
        legend_frame.pack(fill=tk.X, pady=(0, 5))
        
        legend_text = "Hotkeys: Double-Click=Edit Cell | Del=Delete Row | Right-Click=Context Menu"
        ttk.Label(legend_frame, text=legend_text, font=('Helvetica', 8), foreground='gray').pack()
        
        tree_frame = ttk.Frame(self.grid_container)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        
        self.tree = ttk.Treeview(tree_frame, columns=self.header, show='headings')
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Configure treeview with visible grid lines
        # Using fieldbackground as the "grid line" color between rows
        style = ttk.Style()
        style.configure("CSVGrid.Treeview", rowheight=26, 
                       fieldbackground="#c0c0c0", borderwidth=1, relief="solid")
        style.configure("CSVGrid.Treeview.Heading", relief="raised", borderwidth=2,
                       font=('Helvetica', 9, 'bold'), background="#d0d0d0")
        self.tree.configure(style="CSVGrid.Treeview")
        
        for col in self.header:
            # Use | separator in column display via stretch
            self.tree.column(col, anchor="w", width=120, minwidth=60)
            self.tree.heading(col, text=col)

        for i, row in enumerate(self.rows):
            row_to_insert = row[:len(self.header)] if len(row) > len(self.header) else row + [""] * (len(self.header) - len(row))
            display_row = [self._get_cell_display(cell) for cell in row_to_insert]
            tag = "evenrow" if i % 2 == 0 else "oddrow"
            self.tree.insert('', 'end', values=display_row, tags=(tag,))

        # Auto-center columns where all values are checkboxes
        for col_idx, col in enumerate(self.header):
            if self.rows and all(self._is_checkbox_value(row[col_idx]) for row in self.rows if col_idx < len(row)):
                self.tree.column(col, anchor="center")
            
        # Row colors create visible horizontal separation against the gray fieldbackground
        self.tree.tag_configure("evenrow", background="#ffffff")
        self.tree.tag_configure("oddrow", background="#f4f4f4") 

        vscroll = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=vscroll.set)
        vscroll.pack(side=tk.RIGHT, fill=tk.Y)

        hscroll = ttk.Scrollbar(self.grid_container, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(xscrollcommand=hscroll.set)
        hscroll.pack(side=tk.BOTTOM, fill=tk.X)

        self.tree.bind('<Double-1>', self._on_double_click)
        self.tree.bind('<Delete>', self._on_delete_key)
        self.tree.bind('<ButtonRelease-3>', self._on_right_click)
        self.tree.bind('<Tab>', self._on_tab_key)
        self.tree.bind('<Return>', self._on_enter_key)
        self.tree.bind('<ButtonRelease-1>', self._on_single_click)
        
        # Column header drag-and-drop
        self._col_drag_index = None
        self.tree.bind('<ButtonPress-1>', self._on_col_drag_start, add='+')
        self.tree.bind('<B1-Motion>', self._on_col_drag_motion)
        self.tree.bind('<ButtonRelease-1>', self._on_col_drag_drop, add='+')

        # Row drag-and-drop reordering
        self._row_drag_item = None
        self._row_drop_indicator = None
        self.tree.bind('<ButtonPress-1>', self._on_row_drag_start, add='+')
        self.tree.bind('<B1-Motion>', self._on_row_drag_motion, add='+')
        self.tree.bind('<ButtonRelease-1>', self._on_row_drag_drop, add='+')

    def _on_col_drag_start(self, event):
        if self.tree.identify("region", event.x, event.y) == "heading":
            col_id = self.tree.identify_column(event.x)
            self._col_drag_index = int(col_id.replace('#', '')) - 1
            self._col_drag_start_x = event.x
            self._col_drag_active = False
            self._col_drop_target = None
        else:
            self._col_drag_index = None

    def _on_col_drag_motion(self, event):
        if self._col_drag_index is None:
            return

        # Require minimum 8px drag before activating
        if not self._col_drag_active:
            if abs(event.x - self._col_drag_start_x) < 8:
                return
            self._col_drag_active = True

        self.tree.config(cursor="sb_h_double_arrow")
        
        # Determine drop target
        if self.tree.identify("region", event.x, event.y) == "heading":
            col_id = self.tree.identify_column(event.x)
            if col_id:
                drop_idx = int(col_id.replace('#', '')) - 1
                if drop_idx != self._col_drag_index and drop_idx != self._col_drop_target:
                    self._col_drop_target = drop_idx
                    self._show_col_gap(drop_idx)
        else:
            if self._col_drop_target is not None:
                self._col_drop_target = None
                self._remove_col_gap()

    def _show_col_gap(self, drop_idx):
        """Insert a blank spacer column at the drop position."""
        self._remove_col_gap()
        spacer_id = "__spacer__"
        cols = list(self.tree["columns"])
        insert_pos = drop_idx if drop_idx < self._col_drag_index else drop_idx + 1
        if insert_pos > len(cols):
            insert_pos = len(cols)
        cols.insert(insert_pos, spacer_id)
        self.tree["columns"] = cols
        
        # Configure spacer column - narrow with light blue indicator text
        self.tree.column(spacer_id, width=30, minwidth=30, stretch=False)
        self.tree.heading(spacer_id, text="│")
        
        # Reconfigure original columns
        for col in self.header:
            self.tree.column(col, anchor="w", width=120, minwidth=60)
            self.tree.heading(col, text=col)
        
        # Update row values to include a blue bar character in the spacer column
        for item_id in self.tree.get_children():
            values = list(self.tree.item(item_id, 'values'))
            # Insert spacer value at the same position
            values.insert(insert_pos, "│")
            self.tree.item(item_id, values=values)
        
        # Tag configure for light blue background on all rows
        self.tree.tag_configure('evenrow', background='#ffffff')
        self.tree.tag_configure('oddrow', background='#f4f4f4')
        
        self._col_gap_active = True
        self._col_gap_pos = insert_pos

    def _remove_col_gap(self):
        """Remove the spacer column if present."""
        if not getattr(self, '_col_gap_active', False):
            return
        cols = list(self.tree["columns"])
        if "__spacer__" in cols:
            gap_pos = getattr(self, '_col_gap_pos', None)
            # Remove spacer values from rows
            if gap_pos is not None:
                for item_id in self.tree.get_children():
                    values = list(self.tree.item(item_id, 'values'))
                    if gap_pos < len(values):
                        values.pop(gap_pos)
                    self.tree.item(item_id, values=values)
            cols.remove("__spacer__")
            self.tree["columns"] = cols
            # Reconfigure columns
            for col in self.header:
                self.tree.column(col, anchor="w", width=120, minwidth=60)
                self.tree.heading(col, text=col)
        self._col_gap_active = False

    def _on_col_drag_drop(self, event):
        if self._col_drag_index is None:
            return
        self.tree.config(cursor="")
        self._remove_col_gap()
        
        if self.tree.identify("region", event.x, event.y) != "heading":
            self._col_drag_index = None
            return
        col_id = self.tree.identify_column(event.x)
        drop_index = int(col_id.replace('#', '')) - 1
        src = self._col_drag_index
        self._col_drag_index = None
        if src == drop_index or src < 0 or drop_index < 0:
            return
        if src >= len(self.header) or drop_index >= len(self.header):
            return
        # Collect current data from treeview
        all_rows = []
        for item_id in self.tree.get_children():
            row = []
            for v in self.tree.item(item_id, 'values'):
                s = str(v)
                if s == "☑":
                    row.append("TRUE")
                elif s == "☐":
                    row.append("FALSE")
                else:
                    row.append(s)
            all_rows.append(row)
        # Reorder header
        col = self.header.pop(src)
        self.header.insert(drop_index, col)
        # Reorder all rows
        for row in all_rows:
            if len(row) > src:
                val = row.pop(src)
                row.insert(drop_index, val)
        # Update internal state and rebuild
        self.rows = all_rows
        full_data = [self.header] + self.rows
        updated_content = self._list_to_csv(full_data)
        self._load_data_and_ui(updated_content)

    def _on_row_drag_start(self, event):
        """Start row drag if clicking on a cell region."""
        if self.tree.identify("region", event.x, event.y) == "cell":
            item = self.tree.identify_row(event.y)
            if item:
                self._row_drag_item = item
                self._row_drag_start_y = event.y
                self._row_drag_active = False
                self._row_drop_insert_index = None
            else:
                self._row_drag_item = None
        else:
            self._row_drag_item = None

    def _on_row_drag_motion(self, event):
        """Show insertion indicator during row drag."""
        if not self._row_drag_item or self._col_drag_index is not None:
            return

        # Require minimum 8px drag before activating
        if not self._row_drag_active:
            if abs(event.y - self._row_drag_start_y) < 8:
                return
            self._row_drag_active = True

        target = self.tree.identify_row(event.y)

        if not target or target == self._row_drag_item or target == self._row_drop_indicator:
            return

        bbox = self.tree.bbox(target)
        if not bbox:
            return

        x, y, w, h = bbox
        rel_y = event.y - y

        # Calculate insert index excluding the indicator from the item list
        real_items = [i for i in self.tree.get_children() if i != self._row_drop_indicator]
        if target not in real_items:
            return
        target_index = real_items.index(target)
        insert_index = target_index if rel_y < h / 2 else target_index + 1

        # Only update if position changed
        if insert_index == self._row_drop_insert_index:
            return
        self._row_drop_insert_index = insert_index

        # Clear previous indicator
        if self._row_drop_indicator:
            try:
                self.tree.delete(self._row_drop_indicator)
            except Exception:
                pass
            self._row_drop_indicator = None

        # Determine tree insert position (accounting for items in actual tree)
        all_items = list(self.tree.get_children())
        if insert_index < len(real_items):
            tree_insert_index = all_items.index(real_items[insert_index])
        else:
            tree_insert_index = 'end'

        self.tree.config(cursor="hand2")
        self._row_drop_indicator = self.tree.insert('', tree_insert_index,
                                                     values=['━' * 10] * len(self.header),
                                                     tags=('row_spacer',))
        self.tree.tag_configure('row_spacer', foreground='#1976D2', background='#E3F2FD')

    def _on_row_drag_drop(self, event):
        """Complete row reorder on drop."""
        if not self._row_drag_item or self._col_drag_index is not None or not self._row_drag_active:
            if self._row_drop_indicator:
                try:
                    self.tree.delete(self._row_drop_indicator)
                except Exception:
                    pass
                self._row_drop_indicator = None
            self._row_drag_item = None
            return

        self.tree.config(cursor="")

        # Get source index before removing indicator (exclude indicator from count)
        all_items = [i for i in self.tree.get_children() if i != self._row_drop_indicator]
        src_index = all_items.index(self._row_drag_item) if self._row_drag_item in all_items else None
        drop_index = self._row_drop_insert_index

        # Remove indicator
        if self._row_drop_indicator:
            try:
                self.tree.delete(self._row_drop_indicator)
            except Exception:
                pass
            self._row_drop_indicator = None

        self._row_drag_item = None
        self._row_drop_insert_index = None

        if src_index is None or drop_index is None:
            return

        # Adjust drop_index: the indicator was occupying a slot, so account for items before it
        if drop_index > src_index:
            drop_index -= 1

        if drop_index == src_index:
            return

        # Reorder rows data
        row = self.rows.pop(src_index)
        self.rows.insert(drop_index, row)

        full_data = [self.header] + self.rows
        updated_content = self._list_to_csv(full_data)
        self._load_data_and_ui(updated_content)

    def _on_single_click(self, event):
        region = self.tree.identify("region", event.x, event.y)
        if region != "cell":
            return
        item_id = self.tree.identify_row(event.y)
        column_id = self.tree.identify_column(event.x)
        if not item_id or not column_id:
            return
        col_index = int(column_id.replace('#', '')) - 1
        if col_index < 0 or col_index >= len(self.header):
            return
        current_values = list(self.tree.item(item_id, 'values'))
        current_value = current_values[col_index]
        if self._is_checkbox_value(current_value):
            new_value = self._toggle_checkbox(current_value)
            current_values[col_index] = self._get_checkbox_display(new_value)
            self.tree.item(item_id, values=current_values)

    def _on_right_click(self, event):
        region = self.tree.identify("region", event.x, event.y)
        
        if region == "heading":
            column_id = self.tree.identify_column(event.x)
            col_index = int(column_id.replace('#', '')) - 1
            if 0 <= col_index < len(self.header):
                self._show_column_menu(event, col_index)
        elif region == "cell":
            item_id = self.tree.identify_row(event.y)
            column_id = self.tree.identify_column(event.x)
            col_index = int(column_id.replace('#', '')) - 1 if column_id else 0
            if item_id:
                self._show_row_menu(event, item_id, col_index)

    def _on_double_click(self, event):
        region = self.tree.identify("region", event.x, event.y)
        
        if region == "heading":
            column_id = self.tree.identify_column(event.x)
            col_index = int(column_id.replace('#', '')) - 1
            if 0 <= col_index < len(self.header):
                self._rename_column(col_index)
            return
        
        if region != "cell": return
        
        if self.cell_editor and self.cell_editor.winfo_exists():
            self.cell_editor.focus_set() 
            return 

        item_id = self.tree.identify_row(event.y)
        column_id = self.tree.identify_column(event.x)
        
        col_index = int(column_id.replace('#', '')) - 1 
        
        if col_index < 0 or col_index >= len(self.header):
            return

        current_values = list(self.tree.item(item_id, 'values'))
        current_value = current_values[col_index]

        bbox = self.tree.bbox(item_id, column_id)
        if bbox:
            x, y, width, height = bbox
            
            entry_var = tk.StringVar(value=current_value)
            self.cell_editor = ttk.Entry(self.tree, textvariable=entry_var)
            self.cell_editor.place(x=x, y=y, width=width, height=height)
            self.cell_editor.focus_set()

            self.cell_editor.bind("<Return>", lambda e, i=item_id, c=col_index, v=entry_var: self._save_edit(i, c, v.get()))
            self.cell_editor.bind("<FocusOut>", lambda e, i=item_id, c=col_index, v=entry_var: self._save_edit(i, c, v.get()))
            self.cell_editor.bind("<Tab>", lambda e: self._move_to_next_cell()) 

    def _save_edit_and_focus_tree(self, item_id, col_index, new_value):
        self._save_edit(item_id, col_index, new_value)
        # Force focus back to tree immediately
        self.tree.focus_force()
        self.tree.selection_set(item_id)
        self.tree.focus(item_id)
        return 'break'

    def _on_enter_key(self, event):
        selection = self.tree.selection()
        if selection:
            self._edit_cell(selection[0], 0)
        return 'break'

    def _on_tab_key(self, event):
        selection = self.tree.selection()
        if selection:
            self._move_to_next_cell()
        return 'break'

    def _move_to_next_cell(self):
        if self.cell_editor and self.cell_editor.winfo_exists():
            # Get current position from the editor's bindings
            current_item = None
            current_col = 0
            
            # Find current position by checking editor placement
            for item in self.tree.get_children():
                for col in range(len(self.header)):
                    column_id = f"#{col + 1}"
                    bbox = self.tree.bbox(item, column_id)
                    if bbox and self.cell_editor.winfo_x() == bbox[0] and self.cell_editor.winfo_y() == bbox[1]:
                        current_item = item
                        current_col = col
                        break
                if current_item:
                    break
            
            # Save current edit first
            self.cell_editor.event_generate('<FocusOut>')
            
            if current_item:
                # Move to next column
                if current_col + 1 < len(self.header):
                    # Next column in same row
                    self._edit_cell(current_item, current_col + 1)
                else:
                    # Wrap to first column of next row
                    items = self.tree.get_children()
                    current_index = items.index(current_item)
                    if current_index + 1 < len(items):
                        next_item = items[current_index + 1]
                        self._edit_cell(next_item, 0)
                    else:
                        # Wrap to first row, first column
                        if items:
                            self._edit_cell(items[0], 0)

    def _edit_cell(self, item_id, col_index):
        if col_index >= len(self.header):
            return
            
        current_values = list(self.tree.item(item_id, 'values'))
        current_value = current_values[col_index] if col_index < len(current_values) else ""
        
        column_id = f"#{col_index + 1}"
        bbox = self.tree.bbox(item_id, column_id)
        if bbox:
            x, y, width, height = bbox
            
            entry_var = tk.StringVar(value=current_value)
            self.cell_editor = ttk.Entry(self.tree, textvariable=entry_var)
            self.cell_editor.place(x=x, y=y, width=width, height=height)
            self.cell_editor.focus_set()
            self.cell_editor.select_range(0, tk.END)

            self.cell_editor.bind("<Return>", lambda e, i=item_id, c=col_index, v=entry_var: self._save_edit(i, c, v.get()))
            self.cell_editor.bind("<FocusOut>", lambda e, i=item_id, c=col_index, v=entry_var: self._save_edit(i, c, v.get()))
            self.cell_editor.bind("<Tab>", lambda e: self._move_to_next_cell())

    def _save_edit(self, item_id, col_index, new_value):
        if not self.cell_editor: return
            
        try:
            current_values_list = list(self.tree.item(item_id, 'values'))
            
            if 0 <= col_index < len(current_values_list):
                current_values_list[col_index] = new_value
                self.tree.item(item_id, values=current_values_list)

                # If the cell had a link and the ⇗ was removed, clear link in raw data
                row_index = self.tree.index(item_id)
                if row_index < len(self.rows) and col_index < len(self.rows[row_index]):
                    raw = self.rows[row_index][col_index]
                    if LINK_REGEX.match(str(raw).strip()) and not new_value.startswith("⇗ "):
                        self.rows[row_index][col_index] = new_value

            # Auto-add blank row if last row now has non-checkbox content
            all_items = self.tree.get_children()
            if all_items and item_id == all_items[-1]:
                has_content = any(
                    str(v).strip() for v in current_values_list
                    if not self._is_checkbox_value(v)
                )
                if has_content:
                    blank = self._make_blank_row()
                    display_blank = [self._get_checkbox_display(cell) for cell in blank]
                    tag = "evenrow" if len(all_items) % 2 == 0 else "oddrow"
                    self.tree.insert('', 'end', values=display_blank, tags=(tag,))
            
        finally:
            if self.cell_editor and self.cell_editor.winfo_exists():
                self.cell_editor.destroy()
            self.cell_editor = None
            # Always return focus to tree after editing
            self.tree.focus_force()
            self.tree.selection_set(item_id)
            self.tree.focus(item_id)

    def _show_row_menu(self, event, item_id, col_index=0):
        """Show context menu for row operations."""
        menu = tk.Menu(self, tearoff=0)

        # Check if cell has a link
        row_index = self.tree.index(item_id)
        if row_index < len(self.rows) and col_index < len(self.rows[row_index]):
            raw = self.rows[row_index][col_index]
            m = LINK_REGEX.match(str(raw).strip())
            if m and self.controller:
                path = m.group(1)
                display = m.group(2) if m.group(2) else path.split('/')[-1]
                menu.add_command(label=f"Open: {display}",
                               command=lambda p=path: self.controller._open_file_editor(p.split('/')))
                menu.add_separator()

        menu.add_command(label="Link to File", command=lambda: self._link_cell(item_id, col_index))
        menu.add_separator()
        menu.add_command(label="Delete Row", command=lambda: self._delete_row(item_id))
        
        popup_menu(menu, event.x_root, event.y_root)

    def _link_cell(self, item_id, col_index):
        """Set a cell value as a link to a VFS file."""
        if not self.controller:
            return
        picker = VFSFilePicker(self, self.controller.vfs, self.controller.root_name)
        if picker.result:
            path = picker.result
            current_values = list(self.tree.item(item_id, 'values'))
            # Use existing cell text as display, or filename
            raw_val = str(current_values[col_index])
            # Strip existing link markup if re-linking
            m = LINK_REGEX.match(raw_val.strip())
            if m:
                display = m.group(2) if m.group(2) else raw_val
            else:
                display = raw_val.strip() if raw_val.strip() else path.split('/')[-1]
            current_values[col_index] = f"⇗ {display}"
            self.tree.item(item_id, values=current_values)
            # Store raw link in rows data
            row_index = self.tree.index(item_id)
            if row_index < len(self.rows):
                while len(self.rows[row_index]) <= col_index:
                    self.rows[row_index].append("")
                self.rows[row_index][col_index] = f"[[{path}|{display}]]"

    def _set_cell_checkbox(self, item_id, col_index):
        """Convert a cell to a checkbox (default FALSE/☐)."""
        current_values = list(self.tree.item(item_id, 'values'))
        current_values[col_index] = "☐"
        self.tree.item(item_id, values=current_values)

    def _delete_row(self, item_id):
        """Delete the specified row."""
        if not messagebox.askyesno("Confirm Delete", "Delete selected row?"):
            return
            
        # Get row index and remove from data
        row_index = self.tree.index(item_id)
        
        if row_index < len(self.rows):
            del self.rows[row_index]
            full_data = [self.header] + self.rows
            updated_content = self._list_to_csv(full_data)
            self._load_data_and_ui(updated_content)

    def _show_column_menu(self, event, col_index):
        # Create context menu
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="Add Column", command=self._add_column)
        menu.add_separator()
        menu.add_command(label="Rename Column", command=lambda: self._rename_column(col_index))
        menu.add_command(label="Set as Checkbox Column", command=lambda: self._set_column_checkbox(col_index))
        menu.add_separator()
        menu.add_command(label="Delete Column", command=lambda: self._delete_column(col_index))
        
        # Show menu at mouse position
        popup_menu(menu, event.x_root, event.y_root)

    def _set_column_checkbox(self, col_index):
        """Convert all cells in a column to checkboxes."""
        for item_id in self.tree.get_children():
            current_values = list(self.tree.item(item_id, 'values'))
            if not self._is_checkbox_value(current_values[col_index]):
                current_values[col_index] = "☐"
            self.tree.item(item_id, values=current_values)
        self.tree.column(self.header[col_index], anchor="center")

    def _edit_header(self, col_index):
        old_name = self.header[col_index]

    def _rename_column(self, col_index):
        old_name = self.header[col_index]
        new_name = simpledialog.askstring("Rename Column", f"Enter new name for column '{old_name}':", parent=self, initialvalue=old_name)
        
        if new_name is None or new_name.strip() == old_name:
            return

        new_name_stripped = new_name.strip()
        base_name = new_name_stripped.split('.')[0].strip()

        if self.name_regex and not self.name_regex.match(base_name):
            messagebox.showerror("Error", "Header name must only contain letters, numbers, spaces, and hyphens.")
            return

        if new_name_stripped in self.header and new_name_stripped != old_name:
             messagebox.showerror("Error", f"Column '{new_name_stripped}' already exists.")
             return

        self.header[col_index] = new_name_stripped
        updated_content = self.get_content()
        
        if self.controller and self.controller.active_file_path:
            if self.controller._set_file_content(self.controller.active_file_path, updated_content):
                self._load_data_and_ui(updated_content)
            else:
                messagebox.showerror("Internal Error", "Failed to commit updated CSV structure to VFS.")
        else:
             messagebox.showerror("Internal Error", "Cannot rename column: Controller reference or active path is missing.")

    def _delete_column(self, col_index):
        if len(self.header) <= 1:
            messagebox.showerror("Error", "Cannot delete the last column.")
            return
            
        col_name = self.header[col_index]
        if not messagebox.askyesno("Confirm Delete", f"Delete column '{col_name}'?"):
            return
            
        # Remove column from header and all rows
        new_header = [h for i, h in enumerate(self.header) if i != col_index]
        new_rows = []
        for row in self.rows:
            new_row = [cell for i, cell in enumerate(row) if i != col_index]
            new_rows.append(new_row)
            
        full_data = [new_header] + new_rows
        updated_content = self._list_to_csv(full_data)
        
        if self.controller and self.controller.active_file_path:
            if self.controller._set_file_content(self.controller.active_file_path, updated_content):
                self._load_data_and_ui(updated_content)

    def _on_delete_key(self, event):
        selection = self.tree.selection()
        if not selection:
            return
            
        if not messagebox.askyesno("Confirm Delete", "Delete selected row?"):
            return
            
        # Get row index and remove from data
        item = selection[0]
        row_index = self.tree.index(item)
        
        if row_index < len(self.rows):
            del self.rows[row_index]
            full_data = [self.header] + self.rows
            updated_content = self._list_to_csv(full_data)
            self._load_data_and_ui(updated_content)


    def _get_checkbox_columns(self):
        """Returns set of column indices that are checkbox columns."""
        if not self.rows:
            return set()
        # A column is checkbox if all non-empty cells in it are checkbox values
        checkbox_cols = set()
        for col_idx in range(len(self.header)):
            cells = [row[col_idx] for row in self.rows if col_idx < len(row) and row[col_idx].strip()]
            if cells and all(self._is_checkbox_value(c) for c in cells):
                checkbox_cols.add(col_idx)
        return checkbox_cols

    def _make_blank_row(self):
        """Creates a blank row with checkboxes pre-filled for checkbox columns."""
        checkbox_cols = self._get_checkbox_columns()
        return ["☐" if i in checkbox_cols else "" for i in range(len(self.header))]

    def _ensure_blank_row(self):
        """Ensures there's always one blank row at the bottom (ignoring checkbox values)."""
        if not self.rows:
            self.rows.append(self._make_blank_row())
            return
        last_row = self.rows[-1]
        has_content = any(
            cell.strip() for cell in last_row
            if not self._is_checkbox_value(cell)
        )
        if has_content:
            self.rows.append(self._make_blank_row())

    def _add_row(self):
        new_row = [""] * len(self.header)
        # Add to data and refresh display
        current_content = self.get_content()
        updated_content = current_content + "\n" + ",".join(new_row)
        self._load_data_and_ui(updated_content)
        


    def _add_column(self):
        new_header_name = simpledialog.askstring("New Column", "Enter new column header name:", parent=self)
        if new_header_name:
            base_name = new_header_name.split('.')[0].strip()
            if self.name_regex and not self.name_regex.match(base_name):
                messagebox.showerror("Error", "Header name must only contain letters, numbers, spaces, and hyphens.")
                return
            
            current_header = self.header + [new_header_name]
            all_rows_data = []
            for item_id in self.tree.get_children():
                row_values = list(self.tree.item(item_id, 'values')) + [""]
                all_rows_data.append(row_values)
                
            full_data = [current_header] + all_rows_data
            updated_content = self._list_to_csv(full_data)
            
            # When adding a column, we immediately update the VFS *content* but not the disk.
            if self.controller and self.controller.active_file_path:
                if self.controller._set_file_content(self.controller.active_file_path, updated_content):
                    self._load_data_and_ui(updated_content)
                else:
                    messagebox.showerror("Internal Error", "Failed to commit updated CSV structure to VFS.")
            else:
                 messagebox.showerror("Internal Error", "Cannot add column: Controller reference or active path is missing.")

    def _list_to_csv(self, data_list):
        csv_output = []
        for row in data_list:
            quoted_row = []
            for cell in row:
                cell_str = str(cell)
                if ',' in cell_str or '\n' in cell_str or '"' in cell_str:
                    cell_str = cell_str.replace('"', '""')
                    quoted_row.append(f'"{cell_str}"')
                else:
                    quoted_row.append(cell_str)
            csv_output.append(",".join(quoted_row))
        return "\n".join(csv_output)


    def get_content(self):
        if not hasattr(self, 'tree') or not self.tree.winfo_exists():
             return ""

        all_rows_data = []
        for row_idx, item_id in enumerate(self.tree.get_children()):
            row = []
            for col_idx, v in enumerate(self.tree.item(item_id, 'values')):
                s = str(v)
                if s == "☑":
                    row.append("TRUE")
                elif s == "☐":
                    row.append("FALSE")
                elif s.startswith("⇗ ") and row_idx < len(self.rows) and col_idx < len(self.rows[row_idx]):
                    # Use raw link data from self.rows
                    row.append(self.rows[row_idx][col_idx])
                else:
                    row.append(s)
            all_rows_data.append(row)

        # Remove all blank rows (ignoring checkbox values)
        all_rows_data = [
            row for row in all_rows_data
            if any(cell.strip() for cell in row if not self._is_checkbox_value(cell))
        ]

        full_data = [self.header] + all_rows_data
        
        return self._list_to_csv(full_data)


if __name__ == '__main__':
    try:
        if '__file__' in locals():
            os.chdir(os.path.dirname(os.path.abspath(__file__)))
    except NameError:
        pass 
        
    app = WorldBuilderArchive()
    app.mainloop()
