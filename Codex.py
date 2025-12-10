import tkinter as tk
from tkinter import ttk, filedialog, simpledialog, messagebox
import json
import re
import os
from PIL import Image, ImageTk, ImageDraw
import io

class WorldBuilderArchive(tk.Tk):
    # --- Configuration Constants ---
    VFS_STORAGE_FILE = "codex_archive.json"
    ROOT_NAME = "My World"
    
    # Regex to enforce safe and clean file/folder names (letters, numbers, spaces, and hyphens)
    NAME_REGEX = re.compile(r"^[a-zA-Z0-9\s-]+$")

    def __init__(self):
        super().__init__()
        self.title("World Builder Archive (Real-Time Auto-Saving)")
        self.geometry("1200x800")
        
        # --- Application State Management ---
        # The core Virtual File System (VFS) dictionary, loaded from disk
        self.vfs = self._load_vfs() 
        
        # List of strings representing the path currently selected in the Treeview (e.g., ["WorldRoot", "Maps", "Area1"])
        self.current_path = [self.ROOT_NAME]
        
        # Path list of the file currently opened and displayed in the right panel editor
        self.active_file_path = None
        
        # --- UI Initialization ---
        self._create_icons()
        self._setup_layout()
        self._populate_vfs_tree()
        
        # Ensure VFS content is saved to disk when the user closes the application window
        self.protocol("WM_DELETE_WINDOW", self._on_closing)

    # --- Core VFS Persistence & Lifecycle ---
    
    def _on_closing(self):
        """
        Executes final save operations before closing the main window.
        1. Saves content from the active editor (if any).
        2. Writes the entire VFS structure to the JSON file.
        3. Destroys the Tkinter root window.
        """
        self._save_editor_content_to_vfs()
        self._write_vfs_to_disk()
        self.destroy()

    def _load_vfs(self):
        """
        Attempts to load the VFS structure from the JSON file.
        Returns a new default VFS dictionary if the file is missing or contains invalid JSON.
        """
        default_vfs_structure = {"type": "dir", "children": {}} 
        vfs_data = default_vfs_structure

        try:
            if os.path.exists(self.VFS_STORAGE_FILE):
                with open(self.VFS_STORAGE_FILE, 'r') as f:
                    vfs_data = json.load(f) 
            else:
                raise FileNotFoundError
                
        except (FileNotFoundError, json.JSONDecodeError):
            # If load fails, initialize with the default empty VFS structure
            pass 
        
        # The top level of self.vfs is always keyed by the ROOT_NAME for encapsulation
        return {self.ROOT_NAME: vfs_data}


    def _write_vfs_to_disk(self):
        """
        Serializes and writes the current VFS state (excluding the top-level root key) 
        to the predefined JSON file on disk, formatted with indentation.
        """
        try:
            # Only save the contents of the root node
            vfs_to_save = self.vfs.get(self.ROOT_NAME, {})
            with open(self.VFS_STORAGE_FILE, 'w') as f:
                json.dump(vfs_to_save, f, indent=4)
        except Exception as e:
            messagebox.showerror("Save Error", f"Failed to save VFS to disk: {e}")

    # --- Guarded VFS Access Methods ---
    
    def _get_file_node_reference(self, path):
        """
        Traverses the VFS structure using the given path list.
        Returns the direct dictionary reference of the target file or folder node.
        Returns None if any part of the path is invalid.
        """
        node = self.vfs.get(self.ROOT_NAME) 
        
        # If path is only the root, return the root node reference
        if len(path) == 1 and path[0] == self.ROOT_NAME:
            return node 
            
        # Traverse starting from the children of the root
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
        Updates the content field of a file node and triggers an automatic disk save.
        This is the only method that modifies file content in the VFS structure.
        """
        node = self._get_file_node_reference(path_list)
        
        if node and node.get("type") == "file":
            node["content"] = str(content)
            self._write_vfs_to_disk()
            return True
        return False
        
    # --- VFS Structure Modification Methods ---
    
    def _get_target_folder_path(self):
        """
        Determines the correct parent path for creating a new node.
        If the current selection is a file, the parent directory is returned.
        If the current selection is a folder, that folder's path is returned.
        """
        path_list = self.current_path
        node = self._get_file_node_reference(path_list)

        if node and node.get("type") == "file":
            # If a file is selected, create the new node in its parent directory
            return path_list[:-1]

        # If a directory is selected, create the new node inside it
        return path_list

    def _create_node(self, parent_path, name, node_type, content=None):
        """
        Creates a new file or folder node under the specified parent path,
        validates the name, and auto-saves the structural change to disk.
        """
        parent_node = self._get_file_node_reference(parent_path)
        if not parent_node or parent_node.get("type") != "dir":
            messagebox.showerror("Error", f"Cannot create node: Invalid parent directory.")
            return False 
            
        if name in parent_node.get("children", {}):
            messagebox.showerror("Error", f"A file or folder named '{name}' already exists.")
            return False
        
        # Validate the base name using the predefined regex
        base_name = name.split('.')[0]
        if not self.NAME_REGEX.match(base_name):
            messagebox.showerror("Error", "Base name must only contain letters, numbers, spaces, and hyphens.")
            return False

        # Create the new node dictionary based on type
        if node_type == "dir":
            new_node = {"type": "dir", "children": {}}
        elif node_type == "file":
            new_node = {"type": "file", "content": str(content) if content is not None else ""}
        else:
            return False 
        
        # Insert the new node into the parent's children map
        if "children" not in parent_node:
            parent_node["children"] = {}
            
        parent_node["children"][name] = new_node
        self._write_vfs_to_disk() # Auto-save structural change
        return True

    def _delete_node(self, path):
        """
        Handles the deletion of a file or folder node, enforcing specific deletion rules.
        - Root cannot be deleted.
        - Folders must be empty.
        - Files require explicit 'CONFIRM' text input.
        """
        
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
            # Rule: Folder must be empty
            if node_to_delete.get("children"):
                messagebox.showerror("Deletion Restricted", 
                                     f"Folder '{name_to_delete}' must be empty before deletion.")
                return False
            
            # Ask for confirmation for empty folder deletion
            if not messagebox.askyesno("Confirm Deletion", 
                                       f"Are you sure you want to delete the empty folder '{name_to_delete}'?"):
                return False

        elif node_type == "file":
            # Rule: File deletion requires typing 'CONFIRM'
            confirmation = simpledialog.askstring("Confirm File Deletion", 
                                                  f"To permanently delete the file '{name_to_delete}', please type 'CONFIRM' below:",
                                                  parent=self)
            
            if confirmation != 'CONFIRM':
                messagebox.showinfo("Deletion Canceled", "Deletion aborted. Confirmation phrase was not entered correctly.")
                return False
        
        # --- DELETION EXECUTION ---
        
        # If the deleted file was open in the editor, clear the right panel state
        if self.active_file_path and self._get_path_string(self.active_file_path) == self._get_path_string(path):
            self.active_file_path = None
            self._clear_right_panel()

        # Save the current expansion state of the tree before modification
        open_paths = self._get_open_paths()
        
        # Execute the deletion from the parent node's children dictionary
        del parent_node["children"][name_to_delete]
        
        # Rebuild the Treeview and restore expansion state, selecting the parent folder
        self._populate_vfs_tree()
        self._restore_tree_state(open_paths, parent_path)

        self._write_vfs_to_disk() # Auto-save structural change
        return True
        
    def _get_path_string(self, path):
        """Converts a VFS path list (e.g., ['A', 'B']) to a string (e.g., 'A/B')."""
        return "/".join(path)

    # --- Treeview State Management ---

    def _get_open_paths(self):
        """
        Recursively collects the path strings of all nodes currently expanded 
        (open=True) in the Treeview. Used for state preservation during redraws.
        """
        open_paths = set()
        
        def traverse(parent_id):
            for item_id in self.vfs_tree.get_children(parent_id):
                # Check for expansion state
                if self.vfs_tree.item(item_id, 'open'):
                    # Retrieve the full path string stored in the 'values' column
                    path_string = self.vfs_tree.item(item_id, 'values')[0]
                    open_paths.add(path_string)
                    traverse(item_id)
        
        # Start traversal from the top-level items
        traverse('') 
        return open_paths

    def _restore_tree_state(self, open_paths, path_to_select=None):
        """
        Restores the expansion state of the Treeview nodes based on the saved `open_paths`.
        Optionally selects and reveals the node at `path_to_select`.
        """
        item_to_select = None
        
        # Pass 1: Restore expansion state and find the item to select
        def traverse_and_restore(parent_id):
            nonlocal item_to_select
            for item_id in self.vfs_tree.get_children(parent_id):
                item_values = self.vfs_tree.item(item_id, 'values')
                if not item_values: continue
                
                path_string = item_values[0]
                
                # Identify the item ID matching the path to be selected
                if path_to_select and path_string == self._get_path_string(path_to_select):
                    item_to_select = item_id
                
                # Restore expansion state if the path was previously open
                if path_string in open_paths:
                    self.vfs_tree.item(item_id, open=True)
                
                traverse_and_restore(item_id)
                
        traverse_and_restore('')

        # Pass 2: Select and reveal the new item to ensure it's visible
        if item_to_select:
            # Remove any previous selections
            self.vfs_tree.selection_remove(self.vfs_tree.selection())
            
            # Select and scroll to the new item
            self.vfs_tree.selection_set(item_to_select)
            self.vfs_tree.see(item_to_select)
            
            # Update the application's internal path state
            path_string = self.vfs_tree.item(item_to_select, 'values')[0]
            self.current_path = path_string.split('/')
            self.path_var.set(path_string)

    # --- UI Component Setup ---
        
    def _create_icons(self):
        """Generates simple, graphical folder and file icons using PIL for a consistent look."""
        size = (16, 16)
        icon_color = "#34568B" 
        
        # Folder Icon drawing
        folder_img = Image.new('RGBA', size, (0, 0, 0, 0))
        d = ImageDraw.Draw(folder_img)
        d.rectangle([2, 5, 14, 14], fill=icon_color, outline=icon_color) 
        d.polygon([(2, 5), (4, 2), (8, 2), (10, 5)], fill=icon_color)
        self.folder_icon = ImageTk.PhotoImage(folder_img)
        
        # File Icon drawing (a sheet of paper with lines)
        file_img = Image.new('RGBA', size, (0, 0, 0, 0))
        d = ImageDraw.Draw(file_img)
        d.polygon([(2, 2), (13, 2), (13, 14), (2, 14)], fill="white", outline=icon_color)
        d.line([(2, 2), (13, 2), (13, 14), (2, 14), (2, 2)], fill=icon_color, width=1)
        d.line([(5, 5), (10, 5)], fill=icon_color)
        d.line([(5, 8), (10, 8)], fill=icon_color)
        d.line([(5, 11), (10, 11)], fill=icon_color)
        self.file_icon = ImageTk.PhotoImage(file_img)

    def _setup_layout(self):
        """Configures the main window layout using a PanedWindow for adjustable resizing."""
        style = ttk.Style(self)
        style.theme_use("clam") 
        
        # Main container allowing horizontal resizing between the two panels
        self.main_pane = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        self.main_pane.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # --- Left Panel: VFS Management (Treeview and Control Buttons) ---
        left_frame = ttk.Frame(self.main_pane, padding="5 5 5 5")
        self.main_pane.add(left_frame, weight=30) 
        
        # Display of the current path selection
        self.path_var = tk.StringVar(value=self._get_path_string(self.current_path))
        ttk.Label(left_frame, textvariable=self.path_var, font=('Helvetica', 10, 'bold'), anchor='w').pack(fill=tk.X, pady=(0, 5))
        
        # Treeview setup with scrollbars
        tree_frame = ttk.Frame(left_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        
        # Treeview holds VFS structure; 'path_string' column stores the full path for lookup, but is hidden
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
        
        # Action buttons for creation and deletion
        button_frame = ttk.Frame(left_frame)
        button_frame.pack(fill=tk.X, pady=(5, 0))
        
        ttk.Button(button_frame, text="Create Folder", command=self._open_create_folder_dialog).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="Create File", command=self._open_create_file_dialog).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="Delete Selected", command=self._delete_selected_node).pack(side=tk.LEFT, padx=2)

        # --- Right Panel: Editor (Dynamically loaded Text or CSV editor) ---
        self.right_frame = ttk.Frame(self.main_pane, padding="5 5 5 5")
        self.main_pane.add(self.right_frame, weight=70) 
        
        # Initial placeholder label for the editor panel
        self.editor_label = ttk.Label(self.right_frame, text="Select a file from the left panel to open it for editing.", anchor='center')
        self.editor_label.pack(fill=tk.BOTH, expand=True)
        self.active_editor = None

    def _populate_vfs_tree(self):
        """
        Rebuilds the entire Treeview display from the VFS dictionary.
        Note: This function does not handle state restoration; it only draws the structure.
        """
        # Clear all existing items
        for item in self.vfs_tree.get_children():
            self.vfs_tree.delete(item)

        def insert_node(parent_id, node_name, node_data, path_list):
            """Recursive helper to build the Treeview structure."""
            node_type = node_data.get("type", "dir")
            icon = self.folder_icon if node_type == "dir" else self.file_icon

            # Insert the node into the Treeview
            item_id = self.vfs_tree.insert(parent_id, 'end', 
                                           text=node_name, 
                                           image=icon,
                                           tags=("node",))
            
            # Store the full path string in a hidden column for easy lookup/state tracking
            self.vfs_tree.item(item_id, values=(self._get_path_string(path_list),))

            if node_type == "dir" and "children" in node_data:
                # Sort children: directories first, then files, both alphabetically
                children_items = sorted(node_data["children"].items(), key=lambda item: (item[1].get("type") != "dir", item[0].lower()))
                for child_name, child_data in children_items:
                    new_path = path_list + [child_name]
                    insert_node(item_id, child_name, child_data, new_path)

        root_content = self.vfs.get(self.ROOT_NAME)
        if root_content:
            # Insert the root node
            root_id = self.vfs_tree.insert('', 'end', 
                                           text=self.ROOT_NAME, 
                                           image=self.folder_icon,
                                           tags=("node",))
            self.vfs_tree.item(root_id, values=(self._get_path_string([self.ROOT_NAME]),))
            
            if "children" in root_content:
                # Insert all top-level children
                children_items = sorted(root_content["children"].items(), key=lambda item: (item[1].get("type") != "dir", item[0].lower()))
                for child_name, child_data in children_items:
                    new_path = [self.ROOT_NAME, child_name]
                    insert_node(root_id, child_name, child_data, new_path)

            # Ensure the root node is initially expanded
            self.vfs_tree.item(root_id, open=True) 
        
        # Update the path display variable
        self.path_var.set(self._get_path_string(self.current_path))


    def _on_tree_select(self, event):
        """Event handler for single-click selection in the Treeview."""
        selected_item = self.vfs_tree.selection()
        if not selected_item: return
            
        item_id = selected_item[0]
        item_values = self.vfs_tree.item(item_id, 'values')
        if item_values:
            # Update the application's internal state to reflect the selection
            path_string = item_values[0]
            self.current_path = path_string.split('/')
            self.path_var.set(path_string)


    def _on_tree_double_click(self, event):
        """
        Event handler for double-click. 
        Opens files in the editor or expands/collapses directories.
        """
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
            # Toggle folder expansion state
            self.current_path = path_list
            self.path_var.set(path_string)
            is_open = self.vfs_tree.item(item_id, 'open')
            self.vfs_tree.item(item_id, open=not is_open)
        elif node.get("type") == "file":
            # Open the file in the right-hand editor panel
            self._open_file_editor(path_list)


    # --- VFS Action Dialogs ---

    def _open_create_folder_dialog(self):
        """Prompts for a new folder name and attempts creation, preserving tree state."""
        
        # Determine the parent path for the new folder
        target_path = self._get_target_folder_path()
        
        # 1. Save current Treeview expansion state
        open_paths = self._get_open_paths()
        
        new_name = simpledialog.askstring("New Folder", f"Enter new folder name in {target_path[-1]}:", parent=self)
        if new_name:
            if self._create_node(target_path, new_name, "dir"):
                new_path = target_path + [new_name]
                # 2. Redraw and restore state, selecting the newly created folder
                self._populate_vfs_tree()
                self._restore_tree_state(open_paths, new_path)


    def _open_create_file_dialog(self):
        """Opens a custom dialog for selecting file name and type, preserving tree state."""
        # Ensure any active editor content is saved before opening the dialog
        self._save_editor_content_to_vfs() 
        
        # Determine the parent path for the new file
        target_path = self._get_target_folder_path()
        
        # Define allowed file types for the custom dialog
        allowed_types = [".txt", ".csv"]
        dialog = NewFileCreationDialog(self, target_path[-1], allowed_types)
        
        if dialog.result and dialog.result['base_name']:
            base_name = dialog.result['base_name'].strip()
            extension = dialog.result['extension']
            final_name = base_name + extension
            
            # Re-validate the base name before creation
            if not self.NAME_REGEX.match(base_name):
                 messagebox.showerror("Error", "Base name must only contain letters, numbers, spaces, and hyphens.")
                 return

            # 1. Save current Treeview expansion state
            open_paths = self._get_open_paths()

            if self._create_node(target_path, final_name, "file"): 
                new_path = target_path + [final_name]
                # 2. Redraw and restore state, selecting the newly created file
                self._populate_vfs_tree()
                self._restore_tree_state(open_paths, new_path)


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
        # Destroy all children of the right frame
        for widget in self.right_frame.winfo_children():
            widget.destroy()
            
        self.active_editor = None
        # Restore the initial guidance label
        self.editor_label = ttk.Label(self.right_frame, text="Select a file from the left panel to open it for editing.", anchor='center')
        self.editor_label.pack(fill=tk.BOTH, expand=True)

    def _open_file_editor(self, path_list):
        """
        Loads file content, saves the previous editor's state, destroys the old editor, 
        and initializes the correct editor widget (Text or CSV) for the new file.
        """
        
        file_name = path_list[-1]
        
        # 1. Proactively save content of the previously active editor
        self._save_editor_content_to_vfs() 
        
        # 2. Retrieve content for the new file
        content = self._get_file_content(path_list)

        # 3. Clear the panel (destroys the previous editor widget)
        self._clear_right_panel()

        # Frame to hold the new editor UI
        editor_frame = ttk.Frame(self.right_frame)
        editor_frame.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(editor_frame, text=f"Editing: {file_name}", font=('Helvetica', 12, 'bold')).pack(fill=tk.X, pady=(0, 5))
        
        # 4. Instantiate the correct editor type based on file extension
        if file_name.lower().endswith('.csv'):
            # CSV Grid editor (tabular data)
            self.active_editor = CSVGrid(editor_frame, content, name_regex=self.NAME_REGEX, controller=self)
        else: 
            # Default Text editor for .txt and unknown file types
            self.active_editor = TextEditor(editor_frame, content, controller=self) 

        self.active_editor.pack(fill=tk.BOTH, expand=True)
        
        # 5. Update the application state to track the new active file
        self.active_file_path = path_list


    def _save_editor_content_to_vfs(self):
        """
        Retrieves content from the currently active editor and commits it to the VFS.
        Called on key release, focus loss, and file switch.
        """
        if not self.active_editor or not self.active_file_path:
            return

        # Check if the active editor widget still exists in the GUI
        if not hasattr(self.active_editor, 'winfo_exists') or not self.active_editor.winfo_exists():
            return

        new_content = self.active_editor.get_content()
        
        # The VFS setter handles writing the change to disk immediately
        self._set_file_content(self.active_file_path, new_content)


# --- Custom Dialog for File Creation ---

class NewFileCreationDialog(tk.Toplevel):
    """
    Modal dialog for users to input the base file name and select an allowed extension.
    """
    def __init__(self, parent, current_folder_name, allowed_file_types):
        super().__init__(parent)
        # Configure as a modal dialog
        self.transient(parent)
        self.grab_set() 
        self.title("Create New File")
        self.parent = parent
        self.result = None 
        self.allowed_file_types = allowed_file_types 

        self.geometry("350x200")
        self.columnconfigure(0, weight=0)
        self.columnconfigure(1, weight=1)

        self._create_widgets(current_folder_name)
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        # Block interaction with the parent window until this dialog is closed
        self.wait_window(self)

    def _create_widgets(self, folder_name):
        """Sets up the input fields and buttons for the dialog."""
        ttk.Label(self, text=f"Folder:").grid(row=0, column=0, sticky="w", padx=10, pady=5)
        ttk.Label(self, text=folder_name, font=('Helvetica', 10, 'bold')).grid(row=0, column=1, sticky="w", padx=10, pady=5)
        
        ttk.Label(self, text=f"File Name (Base):").grid(row=1, column=0, sticky="w", padx=10, pady=5)
        self.name_entry = ttk.Entry(self)
        self.name_entry.grid(row=1, column=1, sticky="ew", padx=10, pady=5)
        
        ttk.Label(self, text="File Type:").grid(row=2, column=0, sticky="w", padx=10, pady=5)
        
        # Set up the dropdown menu with only allowed types
        default_type = self.allowed_file_types[0] if self.allowed_file_types else ".txt"
        self.file_type_var = tk.StringVar(value=default_type)
        
        if self.allowed_file_types:
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
        """Processes input, validates, and sets the result dictionary."""
        base_name = self.name_entry.get().strip()
        extension = self.file_type_var.get()

        if not base_name:
            messagebox.showerror("Error", "Please enter a file name.", parent=self)
            return

        self.result = {
            'base_name': base_name,
            'extension': extension
        }
        self.destroy()

    def cancel(self):
        """Sets result to None and closes the dialog."""
        self.result = None
        self.destroy()


# --- Editor Widgets ---

class TextEditor(ttk.Frame):
    """
    A simple, scrollable multi-line text editor widget. 
    It binds to key release events to trigger immediate auto-saving.
    """
    def __init__(self, master, initial_content="", controller=None):
        super().__init__(master)
        self.controller = controller 
        
        self.text_widget = tk.Text(self, wrap=tk.WORD, font=('Courier New', 10))
        self.text_widget.insert(tk.END, initial_content)
        self.text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=2, pady=2)
        
        # Bind the key release event to trigger the main application's save function
        if self.controller:
            self.text_widget.bind("<KeyRelease>", self._on_key_release) 
            
        scrollbar = ttk.Scrollbar(self, command=self.text_widget.yview)
        self.text_widget.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
    def _on_key_release(self, event):
        """Invokes the controller's auto-save method after user input."""
        # Avoid saving on non-content keys (like shift, control, navigation)
        if event.keysym in ('Shift_L', 'Shift_R', 'Control_L', 'Control_R', 'Alt_L', 'Alt_R', 'Prior', 'Next', 'Home', 'End'):
            return
            
        if self.controller:
             self.controller._save_editor_content_to_vfs()

    def get_content(self):
        """Retrieves and returns the full content of the text widget."""
        return self.text_widget.get("1.0", tk.END).strip()

