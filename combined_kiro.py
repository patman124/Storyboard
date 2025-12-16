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
    
    # Regex to enforce safe and clean file/folder names (letters, numbers, spaces, and hyphens)
    NAME_REGEX = re.compile(r"^[a-zA-Z0-9\s-]+$")
    
    # NEW: Map friendly display names to file extensions
    FILE_TYPE_MAP = {
        "Text Document": ".txt",
        "Database/Table (.csv)": ".csv",
        "Chronological Timeline": ".timeline"
    }

    def __init__(self):
        super().__init__()
        self.title("World Builder Archive") 
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
            self.title(f"World Builder Archive - {self.root_name} (Saved)") 
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
            
            # Refresh UI
            self._populate_vfs_tree()
            self._clear_right_panel()
            self.title(f"World Builder Archive - {self.root_name}")
            
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
        self.title(f"World Builder Archive - {self.root_name} (Saved)")

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
                messagebox.showerror("Deletion Restricted", 
                                     f"Folder '{name_to_delete}' must be empty before deletion.")
                return False
            
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

        del parent_node["children"][name_to_delete]
        
        self._populate_vfs_tree()
        self._restore_tree_state(self._get_open_paths(), parent_path)

        return True
        
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
        
        self.main_pane = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        self.main_pane.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # --- Left Panel ---
        left_frame = ttk.Frame(self.main_pane, padding="5 5 5 5")
        self.main_pane.add(left_frame, weight=10)  # Reduced from 15 to 10 
        
        self.path_var = tk.StringVar(value=self._get_path_string(self.current_path))
        ttk.Label(left_frame, textvariable=self.path_var, font=('Helvetica', 10, 'bold'), anchor='w').pack(fill=tk.X, pady=(0, 5))
        
        tree_frame = ttk.Frame(left_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        
        self.vfs_tree = ttk.Treeview(tree_frame, columns=('path_string'), show='tree')
        self.vfs_tree.column('#0', width=200, anchor='w')
        self.vfs_tree.heading('#0', text='Name')
        self.vfs_tree.column('path_string', width=0, stretch=tk.NO) 
        self.vfs_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.vfs_tree.bind('<<TreeviewSelect>>', self._on_tree_select)
        self.vfs_tree.bind('<Double-1>', self._on_tree_double_click)
        
        tree_scroll = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.vfs_tree.yview)
        self.vfs_tree.configure(yscrollcommand=tree_scroll.set)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        # File Management Buttons (Load/Save/New)
        file_management_frame = ttk.Frame(left_frame)
        file_management_frame.pack(fill=tk.X, pady=(5, 5))
        
        # --- MODIFIED: Save World is packed RIGHT; Load and Save As are packed LEFT ---
        
        # 1. Pack Save World to the far RIGHT (anchors it to the right side)
        ttk.Button(file_management_frame, text="Save World", command=self.save_world).pack(side=tk.RIGHT, padx=2)
        
        # 2. Load World remains on the LEFT
        ttk.Button(file_management_frame, text="Load World", command=self.load_world).pack(side=tk.LEFT, padx=2)
        
        # 3. Save World As is now packed LEFT (next to Load World)
        ttk.Button(file_management_frame, text="Save World As...", command=self.save_world_as).pack(side=tk.LEFT, padx=2)

        # --- END MODIFIED BLOCK ---

        # VFS Modification Buttons (Folder/File/Delete)
        button_frame = ttk.Frame(left_frame)
        button_frame.pack(fill=tk.X, pady=(0, 0))
        
        ttk.Button(button_frame, text="Create Folder", command=self._open_create_folder_dialog).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="Create File", command=self._open_create_file_dialog).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="Delete Selected", command=self._delete_selected_node).pack(side=tk.LEFT, padx=2)

        # --- Right Panel ---
        self.right_frame = ttk.Frame(self.main_pane, padding="5 5 5 5")
        self.main_pane.add(self.right_frame, weight=70) 
        
        self.editor_label = ttk.Label(self.right_frame, text="Select a file from the left panel to open it for editing.", anchor='center')
        self.editor_label.pack(pady=20)
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
                children_items = sorted(node_data["children"].items(), key=lambda item: (item[1].get("type") != "dir", item[0].lower()))
                for child_name, child_data in children_items:
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
                children_items = sorted(root_content["children"].items(), key=lambda item: (item[1].get("type") != "dir", item[0].lower()))
                for child_name, child_data in children_items:
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

    def _clear_right_panel(self):
        """Removes the active editor widget and replaces it with the default prompt message."""
        for widget in self.right_frame.winfo_children():
            widget.destroy()
            
        self.active_editor = None
        self.editor_label = ttk.Label(self.right_frame, text="Select a file from the left panel to open it for editing.", anchor='center')
        self.editor_label.pack(pady=20)

    def _open_file_editor(self, path_list):
        """Initializes the correct editor widget (Text, CSV, or Timeline) for the new file."""
        
        file_name = path_list[-1]
        self._save_editor_content_to_vfs() # Save content of the *old* active editor before opening new one
        content = self._get_file_content(path_list)
        self._clear_right_panel()

        editor_frame = ttk.Frame(self.right_frame)
        editor_frame.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(editor_frame, text=f"Editing: {file_name}", font=('Helvetica', 12, 'bold')).pack(fill=tk.X, pady=(0, 5))
        
        if file_name.lower().endswith('.csv'):
            self.active_editor = CSVGrid(editor_frame, content, name_regex=self.NAME_REGEX, controller=self)
        elif file_name.lower().endswith('.timeline'):
            # The TimelineEditor is now instantiated here
            self.active_editor = TimelineEditor(editor_frame, content, controller=self)
        else: 
            self.active_editor = TextEditor(editor_frame, content, controller=self) 

        self.active_editor.pack(fill=tk.BOTH, expand=True)
        self.active_file_path = path_list


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


