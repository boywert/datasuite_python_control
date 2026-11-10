import sys
import subprocess
import os
import webbrowser  

# --- Dependency Check ---
# This block checks for 'paramiko'. If it's not found, it tries to install it.
try:
    import paramiko
    import tkinter as tk
    import configparser
except ImportError:
    print("Required modules not found. Attempting to install...")
    try:
        # Use sys.executable to ensure we're using the pip for the current python
        subprocess.check_call([sys.executable, "-m", "pip", "install", "paramiko", "tkinter", "configparser"])
        print("Successfully installed 'paramiko'.")
    except Exception as e:
        print(f"ERROR: Failed to install 'paramiko'.")
        print(f"Please install it manually using: pip install paramiko")
        print(f"Details: {e}")
        sys.exit(1) # Exit the script
# --- End of Dependency Check ---

# All other imports now proceed. We can safely import paramiko here.
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
import paramiko # Import it again, now that we know it's present
import threading
import time
import socket
import configparser

# --- Config File Definition ---
CONFIG_FILE = 'ssh_forwarder.ini'

# --- Global variables to manage the SSH client and forwarding thread ---
ssh_client = None
jump_client = None
forwarding_threads = []
stop_event = threading.Event()

class ForwardServer(paramiko.ServerInterface):
    """
    A basic implementation of a Paramiko server interface for local port forwarding.
    """
    def check_channel_request(self, kind, chanid):
        if kind == 'session':
            return paramiko.OPEN_SUCCEEDED
        return paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED

    def check_auth_password(self, username, password):
        # This server doesn't authenticate clients, so we accept all.
        return paramiko.AUTH_SUCCESSFUL

