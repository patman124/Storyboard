import tkinter as tk
from tkinter import messagebox
import json
import os
from datetime import datetime

# --- Configuration ---
DATA_FILE = 'timeline_data.json'

# --- Utility Functions ---

def load_data():
    """Loads timeline entries from the JSON file, ensuring UTF-8 encoding."""
    if os.path.exists(DATA_FILE):
        try:
            # Explicitly use UTF-8 encoding for reading the file
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                # Data is expected to be a flat list of entries
                return json.load(f)
        except json.JSONDecodeError:
            print(f"Warning: {DATA_FILE} is empty or malformed.")
            return []
    return []

def save_data(data):
    """Saves timeline entries to the JSON file, ensuring UTF-8 encoding."""
    # Explicitly use UTF-8 and ensure_ascii=False to save characters correctly
    # The saved data is a flat list
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

# --- Application Logic ---

class FlexibleTimelineApp:
    def __init__(self, master):
        self.master = master
        master.title("Flexible Nested Timeline UI")
        master.geometry("800x600")

        self.data = load_data()
        self.entry_widgets = {} 
        # State variable to control button visibility and functionality
        self.editing_enabled = tk.BooleanVar(master, value=False) 

        # 1. Input Frame (Top)
        self.input_frame = tk.Frame(master, padx=10, pady=10, relief=tk.RIDGE, bd=2)
        self.input_frame.pack(side=tk.TOP, fill=tk.X)

        # Timeframe Input (Flexible)
        tk.Label(self.input_frame, text="Timeframe:").grid(row=0, column=0, sticky='w', padx=5, pady=2)
        self.timeframe_entry = tk.Entry(self.input_frame, width=20)
        self.timeframe_entry.grid(row=0, column=1, sticky='w', padx=5, pady=2)
        
        # Parent Entry Selection (Dropdown for Nesting)
        tk.Label(self.input_frame, text="Parent Entry (for nesting):").grid(row=0, column=2, sticky='w', padx=5, pady=2)
        
        # --- Parent Selection Variables ---
        self.parent_id_selected = tk.StringVar(master, value="None") 
        self.parent_display_var = tk.StringVar(master, value="None (Top Level)") 
        
        self.parent_menu = tk.OptionMenu(self.input_frame, self.parent_display_var, "None (Top Level)")
        self.parent_menu.config(width=30)
        self.parent_menu.grid(row=0, column=3, sticky='ew', padx=5, pady=2)
        self.update_parent_menu() # Populate initial parents
        
        # Edit Toggle Button (Row 0, Column 4)
        self.edit_toggle_button = tk.Button(
            self.input_frame, 
            text="Edit Entries (OFF)", 
            command=self.toggle_editing, 
            bg="#ddffdd"
        )
        self.edit_toggle_button.grid(row=0, column=4, sticky='w', padx=5, pady=2)

        # Description Input
        tk.Label(self.input_frame, text="Description:").grid(row=1, column=0, sticky='w', padx=5, pady=2)
        self.text_entry = tk.Entry(self.input_frame, width=70)
        self.text_entry.grid(row=1, column=1, columnspan=3, sticky='ew', padx=5, pady=2)
        
        # Add Button
        self.add_button = tk.Button(self.input_frame, text="[+] Add Entry", command=self.add_entry, bg="#e0ffe0")
        self.add_button.grid(row=1, column=4, sticky='e', padx=5, pady=2)
        
        self.input_frame.grid_columnconfigure(3, weight=1) 

        # --- Separator ---
        tk.Frame(master, height=1, bg="gray").pack(fill='x', padx=10, pady=5)

        # 2. Display Frame (Bottom) - Scrollable
        self.canvas = tk.Canvas(master, borderwidth=0, background="#ffffff")
        self.timeline_scrollbar = tk.Scrollbar(master, orient="vertical", command=self.canvas.yview)
        self.timeline_frame = tk.Frame(self.canvas, background="#ffffff")

        self.timeline_scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True, padx=10, pady=5)
        
        self.canvas_window = self.canvas.create_window((4, 4), window=self.timeline_frame, anchor="nw", 
                                                       tags="self.timeline_frame")

        self.timeline_frame.bind("<Configure>", self.on_frame_configure)
        self.canvas.bind('<Configure>', self.on_canvas_configure)

        self.refresh_display()

    def on_frame_configure(self, event):
        """Reset the scroll region to encompass the inner frame's extent."""
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def on_canvas_configure(self, event):
        """Update the inner frame width to fit the canvas width."""
        canvas_width = event.width
        self.canvas.itemconfig(self.canvas_window, width=canvas_width)

    def set_parent_selection(self, display_name, entry_id):
        """Sets both the display text and the hidden ID for parent selection."""
        self.parent_display_var.set(display_name)
        # Store "None" if entry_id is None, otherwise store the actual ID
        self.parent_id_selected.set(entry_id or "None")

    def update_parent_menu(self):
        """Updates the dropdown menu with current available parent entries."""
        menu = self.parent_menu["menu"]
        menu.delete(0, "end")
        
        # Set command for the top-level option
        menu.add_command(label="None (Top Level)", 
                         command=lambda: self.set_parent_selection("None (Top Level)", None))
        
        # Helper function to recursively add entries to the menu
        def add_entries_to_menu(entries, level=0):
            for entry in entries:
                # Use the timeframe and description for the display name
                display_name = ("—" * level) + f" {entry['timeframe']}: {entry['text']}"
                entry_id = entry['id']
                
                # Set command for nested entries
                menu.add_command(label=display_name, 
                                 command=lambda dn=display_name, e_id=entry_id: self.set_parent_selection(dn, e_id))
                
                # Recurse using the 'children' key generated by build_tree
                if 'children' in entry and entry['children']:
                    add_entries_to_menu(entry['children'], level + 1)

        # We call build_tree on the flat data to get the hierarchical view for the menu display
        hierarchical_data = self.build_tree(self.data)
        add_entries_to_menu(hierarchical_data)

    def get_parent_id(self):
        """Retrieves the selected parent ID from the hidden variable."""
        selection = self.parent_id_selected.get()
        if selection == "None":
            return None
        return selection

    def find_entry(self, data, entry_id):
        """
        Finds an entry by ID in the flat list and returns the entry and the list it belongs to.
        Since the list is flat, the parent list is always data itself.
        """
        for entry in data:
            if entry.get('id') == entry_id:
                return entry, data 
        return None, None

    def add_entry(self):
        """Handles adding a new timeline entry, ensuring data is stored flat."""
        timeframe = self.timeframe_entry.get().strip()
        text = self.text_entry.get().strip()

        if not timeframe or not text:
            messagebox.showerror("Input Error", "Timeframe and Description are required.")
            return

        # Generate a unique ID (using timestamp for simplicity)
        entry_id = datetime.now().strftime('%Y%m%d%H%M%S%f') 
        parent_id = self.get_parent_id()

        new_entry = {
            'id': entry_id, 
            'timeframe': timeframe, 
            'text': text, 
            'parent_id': parent_id,
            # 'children' key is omitted from the stored data to maintain a flat structure
        }

        # Append ALL entries to the top-level flat list self.data
        self.data.append(new_entry)

        save_data(self.data) # Save the flat list to JSON
        
        self.timeframe_entry.delete(0, tk.END) # Clear inputs
        self.text_entry.delete(0, tk.END)
        
        # Parent selection is persistent
        
        self.refresh_display()
        self.update_parent_menu()
    
    def toggle_editing(self):
        """Toggles the editing mode and updates the button text and display."""
        
        # Toggle the boolean state
        is_enabled = not self.editing_enabled.get()
        self.editing_enabled.set(is_enabled)
        
        # Update the toggle button text and color
        if is_enabled:
            self.edit_toggle_button.config(text="Edit Entries (ON)", bg="#ffdddd")
        else:
            self.edit_toggle_button.config(text="Edit Entries (OFF)", bg="#ddffdd")
            
        # Refresh the display to hide/show the Move and Delete buttons
        self.refresh_display()


    def delete_entry(self, entry_id):
        """Deletes an entry and all its children by filtering the flat data list."""
        if not messagebox.askyesno("Confirm Delete", "Are you sure you want to delete this entry and all its nested children?"):
            return
            
        # First, build the hierarchical tree from the flat data to easily find all descendants
        hierarchical_data = self.build_tree(self.data)

        def find_node_and_collect_descendants(entries, target_id):
            """Searches the tree for target_id and returns the set of all IDs (including target) to remove."""
            for entry in entries:
                if entry['id'] == target_id:
                    # Found it, collect all descendants recursively
                    ids = {target_id}
                    def collect_ids(children):
                        for child in children:
                            ids.add(child['id'])
                            collect_ids(child.get('children', []))
                    collect_ids(entry.get('children', []))
                    return ids
                # Recurse into children
                if entry.get('children'):
                    found_ids = find_node_and_collect_descendants(entry['children'], target_id)
                    if found_ids:
                        return found_ids
            return set()

        ids_to_remove = find_node_and_collect_descendants(hierarchical_data, entry_id)
        
        if not ids_to_remove:
             messagebox.showerror("Error", "Could not find the entry to delete.")
             return

        # Filter the original flat data list, keeping only entries whose ID is NOT in the removal set
        self.data = [entry for entry in self.data if entry['id'] not in ids_to_remove]
        
        # If the entry being deleted was the currently selected parent, reset selection
        if self.parent_id_selected.get() == entry_id:
            self.parent_display_var.set("None (Top Level)") 
            self.parent_id_selected.set("None") 
            
        save_data(self.data)
        self.refresh_display()
        self.update_parent_menu()

    def move_entry(self, entry_id, direction):
        """
        Handles reordering of an entry relative to its siblings.
        Since only 'up' is supported, direction will always be 'up'.
        """
        if direction != 'up':
            return 

        # 1. Find the entry and its parent ID
        moving_entry, _ = self.find_entry(self.data, entry_id)
        if not moving_entry: return

        parent_id = moving_entry.get('parent_id')

        # 2. Get the list of flat indices for all entries (siblings) that share this parent ID
        sibling_indices = [
            i for i, entry in enumerate(self.data) 
            if entry.get('parent_id') == parent_id
        ]
        
        # 3. Find the current flat index (in self.data) of the moving entry
        current_flat_index = self.data.index(moving_entry)

        # 4. Find the position (rank) of the entry within the sibling group
        try:
            sibling_rank = sibling_indices.index(current_flat_index)
        except ValueError:
            return

        # 5. Determine the target rank (index in sibling_indices) for UP movement
        target_rank = sibling_rank - 1 

        if not (0 <= target_rank < len(sibling_indices)):
            # Cannot move further up
            return

        # 6. Get the flat index (in self.data) of the target sibling
        target_flat_index = sibling_indices[target_rank]
        
        # 7. Swap the entries in the main self.data list
        self.data[current_flat_index], self.data[target_flat_index] = \
            self.data[target_flat_index], self.data[current_flat_index]

        save_data(self.data)
        self.refresh_display()


    def build_tree(self, flat_list, parent_id=None):
        """Recursively converts the flat list into a nested tree structure for display, ensuring required keys exist."""
        tree = []
        for entry in flat_list:
            # Add resilience against corrupted data missing keys
            if 'id' not in entry or 'timeframe' not in entry or 'text' not in entry:
                print(f"Skipping corrupted entry: {entry}")
                continue
                
            if entry.get('parent_id') == parent_id:
                # This entry belongs at the current nesting level
                # Create a copy with the 'children' structure initialized for recursion
                current_entry = {
                    'id': entry['id'],
                    'timeframe': entry['timeframe'],
                    'text': entry['text'],
                    'parent_id': entry.get('parent_id'),
                    # Recursively build children using the ENTIRE flat list again
                    'children': self.build_tree(flat_list, entry['id'])
                }
                tree.append(current_entry)
        return tree


    def refresh_display(self):
        """Clears and redraws the timeline entries using the hierarchical structure."""
        # Clear all previous widgets
        for widget in self.timeline_frame.winfo_children():
            widget.destroy()
        
        # Load the flat data and restructure it for display
        self.data = load_data() 
        hierarchical_data = self.build_tree(self.data)
        
        self.row_counter = 0

        def display_entry(entry, level=0):
            """Recursively displays an entry and its children."""
            
            is_enabled = self.editing_enabled.get() 
            
            indent = "  " * level
            bg_color = "#f0f0ff" if level == 0 else ("#f7f7f7" if level % 2 == 1 else "#ffffff")
            
            # Entry Container Frame (to hold label and buttons)
            entry_frame = tk.Frame(self.timeline_frame, background=bg_color)
            entry_frame.grid(row=self.row_counter, column=0, sticky='ew', padx=2, pady=1)

            # Main Entry Label
            main_label = tk.Label(
                entry_frame, 
                text=f"{indent}➤ {entry['timeframe']}: {entry['text']}", 
                anchor='w', 
                justify=tk.LEFT,
                font=('Arial', 10, 'bold' if level == 0 else 'normal'),
                padx=5, 
                pady=5,
                background=bg_color
            )
            main_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

            entry_id = entry['id']
            
            # --- Conditional Button Creation and Display ---
            if is_enabled:
                
                # 1. Delete Button (Packed RIGHT - appears on the far right)
                delete_button = tk.Button(
                    entry_frame, 
                    text="[X]", 
                    command=lambda e_id=entry_id: self.delete_entry(e_id),
                    width=3,
                    bg="#ffcccc",
                    activebackground="#ff9999",
                )
                delete_button.pack(side=tk.RIGHT, padx=2)
                
                # 2. Move Up Button (Packed RIGHT - appears next to Delete)
                move_up_button = tk.Button(
                    entry_frame, 
                    text="[↑]", 
                    command=lambda e_id=entry_id: self.move_entry(e_id, 'up'),
                    width=3,
                    bg="#ddddff",
                    activebackground="#ccccff",
                )
                move_up_button.pack(side=tk.RIGHT, padx=2)
            # --- End Conditional Block ---


            self.row_counter += 1

            # Recursively display children
            if 'children' in entry:
                for child in entry['children']:
                    display_entry(child, level + 1)


        # Start the recursive display from the top level
        for top_entry in hierarchical_data:
            display_entry(top_entry)

        # Update the layout and scroll region
        self.timeline_frame.grid_columnconfigure(0, weight=1)
        self.timeline_frame.update_idletasks()
        self.canvas.config(scrollregion=self.canvas.bbox("all"))


# --- Main Execution ---

if __name__ == "__main__":
    root = tk.Tk()
    # 🎯 UTF-8 FIX 1: Set the main window encoding for character display
    root.option_add('*encoding', 'utf-8') 
    
    app = FlexibleTimelineApp(root)
    root.mainloop()