class CSVGrid(ttk.Frame):
    """
    A tabular data editor for CSV files, utilizing a Treeview for display and 
    in-place editing for interaction.
    """
    def __init__(self, master, initial_content="", name_regex=None, controller=None):
        super().__init__(master)
        self.name_regex = name_regex 
        self.controller = controller 
        self.cell_editor = None # Tracks the temporary entry widget for cell editing
        
        self.grid_container = ttk.Frame(self)
        self.grid_container.pack(fill=tk.BOTH, expand=True)

        self._load_data_and_ui(initial_content)


    def _load_data_and_ui(self, content):
        """
        The main loading routine: parses CSV content, updates internal data structures, 
        and rebuilds the Treeview widget.
        """
        # Clear existing UI elements in the container
        for widget in self.grid_container.winfo_children():
            widget.destroy()
            
        self.data = self._parse_csv(content) 
        
        # Ensure minimal structure if content is empty
        if not self.data or not self.data[0]:
            self.data = [["Col 1", "Col 2"], ["", ""]]
        
        self.header = self.data[0]
        self.rows = self.data[1:]
        
        self._setup_grid_ui()


    def _parse_csv(self, content):
        """
        Performs basic CSV parsing by splitting lines and cells by comma. 
        It attempts to normalize row lengths to match the header length.
        """
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
                # Pad shorter rows
                while len(parsed_data[i]) < header_len:
                    parsed_data[i].append("") 
                # Trim longer rows
                if len(parsed_data[i]) > header_len:
                    parsed_data[i] = parsed_data[i][:header_len]
        
        return parsed_data

    def _setup_grid_ui(self):
        """Creates the Treeview widget, configures columns based on headers, and populates rows."""
        
        # Control buttons for structural changes
        button_frame = ttk.Frame(self.grid_container)
        button_frame.pack(fill=tk.X, pady=(0, 5))
        ttk.Button(button_frame, text="Add Row", command=self._add_row).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="Add Column", command=self._add_column).pack(side=tk.LEFT, padx=2)
        
        tree_frame = ttk.Frame(self.grid_container)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        
        # Treeview setup
        self.tree = ttk.Treeview(tree_frame, columns=self.header, show='headings')
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Configure columns and headings
        for col in self.header:
            self.tree.column(col, anchor="w", width=100)
            self.tree.heading(col, text=col)
            
        # Insert data rows
        for i, row in enumerate(self.rows):
            # Ensure the inserted row has the correct number of cells
            row_to_insert = row[:len(self.header)] if len(row) > len(self.header) else row + [""] * (len(self.header) - len(row))
            self.tree.insert('', 'end', values=row_to_insert, tags=(str(i),)) 

        # Scrollbar setup
        vscroll = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=vscroll.set)
        vscroll.pack(side=tk.RIGHT, fill=tk.Y)

        hscroll = ttk.Scrollbar(self.grid_container, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(xscrollcommand=hscroll.set)
        hscroll.pack(side=tk.BOTTOM, fill=tk.X)

        # Bind event for in-place editing
        self.tree.bind('<Double-1>', self._on_double_click)

    # --- Grid Editing Methods ---

    def _on_double_click(self, event):
        """
        Handles double-click events to initiate in-place editing for either a cell or a header.
        """
        region = self.tree.identify("region", event.x, event.y)
        
        if region == "heading":
            # If header is clicked, calculate column index and initiate header rename
            column_id = self.tree.identify_column(event.x)
            col_index = int(column_id.replace('#', '')) - 1
            if 0 <= col_index < len(self.header):
                self._edit_header(col_index)
            return
        
        if region != "cell": return
        
        # If another editor is already open, focus on it and prevent opening a new one
        if self.cell_editor and self.cell_editor.winfo_exists():
            self.cell_editor.focus_set() 
            return 

        item_id = self.tree.identify_row(event.y)
        column_id = self.tree.identify_column(event.x)
        
        col_index = int(column_id.replace('#', '')) - 1 
        
        if col_index < 0 or col_index >= len(self.header):
            return

        # Retrieve current value and bounding box for placement
        current_values = list(self.tree.item(item_id, 'values'))
        current_value = current_values[col_index]

        bbox = self.tree.bbox(item_id, column_id)
        if bbox:
            x, y, width, height = bbox
            
            entry_var = tk.StringVar(value=current_value)
            self.cell_editor = ttk.Entry(self.tree, textvariable=entry_var)
            self.cell_editor.place(x=x, y=y, width=width, height=height)
            self.cell_editor.focus_set()

            # Bind events to save the edited content
            self.cell_editor.bind("<Return>", lambda e, i=item_id, c=col_index, v=entry_var: self._save_edit(i, c, v.get()))
            self.cell_editor.bind("<FocusOut>", lambda e, i=item_id, c=col_index, v=entry_var: self._save_edit(i, c, v.get())) 

    def _save_edit(self, item_id, col_index, new_value):
        """
        Commits the edited cell value to the Treeview, triggers the VFS save 
        via the controller, and destroys the temporary editor widget.
        """
        if not self.cell_editor: return
            
        try:
            current_values_list = list(self.tree.item(item_id, 'values'))
            
            if 0 <= col_index < len(current_values_list):
                current_values_list[col_index] = new_value
                # Update the Treeview item's internal values
                self.tree.item(item_id, values=current_values_list)
            
            # The cell data has changed, so trigger an auto-save
            if self.controller:
                self.controller._save_editor_content_to_vfs()

        finally:
            if self.cell_editor and self.cell_editor.winfo_exists():
                self.cell_editor.destroy()
            self.cell_editor = None

    def _edit_header(self, col_index):
        """
        Prompts user for a new column name, validates it, updates the internal header 
        state, and forces a full reload of the grid to update the Treeview structure.
        """
        old_name = self.header[col_index]
        
        new_name = simpledialog.askstring("Rename Column", f"Enter new name for column '{old_name}':", parent=self)
        
        if new_name is None or new_name.strip() == old_name:
            return

        new_name_stripped = new_name.strip()
        base_name = new_name_stripped.split('.')[0].strip()

        # Input Validation against NAME_REGEX
        if self.name_regex and not self.name_regex.match(base_name):
            messagebox.showerror("Error", "Header name must only contain letters, numbers, spaces, and hyphens.")
            return

        if new_name_stripped in self.header and new_name_stripped != old_name:
             messagebox.showerror("Error", f"Column '{new_name_stripped}' already exists.")
             return

        # 1. Update internal state (header)
        self.header[col_index] = new_name_stripped
        
        # 2. Get the new CSV content string reflecting the header change
        updated_content = self.get_content()
        
        if self.controller and self.controller.active_file_path:
            # 3. Commit the new CSV content to VFS (triggers disk write)
            if self.controller._set_file_content(self.controller.active_file_path, updated_content):
                
                # 4. Reload the entire grid UI from the updated content string
                self._load_data_and_ui(updated_content)
                
            else:
                messagebox.showerror("Internal Error", "Failed to commit updated CSV structure to VFS.")
        else:
             messagebox.showerror("Internal Error", "Cannot rename column: Controller reference or active path is missing.")


    def _add_row(self):
        """Adds a new row of empty cells to the end of the grid and auto-saves."""
        new_row = [""] * len(self.header)
        self.tree.insert('', 'end', values=new_row)
        
        # Structural change requires immediate VFS update
        if self.controller:
             self.controller._save_editor_content_to_vfs()


    def _add_column(self):
        """
        Adds a new column, initializes its cells to empty strings, and forces a 
        full reload of the grid after saving the new structure to VFS.
        """
        new_header_name = simpledialog.askstring("New Column", "Enter new column header name:", parent=self)
        if new_header_name:
            base_name = new_header_name.split('.')[0].strip()
            # Validate new header name
            if self.name_regex and not self.name_regex.match(base_name):
                messagebox.showerror("Error", "Header name must only contain letters, numbers, spaces, and hyphens.")
                return
            
            # 1. Collect all data from the current Treeview state, adding an empty cell to each row
            current_header = self.header + [new_header_name]
            all_rows_data = []
            for item_id in self.tree.get_children():
                row_values = list(self.tree.item(item_id, 'values')) + [""]
                all_rows_data.append(row_values)
                
            full_data = [current_header] + all_rows_data
            updated_content = self._list_to_csv(full_data)
            
            if self.controller and self.controller.active_file_path:
                # 2. Commit the new CSV structure to VFS and disk
                if self.controller._set_file_content(self.controller.active_file_path, updated_content):
                    
                    # 3. Reload the grid locally to display the new column
                    self._load_data_and_ui(updated_content)
                else:
                    messagebox.showerror("Internal Error", "Failed to commit updated CSV structure to VFS.")
            else:
                 messagebox.showerror("Internal Error", "Cannot add column: Controller reference or active path is missing.")

    def _list_to_csv(self, data_list):
        """
        Converts a list of lists (including header) back into a standard CSV string,
        handling basic quoting for cells that contain commas or newlines.
        """
        csv_output = []
        for row in data_list:
            quoted_row = []
            for cell in row:
                cell_str = str(cell)
                # Check if quoting is necessary
                if ',' in cell_str or '\n' in cell_str or '"' in cell_str:
                    # Escape internal quotes by doubling them, then wrap the whole cell in quotes
                    cell_str = cell_str.replace('"', '""')
                    quoted_row.append(f'"{cell_str}"')
                else:
                    quoted_row.append(cell_str)
            csv_output.append(",".join(quoted_row))
        return "\n".join(csv_output)


    def get_content(self):
        """
        Retrieves the complete, current state of the grid (header + rows) and returns 
        it as a CSV formatted string.
        """
        
        if not hasattr(self, 'tree') or not self.tree.winfo_exists():
             return ""

        # Extract all row data from the Treeview
        all_rows_data = []
        for item_id in self.tree.get_children():
            # Convert Treeview values tuple to list of strings
            all_rows_data.append([str(v) for v in self.tree.item(item_id, 'values')])

        # Combine header and rows
        full_data = [self.header] + all_rows_data
        
        return self._list_to_csv(full_data)


if __name__ == '__main__':
    
    # Ensures the script runs with the current directory as the working directory 
    # for file persistence (where world_vfs_archive.json is saved)
    try:
        if '__file__' in locals():
            os.chdir(os.path.dirname(os.path.abspath(__file__)))
    except NameError:
        pass 
        
    app = WorldBuilderArchive()
    app.mainloop()