def forward_tunnel(local_port, remote_host, remote_port, transport, stop_event):
    """
    This function runs in a separate thread and handles the forwarding for a single rule.
    It listens on a local port and forwards connections to the remote host/port.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
            server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server_socket.bind(('', local_port))
            server_socket.listen(5)
            print(f"Listening for connections on localhost:{local_port}...")

            while not stop_event.is_set():
                try:
                    server_socket.settimeout(1.0)
                    client_socket, client_addr = server_socket.accept()
                    print(f"Accepted connection from {client_addr} for port {local_port}")

                    dest_addr = (remote_host, remote_port)
                    channel = transport.open_channel("direct-tcpip", dest_addr, client_addr)

                    if channel is None:
                        print(f"Failed to open channel for port {local_port}.")
                        client_socket.close()
                        continue

                    print(f"Opened channel to {remote_host}:{remote_port}")

                    threading.Thread(target=handle_client_to_remote, args=(client_socket, channel, stop_event), daemon=True).start()
                    threading.Thread(target=handle_remote_to_client, args=(client_socket, channel, stop_event), daemon=True).start()

                except socket.timeout:
                    continue
                except Exception as e:
                    if not stop_event.is_set():
                        print(f"Error in forwarding loop for port {local_port}: {e}")
                    break
    except Exception as e:
        # This error is likely to happen before the loop starts.
        # --- THREAD-SAFE GUI UPDATE ---
        def show_error_safe(msg):
             messagebox.showerror("Error", msg)

        if "address already in use" in str(e):
            app.after(0, lambda: show_error_safe(f"Port {local_port} is already in use. Please choose another port."))
        else:
            app.after(0, lambda: show_error_safe(f"Failed to start listener on port {local_port}: {e}"))
    finally:
        print(f"Stopped listening on localhost:{local_port}")


def handle_client_to_remote(client_socket, channel, stop_event):
    """
    Reads data from the local client and sends it to the remote host via the SSH channel.
    """
    try:
        while channel.active and not stop_event.is_set():
            data = client_socket.recv(1024)
            if not data:
                break
            channel.send(data)
    except socket.error:
        pass
    finally:
        channel.close()
        client_socket.close()


def handle_remote_to_client(client_socket, channel, stop_event):
    """
    Reads data from the remote host via the SSH channel and sends it to the local client.
    """
    try:
        while channel.active and not stop_event.is_set():
            data = channel.recv(1024)
            if not data:
                break
            client_socket.send(data)
    except socket.error:
        pass
    finally:
        channel.close()
        client_socket.close()


def start_forwarding():
    """
    Gathers connection details, establishes the SSH connection,
    and starts the forwarding threads for all defined rules.
    """
    global ssh_client, jump_client, forwarding_threads, stop_event

    if forwarding_threads: # Check list
        messagebox.showinfo("Info", "Forwarding is already active.")
        return

    # Reset the stop event for the new session
    stop_event.clear()
    forwarding_threads.clear() # Clear the list

    ssh_host = entry_ssh_host.get()
    ssh_port = int(entry_ssh_port.get())
    ssh_user = entry_ssh_user.get()
    auth_method = auth_method_var.get()

    # --- Get all rules from the Treeview ---
    rules_to_forward = []
    for item_id in rules_tree.get_children():
        values = rules_tree.item(item_id, 'values')
        try:
            rule = {
                'local_port': int(values[0]),
                'remote_host': values[1],
                'remote_port': int(values[2])
            }
            rules_to_forward.append(rule)
        except (ValueError, IndexError):
            messagebox.showerror("Error", f"Invalid rule in list: {values}")
            return
            
    if not rules_to_forward:
        messagebox.showerror("Error", "No forwarding rules defined. Please add at least one rule.")
        return

    jump_sock = None
    try:
        # --- Handle Jump Host Connection (if enabled) ---
        if use_jump_host_var.get():
            # (Jump host logic remains the same)
            jump_host = entry_jump_host.get()
            jump_port = int(entry_jump_port.get())
            jump_user = entry_jump_user.get()
            jump_auth_method = jump_auth_method_var.get()
            jump_client = paramiko.SSHClient()
            jump_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            jump_connect_kwargs = {'hostname': jump_host, 'port': jump_port, 'username': jump_user, 'timeout': 10}
            if jump_auth_method == 'password':
                jump_connect_kwargs['password'] = entry_jump_pass.get()
            else:
                key_filename = entry_jump_key.get()
                if not key_filename or not os.path.exists(key_filename): raise ValueError("Jump host SSH key file not found.")
                jump_connect_kwargs['key_filename'] = key_filename
            status_label.config(text=f"Status: Connecting to jump host {jump_host}...")
            app.update_idletasks()
            jump_client.connect(**jump_connect_kwargs)
            transport = jump_client.get_transport()
            dest_addr = (ssh_host, ssh_port)
            local_addr = ('127.0.0.1', 0)
            jump_sock = transport.open_channel("direct-tcpip", dest_addr, local_addr)

        # --- Establish Final SSH Connection ---
        ssh_client = paramiko.SSHClient()
        ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        status_label.config(text=f"Status: Connecting to {ssh_host}...")
        app.update_idletasks()
        connect_kwargs = {'hostname': ssh_host, 'port': ssh_port, 'username': ssh_user, 'timeout': 10, 'sock': jump_sock}
        if auth_method == 'password':
            connect_kwargs['password'] = entry_ssh_pass.get()
        else:
            key_filename = entry_ssh_key.get()
            if not key_filename or not os.path.exists(key_filename): raise ValueError("Destination SSH key file not found.")
            connect_kwargs['key_filename'] = key_filename
        ssh_client.connect(**connect_kwargs)
        
        transport = ssh_client.get_transport()
        if not transport or not transport.is_active():
            raise Exception("Failed to get active transport.")
        
        status_label.config(text=f"Status: Connected to {ssh_host}. Starting tunnels...")
        
        # --- Start one forwarding thread FOR EACH RULE ---
        for rule in rules_to_forward:
            thread = threading.Thread(
                target=forward_tunnel,
                args=(
                    rule['local_port'],
                    rule['remote_host'],
                    rule['remote_port'],
                    transport,
                    stop_event
                ),
                daemon=True
            )
            thread.start()
            forwarding_threads.append(thread) # Add thread to our list
        
        status_label.config(text=f"Status: Forwarding {len(forwarding_threads)} rule(s).")
        start_button.config(state=tk.DISABLED)
        stop_button.config(state=tk.NORMAL)
        jupyter_button.config(state=tk.NORMAL)
        batch_button.config(state=tk.NORMAL)
        # Disable rule modification buttons
        add_rule_button.config(state=tk.DISABLED)
        remove_rule_button.config(state=tk.DISABLED)


    except Exception as e:
        messagebox.showerror("Connection Error", f"Failed to connect or start forwarding:\n{e}")
        status_label.config(text="Status: Disconnected")
        if ssh_client: ssh_client.close()
        if jump_client: jump_client.close()
        forwarding_threads.clear() # Ensure list is empty on failure


def stop_forwarding(show_message=True):
    """
    Stops all forwarding threads and closes the SSH connection(s).
    """
    global ssh_client, jump_client, forwarding_threads

    if not forwarding_threads and not ssh_client and not jump_client:
        if show_message: messagebox.showinfo("Info", "Forwarding is not active.")
        return

    print("Stopping forwarding...")
    stop_event.set()

    if forwarding_threads:
        for t in forwarding_threads:
            t.join(timeout=1.0) # Join each thread
        forwarding_threads.clear() # Clear the list
    
    if ssh_client:
        ssh_client.close(); ssh_client = None
        print("SSH client closed.")
    
    if jump_client:
        jump_client.close(); jump_client = None
        print("Jump host client closed.")

    status_label.config(text="Status: Disconnected")
    start_button.config(state=tk.NORMAL)
    stop_button.config(state=tk.DISABLED)
    jupyter_button.config(state=tk.DISABLED)
    batch_button.config(state=tk.DISABLED)
    # Re-enable rule modification buttons
    add_rule_button.config(state=tk.NORMAL)
    remove_rule_button.config(state=tk.NORMAL)
    
    if show_message: messagebox.showinfo("Success", "Forwarding stopped.")


def on_closing():
    """ Handles the window close event. """
    if forwarding_threads: # Check list
        if messagebox.askokcancel("Quit", "Forwarding is active. Do you want to stop it and quit?"):
            stop_forwarding(show_message=False)
            app.destroy()
    else:
        app.destroy()

# --- (NEW) Config file helper functions ---

def set_entry_text(entry_widget, text):
    """Helper to clear and set text in an Entry widget."""
    entry_widget.delete(0, tk.END)
    entry_widget.insert(0, text)

def save_config():
    """Saves the current GUI settings to the config file."""
    config = configparser.ConfigParser()
    
    # SSH Server details
    config['SSH'] = {
        'Host': entry_ssh_host.get(),
        'Port': entry_ssh_port.get(),
        'Username': entry_ssh_user.get(),
        'AuthMethod': auth_method_var.get(),
        'KeyFile': entry_ssh_key.get()
        # Note: Passwords are NOT saved for security.
    }
    
    # Jump Host details
    config['JumpHost'] = {
        'Enabled': use_jump_host_var.get(),
        'Host': entry_jump_host.get(),
        'Port': entry_jump_port.get(),
        'Username': entry_jump_user.get(),
        'AuthMethod': jump_auth_method_var.get(),
        'KeyFile': entry_jump_key.get()
    }
    
    # Forwarding Rules
    config['ForwardingRules'] = {}
    i = 0
    for item_id in rules_tree.get_children():
        values = rules_tree.item(item_id, 'values')
        config['ForwardingRules'][f'rule_{i}'] = ",".join(map(str, values))
        i += 1
        
    try:
        with open(CONFIG_FILE, 'w') as configfile:
            config.write(configfile)
        messagebox.showinfo("Config Saved", f"Configuration saved to {CONFIG_FILE}.\nPasswords are not saved for security.")
    except Exception as e:
        messagebox.showerror("Error", f"Failed to save config file:\n{e}")

def load_config():
    """Loads settings from the config file into the GUI."""
    if not os.path.exists(CONFIG_FILE):
        return # No config file to load

    config = configparser.ConfigParser()
    config.read(CONFIG_FILE)
    
    try:
        # Load SSH
        if 'SSH' in config:
            ssh_config = config['SSH']
            set_entry_text(entry_ssh_host, ssh_config.get('Host', ''))
            set_entry_text(entry_ssh_port, ssh_config.get('Port', '22'))
            set_entry_text(entry_ssh_user, ssh_config.get('Username', ''))
            auth_method_var.set(ssh_config.get('AuthMethod', 'password'))
            set_entry_text(entry_ssh_key, ssh_config.get('KeyFile', ''))

        # Load Jump Host
        if 'JumpHost' in config:
            jump_config = config['JumpHost']
            use_jump_host_var.set(jump_config.getboolean('Enabled', False))
            set_entry_text(entry_jump_host, jump_config.get('Host', ''))
            set_entry_text(entry_jump_port, jump_config.get('Port', '22'))
            set_entry_text(entry_jump_user, jump_config.get('Username', ''))
            jump_auth_method_var.set(jump_config.get('AuthMethod', 'password'))
            set_entry_text(entry_jump_key, jump_config.get('KeyFile', ''))
            
        # Load Forwarding Rules
        if 'ForwardingRules' in config:
            # Clear existing rules
            for i in rules_tree.get_children():
                rules_tree.delete(i)
                
            rule_config = config['ForwardingRules']
            for key in rule_config:
                if key.startswith('rule_'):
                    values = rule_config[key].split(',')
                    if len(values) == 3:
                        rules_tree.insert("", tk.END, values=values)
                        
    except Exception as e:
        messagebox.showerror("Config Load Error", f"Failed to load config file:\n{e}")
        
    finally:
        # Update GUI state to reflect loaded values
        toggle_auth_fields(auth_method_var, entry_ssh_pass, entry_ssh_key, browse_button)
        toggle_jump_host_fields()


# --- (GUI helper functions) ---
def browse_key_file(entry_widget):
    filename = filedialog.askopenfilename(title="Select SSH Private Key", filetypes=(("All files", "*.*"),))
    if filename:
        entry_widget.delete(0, tk.END)
        entry_widget.insert(0, filename)

def toggle_auth_fields(var, pass_entry, key_entry, browse_btn):
    state = 'normal' if var.get() == 'password' else 'disabled'
    pass_entry.config(state=state)
    key_entry.config(state='!'+state)
    browse_btn.config(state='!'+state)

def toggle_jump_host_fields():
    state = tk.NORMAL if use_jump_host_var.get() else tk.DISABLED
    for child in jump_frame.winfo_children():
        child.configure(state=state)
    if use_jump_host_var.get():
        toggle_auth_fields(jump_auth_method_var, entry_jump_pass, entry_jump_key, jump_browse_button)
    else:
        entry_jump_pass.config(state=tk.DISABLED)
        entry_jump_key.config(state=tk.DISABLED)
        jump_browse_button.config(state=tk.DISABLED)

# --- (New GUI functions for managing rules) ---
def add_rule_to_tree():
    """ Adds the rule from the entry boxes to the treeview list """
    local_port = entry_local_port.get()
    remote_host = entry_remote_host.get()
    remote_port = entry_remote_port.get()

    # Validation
    if not remote_host:
        messagebox.showwarning("Warning", "Remote Host cannot be empty.")
        return
    try:
        lp = int(local_port)
        rp = int(remote_port)
        if not (0 < lp < 65536 and 0 < rp < 65536):
            raise ValueError("Port out of range")
    except ValueError:
        messagebox.showwarning("Warning", "Local and Remote Ports must be valid numbers (1-65535).")
        return
        
    # Check for duplicate local port
    for item_id in rules_tree.get_children():
        values = rules_tree.item(item_id, 'values')
        if values and int(values[0]) == lp:
            messagebox.showwarning("Warning", f"Local Port {lp} is already in the list.")
            return

    # Add to tree
    rules_tree.insert("", tk.END, values=(local_port, remote_host, remote_port))
    
    # Clear entry boxes
    entry_local_port.delete(0, tk.END)
    entry_remote_host.delete(0, tk.END)
    entry_remote_port.delete(0, tk.END)
    entry_local_port.insert(0, str(lp + 1)) # Suggest next port
    entry_remote_host.insert(0, "localhost")

def go_to_web(url):

    print(f"Opening browser to {url}")
    webbrowser.open(url)
    
    # Optional: Warn if not connected
    if not forwarding_threads:
        print("Note: Forwarding not active. Browser may show 'Connection Refused'.")

def remove_selected_rule():
    """ Removes the selected rule(s) from the treeview list """
    selected_items = rules_tree.selection()
    if not selected_items:
        messagebox.showwarning("Warning", "Please select one or more rules to remove.")
        return
    
    if messagebox.askyesno("Confirm", "Remove selected rule(s)?"):
        for item in selected_items:
            rules_tree.delete(item)


# --- GUI Setup ---
app = tk.Tk()
app.title("SSH Local Port Forwarder (Multi-Port)")
app.geometry("500x750")

# --- (NEW) Menu Bar ---
menubar = tk.Menu(app)
file_menu = tk.Menu(menubar, tearoff=0)
file_menu.add_command(label="Load Config", command=load_config)
file_menu.add_command(label="Save Config", command=save_config)
file_menu.add_separator()
file_menu.add_command(label="Exit", command=on_closing)
menubar.add_cascade(label="File", menu=file_menu)
app.config(menu=menubar)

main_frame = ttk.Frame(app, padding="10")
main_frame.pack(fill=tk.BOTH, expand=True)

# --- SSH Connection Details (Unchanged) ---
ssh_frame = ttk.LabelFrame(main_frame, text="Destination SSH Server", padding="10")
ssh_frame.pack(fill=tk.X, pady=5)
ssh_frame.columnconfigure(1, weight=1)

ttk.Label(ssh_frame, text="Host:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
entry_ssh_host = ttk.Entry(ssh_frame)
entry_ssh_host.grid(row=0, column=1, columnspan=2, sticky=tk.EW)
#entry_ssh_host.insert(0, "your_ssh_server.com")
ttk.Label(ssh_frame, text="Port:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=2)
entry_ssh_port = ttk.Entry(ssh_frame, width=10)
entry_ssh_port.grid(row=1, column=1, columnspan=2, sticky=tk.W)
#entry_ssh_port.insert(0, "22")
ttk.Label(ssh_frame, text="Username:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=2)
entry_ssh_user = ttk.Entry(ssh_frame)
entry_ssh_user.grid(row=2, column=1, columnspan=2, sticky=tk.EW)
auth_method_var = tk.StringVar(value="password")
ttk.Label(ssh_frame, text="Auth:").grid(row=3, column=0, sticky=tk.W, padx=5, pady=5)
password_radio = ttk.Radiobutton(ssh_frame, text="Password", variable=auth_method_var, value="password", command=lambda: toggle_auth_fields(auth_method_var, entry_ssh_pass, entry_ssh_key, browse_button))
password_radio.grid(row=3, column=1, sticky=tk.W, pady=5)
key_radio = ttk.Radiobutton(ssh_frame, text="SSH Key", variable=auth_method_var, value="key", command=lambda: toggle_auth_fields(auth_method_var, entry_ssh_pass, entry_ssh_key, browse_button))
key_radio.grid(row=3, column=2, sticky=tk.W, padx=10, pady=5)
ttk.Label(ssh_frame, text="Password:").grid(row=4, column=0, sticky=tk.W, padx=5, pady=2)
entry_ssh_pass = ttk.Entry(ssh_frame, show="*")
entry_ssh_pass.grid(row=4, column=1, columnspan=2, sticky=tk.EW)
ttk.Label(ssh_frame, text="Key File:").grid(row=5, column=0, sticky=tk.W, padx=5, pady=2)
entry_ssh_key = ttk.Entry(ssh_frame)
entry_ssh_key.grid(row=5, column=1, sticky=tk.EW)
browse_button = ttk.Button(ssh_frame, text="Browse...", command=lambda: browse_key_file(entry_ssh_key))
browse_button.grid(row=5, column=2, sticky=tk.W, padx=5)

# --- Jump Host Details (Unchanged) ---
jump_host_controls_frame = ttk.Frame(main_frame)
jump_host_controls_frame.pack(fill=tk.X, pady=(10,0))
use_jump_host_var = tk.BooleanVar(value=False)
jump_check = ttk.Checkbutton(jump_host_controls_frame, text="Use Jump Host (Bastion)", variable=use_jump_host_var, command=toggle_jump_host_fields)
jump_check.pack(anchor=tk.W)
jump_frame = ttk.LabelFrame(main_frame, text="Jump Host Details", padding="10")
jump_frame.pack(fill=tk.X, pady=5)
jump_frame.columnconfigure(1, weight=1)
# (All jump host fields are the same)
ttk.Label(jump_frame, text="Host:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
entry_jump_host = ttk.Entry(jump_frame)
entry_jump_host.grid(row=0, column=1, columnspan=2, sticky=tk.EW)
ttk.Label(jump_frame, text="Port:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=2)
entry_jump_port = ttk.Entry(jump_frame, width=10)
entry_jump_port.grid(row=1, column=1, columnspan=2, sticky=tk.W)
#entry_jump_port.insert(0, "22")
ttk.Label(jump_frame, text="Username:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=2)
entry_jump_user = ttk.Entry(jump_frame)
entry_jump_user.grid(row=2, column=1, columnspan=2, sticky=tk.EW)
jump_auth_method_var = tk.StringVar(value="password")
ttk.Label(jump_frame, text="Auth:").grid(row=3, column=0, sticky=tk.W, padx=5, pady=5)
jump_password_radio = ttk.Radiobutton(jump_frame, text="Password", variable=jump_auth_method_var, value="password", command=lambda: toggle_auth_fields(jump_auth_method_var, entry_jump_pass, entry_jump_key, jump_browse_button))
jump_password_radio.grid(row=3, column=1, sticky=tk.W, pady=5)
jump_key_radio = ttk.Radiobutton(jump_frame, text="SSH Key", variable=jump_auth_method_var, value="key", command=lambda: toggle_auth_fields(jump_auth_method_var, entry_jump_pass, entry_jump_key, jump_browse_button))
jump_key_radio.grid(row=3, column=2, sticky=tk.W, padx=10, pady=5)
ttk.Label(jump_frame, text="Password:").grid(row=4, column=0, sticky=tk.W, padx=5, pady=2)
entry_jump_pass = ttk.Entry(jump_frame, show="*")
entry_jump_pass.grid(row=4, column=1, columnspan=2, sticky=tk.EW)
ttk.Label(jump_frame, text="Key File:").grid(row=5, column=0, sticky=tk.W, padx=5, pady=2)
entry_jump_key = ttk.Entry(jump_frame)
entry_jump_key.grid(row=5, column=1, sticky=tk.EW)
jump_browse_button = ttk.Button(jump_frame, text="Browse...", command=lambda: browse_key_file(entry_jump_key))
jump_browse_button.grid(row=5, column=2, sticky=tk.W, padx=5)

# --- (UPDATED) Preset Buttons ---




# --- Port Forwarding Details (Unchanged) ---
# This frame is now for ADDING a rule
forward_frame = ttk.LabelFrame(main_frame, text="Add Forwarding Rule", padding="10")
forward_frame.pack(fill=tk.X, pady=5)
forward_frame.columnconfigure(1, weight=1)

ttk.Label(forward_frame, text="Local Port:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
entry_local_port = ttk.Entry(forward_frame, width=10)
entry_local_port.grid(row=0, column=1, sticky=tk.W)
entry_local_port.insert(0, "8080")

ttk.Label(forward_frame, text="Remote Host:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=2)
entry_remote_host = ttk.Entry(forward_frame)
entry_remote_host.grid(row=1, column=1, sticky=tk.EW)
entry_remote_host.insert(0, "localhost")

ttk.Label(forward_frame, text="Remote Port:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=2)
entry_remote_port = ttk.Entry(forward_frame, width=10)
entry_remote_port.grid(row=2, column=1, sticky=tk.W)
entry_remote_port.insert(0, "80")

add_rule_button = ttk.Button(forward_frame, text="Add Rule", command=add_rule_to_tree)
add_rule_button.grid(row=1, column=2, padx=10, sticky=tk.E)

# --- Frame for the list of rules (Unchanged) ---
rules_list_frame = ttk.LabelFrame(main_frame, text="Active Forwarding Rules", padding="10")
rules_list_frame.pack(fill=tk.BOTH, pady=5, expand=True)

columns = ("local_port", "remote_host", "remote_port")
rules_tree = ttk.Treeview(rules_list_frame, columns=columns, show="headings", height=5)
rules_tree.heading("local_port", text="Local Port")
rules_tree.heading("remote_host", text="Remote Host")
rules_tree.heading("remote_port", text="Remote Port")
rules_tree.column("local_port", width=80, anchor=tk.W)
rules_tree.column("remote_host", width=200, anchor=tk.W)
rules_tree.column("remote_port", width=80, anchor=tk.W)
rules_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

tree_scrollbar = ttk.Scrollbar(rules_list_frame, orient="vertical", command=rules_tree.yview)
rules_tree.configure(yscrollcommand=tree_scrollbar.set)
tree_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

remove_rule_button = ttk.Button(main_frame, text="Remove Selected Rule", command=remove_selected_rule)
remove_rule_button.pack(fill=tk.X, padx=10, pady=(0, 5))


# --- Control Buttons and Status (Unchanged) ---
control_frame = ttk.Frame(main_frame, padding="10")
control_frame.pack(fill=tk.X, side=tk.BOTTOM) # Move to bottom

start_button = ttk.Button(control_frame, text="Start Forwarding", command=start_forwarding)
start_button.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)

stop_button = ttk.Button(control_frame, text="Stop Forwarding", command=stop_forwarding, state=tk.DISABLED)
stop_button.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)


jupyter_button = ttk.Button(control_frame, text="Jupyter Notebook", command=lambda: go_to_web("http://localhost:5002/lab"), state=tk.DISABLED)
jupyter_button.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)

batch_button = ttk.Button(control_frame, text="Batch Scheduler",command=lambda: go_to_web("http://localhost:5001"), state=tk.DISABLED)
batch_button.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)




status_label = ttk.Label(main_frame, text="Status: Disconnected", relief=tk.SUNKEN, anchor=tk.W)
status_label.pack(side=tk.BOTTOM, fill=tk.X, ipady=2)





# --- Initialize field states and Set window closing protocol ---
# Note: We removed the hardcoded inserts (e.g., 'your_ssh_server.com')
# The load_config() function will populate them.

# --- (NEW) Load config on startup ---
try:
    load_config()
except Exception as e:
    print(f"Could not load config file on startup: {e}")

# Call toggles one last time after load_config to ensure GUI is in a consistent state
toggle_auth_fields(auth_method_var, entry_ssh_pass, entry_ssh_key, browse_button)
toggle_jump_host_fields()

app.protocol("WM_DELETE_WINDOW", on_closing)

# --- Run the application ---
app.mainloop()