# --- Editor Widgets (Text, CSV, Timeline) ---

class TextEditor(ttk.Frame):
    """A simple, scrollable multi-line text editor widget."""
    def __init__(self, master, initial_content="", controller=None):
        super().__init__(master)
        self.controller = controller 
        
        self.text_widget = tk.Text(self, wrap=tk.WORD, font=('Courier New', 10))
        self.text_widget.insert(tk.END, initial_content)
        self.text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=2, pady=2)
            
        scrollbar = ttk.Scrollbar(self, command=self.text_widget.yview)
        self.text_widget.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
    def get_content(self):
        """Retrieves and returns the full content of the text widget."""
        return self.text_widget.get("1.0", tk.END).strip()

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
                
                ttk.Label(units_frame, text=f"{unit.replace('_', ' ').title()}:").grid(row=i, column=1, sticky="w", padx=5)
                
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
        
        # Add BC/AD configuration below the time units (only when ages are disabled)
        bc_ad_frame = ttk.LabelFrame(self.config_frame, text="BC/AD Dating", padding="5")
        bc_ad_frame.pack(fill=tk.X, pady=(10, 0))
        
        # Enable checkbox
        self.bc_ad_var = tk.BooleanVar(value=self.config_data.get("bc_ad_enabled", False))
        self.bc_ad_checkbox = ttk.Checkbutton(bc_ad_frame, text="Enable BC/AD Dating", 
                                             variable=self.bc_ad_var, command=self._toggle_bc_ad)
        self.bc_ad_checkbox.grid(row=0, column=0, columnspan=4, sticky="w", pady=5)
        
        # BC Label and Years
        ttk.Label(bc_ad_frame, text="BC Label:").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        self.bc_var = tk.StringVar(value=self.config_data.get("bc_label", "BC"))
        self.bc_var.trace_add('write', self._update_bc_ad_labels)
        self.bc_entry = ttk.Entry(bc_ad_frame, width=10, textvariable=self.bc_var)
        self.bc_entry.grid(row=1, column=1, padx=5, pady=5)
        
        ttk.Label(bc_ad_frame, text="BC Years:").grid(row=1, column=2, padx=5, pady=5, sticky="w")
        self.bc_years_var = tk.IntVar(value=self.config_data.get("bc_years", 100))
        self.bc_years_spinbox = ttk.Spinbox(bc_ad_frame, from_=1, to=999999, width=8, textvariable=self.bc_years_var)
        self.bc_years_spinbox.grid(row=1, column=3, padx=5, pady=5)
        
        # AD Label and Years
        ttk.Label(bc_ad_frame, text="AD Label:").grid(row=2, column=0, sticky="w", padx=5, pady=5)
        self.ad_var = tk.StringVar(value=self.config_data.get("ad_label", "AD"))
        self.ad_var.trace_add('write', self._update_bc_ad_labels)
        self.ad_entry = ttk.Entry(bc_ad_frame, width=10, textvariable=self.ad_var)
        self.ad_entry.grid(row=2, column=1, padx=5, pady=5)
        
        ttk.Label(bc_ad_frame, text="AD Years:").grid(row=2, column=2, padx=5, pady=5, sticky="w")
        self.ad_years_var = tk.IntVar(value=self.config_data.get("ad_years", 100))
        self.ad_years_spinbox = ttk.Spinbox(bc_ad_frame, from_=1, to=999999, width=8, textvariable=self.ad_years_var)
        self.ad_years_spinbox.grid(row=2, column=3, padx=5, pady=5)

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
        
        legend_text = "Hotkeys: Enter=Edit Event | Shift+Enter=New Event | Ctrl+Enter=New Sub-Event | Del=Delete Event"
        ttk.Label(legend_frame, text=legend_text, font=('Helvetica', 8), foreground='gray').pack()
        
        # Event management buttons
        btn_frame = ttk.Frame(events_frame)
        btn_frame.pack(fill=tk.X, pady=(0,5))
        
        ttk.Button(btn_frame, text="Add Event", command=self._add_event).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Add Sub-Event", command=self._add_sub_event).pack(side=tk.LEFT, padx=2)
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
        self.events_tree.bind('<Control-Return>', self._hotkey_add_sub_event)
        self.events_tree.bind('<Delete>', self._hotkey_delete_event)
        
        # Explicitly bind arrow keys to ensure navigation works
        self.events_tree.bind('<Up>', self._navigate_up)
        self.events_tree.bind('<Down>', self._navigate_down)
        self.events_tree.bind('<Left>', self._navigate_left)
        self.events_tree.bind('<Right>', self._navigate_right)
        
        self.events_tree.focus_set()  # Allow tree to receive key events

        # Initialize BC/AD state after all widgets are created
        self._toggle_bc_ad()
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
        if name_btn and unit != "years":  # Don't disable Name Years button
            name_btn.config(state=state)
        
        # Special handling: disable years and BC/AD when ages is enabled
        if unit == "ages":
            years_visible_var = getattr(self, "years_visible_var", None)
            years_count_spinbox = getattr(self, "years_count_spinbox", None)
            years_checkbox = getattr(self, "years_checkbox", None)
            
            # BC/AD controls
            bc_ad_checkbox = getattr(self, "bc_ad_checkbox", None)
            bc_entry = getattr(self, "bc_entry", None)
            ad_entry = getattr(self, "ad_entry", None)
            bc_years_spinbox = getattr(self, "bc_years_spinbox", None)
            ad_years_spinbox = getattr(self, "ad_years_spinbox", None)
            
            if years_visible_var and years_count_spinbox and years_checkbox:
                if visible:  # Ages is enabled, disable years and BC/AD
                    years_visible_var.set(False)
                    years_count_spinbox.config(state="disabled")
                    years_checkbox.config(state="disabled")
                    
                    # Disable BC/AD controls
                    if bc_ad_checkbox:
                        self.bc_ad_var.set(False)
                        bc_ad_checkbox.config(state="disabled")
                    if bc_entry:
                        bc_entry.config(state="disabled")
                    if ad_entry:
                        ad_entry.config(state="disabled")
                    if bc_years_spinbox:
                        bc_years_spinbox.config(state="disabled")
                    if ad_years_spinbox:
                        ad_years_spinbox.config(state="disabled")
                        
                else:  # Ages is disabled, allow years and BC/AD to be enabled
                    years_count_spinbox.config(state="normal")
                    years_checkbox.config(state="normal")
                    
                    # Enable BC/AD controls
                    if bc_ad_checkbox:
                        bc_ad_checkbox.config(state="normal")
                    self._toggle_bc_ad()  # Update BC/AD entry states based on checkbox
            
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
        
        if hasattr(self, 'year_scale') and (ages_enabled or years_enabled):
            # Find year label - show when Ages OR Years checkbox is checked
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
        # Calculate total possible days in the timeline
        ages_count = self.config_data["time_units"]["ages"]["count"]
        months_per_year = self.config_data["time_units"]["months"]["count"]
        days_per_month = self.config_data["time_units"]["days_of_month"]["count"]
        
        total_days = 0
        for age in range(1, ages_count + 1):
            years_in_age = self.config_data["time_units"]["ages"].get("years_per_age", {}).get(str(age), 100)
            total_days += years_in_age * months_per_year * days_per_month
        
        self.master_timeline_scale.config(to=max(total_days - 1, 1))

    def _get_cumulative_days(self):
        """Get current cumulative days from timeline position."""
        day_of_month = int(self.current_day_of_month.get())
        month = int(self.current_month.get())
        year = int(self.current_year.get())
        age = int(self.current_age.get())
        days_per_month = self.config_data["time_units"]["days_of_month"]["count"]
        months_per_year = self.config_data["time_units"]["months"]["count"]
        
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
        
        remaining_days = cumulative_days
        
        # Find the age
        age = 1
        ages_count = self.config_data["time_units"]["ages"]["count"]
        for current_age in range(1, ages_count + 1):
            years_in_age = self.config_data["time_units"]["ages"].get("years_per_age", {}).get(str(current_age), 100)
            days_in_age = years_in_age * months_per_year * days_per_month
            
            if remaining_days < days_in_age:
                age = current_age
                break
            remaining_days -= days_in_age
        
        # Find year within age
        days_per_year = months_per_year * days_per_month
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
        
        self._update_day_of_month()

    def _scroll_scale(self, event, var):
        """Handle mouse wheel scrolling on scale widgets."""
        current = var.get()
        new_value = current + 1 if event.delta > 0 else current - 1
        
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
        
        if enabled:
            self.bc_entry.config(state="normal")
            self.ad_entry.config(state="normal")
            self.bc_years_spinbox.config(state="normal")
            self.ad_years_spinbox.config(state="normal")
        else:
            self.bc_entry.config(state="disabled")
            self.ad_entry.config(state="disabled")
            self.bc_years_spinbox.config(state="disabled")
            self.ad_years_spinbox.config(state="disabled")
            # Reset negative years to positive when BC/AD is disabled
            if self.current_year.get() <= 0:
                self.current_year.set(1)
        
        # Update labels when changed
        if enabled:
            self.config_data["bc_label"] = self.bc_var.get()
            self.config_data["ad_label"] = self.ad_var.get()
            self.config_data["bc_years"] = self.bc_years_var.get()
            self.config_data["ad_years"] = self.ad_years_var.get()
        
        # Update year range
        self._update_ranges()
        self._update_display()
        self._populate_events()  # Refresh events display with new BC/AD formatting

    def _configure_ages(self):
        """Open dialog to configure ages with BC/AD settings."""
        dialog = AgeConfigDialog(self, self.config_data["time_units"]["ages"], self.config_data)
        if dialog.result:
            self.config_data["time_units"]["ages"]["names"] = dialog.result["names"]
            self.config_data["time_units"]["ages"]["years_per_age"] = dialog.result["years_per_age"]
            self.config_data.update(dialog.result["bc_ad_config"])
            self.bc_ad_var.set(self.config_data.get("bc_ad_enabled", False))
            self.bc_var.set(self.config_data.get("bc_label", "BC"))
            self.ad_var.set(self.config_data.get("ad_label", "AD"))
            self._toggle_bc_ad()
            self._update_ranges()
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
            
        # Show years if Years is enabled OR Ages is enabled (since ages need years)
        if visible_units.get("years", True) or visible_units.get("ages", True):
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
        """Add a new timeline event."""
        current_time = {
            "age": int(self.current_age.get()),
            "year": int(self.current_year.get()),
            "month": int(self.current_month.get()),
            "day_of_week": int(self.current_day_of_week.get()),
            "day_of_month": int(self.current_day_of_month.get())
        }
        
        dialog = TimelineEventDialog(self, current_time)
        if dialog.result:
            self.config_data["events"].append(dialog.result)
            self._populate_events()

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
        
        # Check if this is a sub-event
        if "_" in item_id:
            # Sub-event format: "main_index_sub_index"
            main_index, sub_index = map(int, item_id.split("_"))
            if (main_index < len(self.config_data["events"]) and 
                sub_index < len(self.config_data["events"][main_index].get("sub_events", []))):
                
                sub_event = self.config_data["events"][main_index]["sub_events"][sub_index]
                
                # Handle backward compatibility
                if "time" in sub_event and "start_time" not in sub_event:
                    sub_event["start_time"] = sub_event["time"]
                    del sub_event["time"]
                
                current_time = sub_event.get("start_time", {
                    "age": int(self.current_age.get()),
                    "year": int(self.current_year.get()),
                    "month": int(self.current_month.get()),
                    "day_of_week": int(self.current_day_of_week.get()),
                    "day_of_month": int(self.current_day_of_month.get())
                })
                
                dialog = TimelineEventDialog(self, current_time, sub_event)
                if dialog.result:
                    self.config_data["events"][main_index]["sub_events"][sub_index] = dialog.result
                    self._populate_events()
        else:
            # Main event
            event_index = int(item_id) if item_id.isdigit() else None
            if event_index is not None and event_index < len(self.config_data["events"]):
                event = self.config_data["events"][event_index]
                
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
                    self.config_data["events"][event_index] = dialog.result
                    self._populate_events()
        
    def _delete_event(self):
        """Delete selected event or sub-event.""" 
        selection = self.events_tree.selection()
        if not selection:
            messagebox.showinfo("Selection Required", "Please select an event to delete.")
            return
        
        item_id = selection[0]
        
        # Check if this is a sub-event
        if "_" in item_id:
            # Sub-event format: "main_index_sub_index"
            main_index, sub_index = map(int, item_id.split("_"))
            if (main_index < len(self.config_data["events"]) and 
                sub_index < len(self.config_data["events"][main_index].get("sub_events", []))):
                
                sub_event_name = self.config_data["events"][main_index]["sub_events"][sub_index]["name"]
                if messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete the sub-event '{sub_event_name}'?"):
                    del self.config_data["events"][main_index]["sub_events"][sub_index]
                    self._populate_events()
        else:
            # Main event
            event_index = int(item_id) if item_id.isdigit() else None
            if event_index is not None and event_index < len(self.config_data["events"]):
                event_name = self.config_data["events"][event_index]["name"]
                sub_events_count = len(self.config_data["events"][event_index].get("sub_events", []))
                
                if sub_events_count > 0:
                    message = f"Are you sure you want to delete the event '{event_name}' and its {sub_events_count} sub-event(s)?"
                else:
                    message = f"Are you sure you want to delete the event '{event_name}'?"
                
                if messagebox.askyesno("Confirm Delete", message):
                    del self.config_data["events"][event_index]
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
            
            # Format start and end times separately
            start_time_str = self._format_event_time_display(start_time)
            end_time_str = self._format_event_time_display(end_time) if end_time else ""
                
            # Insert main event
            main_item = self.events_tree.insert('', 'end', text=event['name'], iid=str(original_index),
                                               values=(start_time_str, end_time_str, event.get('description', '')[:50]))
            
            # Insert sub-events
            sub_events = event.get('sub_events', [])
            for sub_index, sub_event in enumerate(sub_events):
                sub_start_time = sub_event.get('start_time', {})
                sub_end_time = sub_event.get('end_time')
                
                sub_start_time_str = self._format_event_time_display(sub_start_time)
                sub_end_time_str = self._format_event_time_display(sub_end_time) if sub_end_time else ""
                
                self.events_tree.insert(main_item, 'end', text=sub_event['name'], 
                                       iid=f"{original_index}_{sub_index}",
                                       values=(sub_start_time_str, sub_end_time_str, sub_event.get('description', '')[:50]))
            
            # Expand main events that have sub-events
            if sub_events:
                self.events_tree.item(main_item, open=True)

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
        
        # Configure highlight tag
        self.events_tree.tag_configure('highlighted', background='lightblue')
        
        # Clear all existing highlights
        for item in self.events_tree.get_children():
            self.events_tree.item(item, tags=())
            # Also clear sub-events
            for sub_item in self.events_tree.get_children(item):
                self.events_tree.item(sub_item, tags=())
        
        # Check each event for matches
        for i, event in enumerate(self.config_data["events"]):
            start_time = event.get('start_time', {})
            end_time = event.get('end_time')
            
            # Check if current time matches start time or is within range
            matches_start = self._times_match(current_time, start_time)
            in_range = False
            
            if end_time:
                in_range = self._time_in_range(current_time, start_time, end_time)
            
            if matches_start or in_range:
                item_id = str(i)
                if item_id in [child for child in self.events_tree.get_children()]:
                    self.events_tree.item(item_id, tags=('highlighted',))
            
            # Check sub-events
            sub_events = event.get('sub_events', [])
            for sub_index, sub_event in enumerate(sub_events):
                sub_start_time = sub_event.get('start_time', {})
                sub_end_time = sub_event.get('end_time')
                
                sub_matches_start = self._times_match(current_time, sub_start_time)
                sub_in_range = False
                
                if sub_end_time:
                    sub_in_range = self._time_in_range(current_time, sub_start_time, sub_end_time)
                
                if sub_matches_start or sub_in_range:
                    sub_item_id = f"{i}_{sub_index}"
                    for child in self.events_tree.get_children(str(i)):
                        if child.endswith(f"_{sub_index}"):
                            self.events_tree.item(child, tags=('highlighted',))
                            break

    def _times_match(self, time1, time2):
        """Check if two time dictionaries match."""
        visible_units = self.config_data.get("visible_units", {})
        
        if visible_units.get("ages", True) and time1.get("age") != time2.get("age"):
            return False
        # Check years if Years is enabled OR Ages is enabled (since ages need years)
        if (visible_units.get("years", True) or visible_units.get("ages", True)) and time1.get("year") != time2.get("year"):
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
            
        # Show years if Years is enabled OR Ages is enabled (since ages need years)
        if visible_units.get("years", True) or visible_units.get("ages", True):
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
        self.name_var = tk.StringVar(value=self.existing_event["name"] if self.existing_event else "")
        ttk.Entry(self, textvariable=self.name_var, width=40).grid(row=0, column=1, columnspan=2, padx=10, pady=5)
        
        # Description
        ttk.Label(self, text="Description:").grid(row=1, column=0, sticky="nw", padx=10, pady=5)
        self.desc_text = tk.Text(self, width=40, height=3)
        if self.existing_event:
            self.desc_text.insert("1.0", self.existing_event.get("description", ""))
        self.desc_text.grid(row=1, column=1, columnspan=2, padx=10, pady=5)
        
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
            
        if visible_units.get("years", True) or visible_units.get("ages", True):
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
        if (visible_units.get("years", True) or visible_units.get("ages", True)) and hasattr(self, f"{prefix}_year_var"):
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

    def _ok(self):
        name = self.name_var.get().strip()
        if not name:
            messagebox.showerror("Error", "Event name is required.")
            return
            
        result_data = {
            "name": name,
            "description": self.desc_text.get("1.0", tk.END).strip(),
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
        
        self._setup_grid_ui()


    def _parse_csv(self, content):
        if not content.strip():
            return []
        
        lines = content.strip().split('\n')
        parsed_data = []
        for line in lines:
            cells = [cell.strip() for cell in line.split(',')]
            parsed_data.append(cells)
            
        if parsed_data:
            header_len = len(parsed_data[0])
            for i in range(len(parsed_data)):
                while len(parsed_data[i]) < header_len:
                    parsed_data[i].append("") 
                if len(parsed_data[i]) > header_len:
                    parsed_data[i] = parsed_data[i][:header_len]
        
        return parsed_data

    def _setup_grid_ui(self):
        button_frame = ttk.Frame(self.grid_container)
        button_frame.pack(fill=tk.X, pady=(0, 5))
        ttk.Button(button_frame, text="Add Row", command=self._add_row).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="Add Column", command=self._add_column).pack(side=tk.LEFT, padx=2)
        
        tree_frame = ttk.Frame(self.grid_container)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        
        self.tree = ttk.Treeview(tree_frame, columns=self.header, show='headings')
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        for col in self.header:
            self.tree.column(col, anchor="w", width=100)
            self.tree.heading(col, text=col)
            
        for i, row in enumerate(self.rows):
            row_to_insert = row[:len(self.header)] if len(row) > len(self.header) else row + [""] * (len(self.header) - len(row))
            self.tree.insert('', 'end', values=row_to_insert, tags=(str(i),)) 

        vscroll = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=vscroll.set)
        vscroll.pack(side=tk.RIGHT, fill=tk.Y)

        hscroll = ttk.Scrollbar(self.grid_container, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(xscrollcommand=hscroll.set)
        hscroll.pack(side=tk.BOTTOM, fill=tk.X)

        self.tree.bind('<Double-1>', self._on_double_click)

    def _on_double_click(self, event):
        region = self.tree.identify("region", event.x, event.y)
        
        if region == "heading":
            column_id = self.tree.identify_column(event.x)
            col_index = int(column_id.replace('#', '')) - 1
            if 0 <= col_index < len(self.header):
                self._edit_header(col_index)
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

    def _save_edit(self, item_id, col_index, new_value):
        if not self.cell_editor: return
            
        try:
            current_values_list = list(self.tree.item(item_id, 'values'))
            
            if 0 <= col_index < len(current_values_list):
                current_values_list[col_index] = new_value
                self.tree.item(item_id, values=current_values_list)
            
        finally:
            if self.cell_editor and self.cell_editor.winfo_exists():
                self.cell_editor.destroy()
            self.cell_editor = None

    def _edit_header(self, col_index):
        old_name = self.header[col_index]
        new_name = simpledialog.askstring("Rename Column", f"Enter new name for column '{old_name}':", parent=self)
        
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
        
        # When changing a header, we immediately update the VFS *content* but not the disk.
        if self.controller and self.controller.active_file_path:
            if self.controller._set_file_content(self.controller.active_file_path, updated_content):
                self._load_data_and_ui(updated_content)
            else:
                messagebox.showerror("Internal Error", "Failed to commit updated CSV structure to VFS.")
        else:
             messagebox.showerror("Internal Error", "Cannot rename column: Controller reference or active path is missing.")


    def _add_row(self):
        new_row = [""] * len(self.header)
        self.tree.insert('', 'end', values=new_row)
        


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
        for item_id in self.tree.get_children():
            all_rows_data.append([str(v) for v in self.tree.item(item_id, 'values')])

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
