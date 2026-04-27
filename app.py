import sys
import argparse
import datetime
import gi

# CLI Quick Add implementation
if len(sys.argv) > 1 and sys.argv[1] == 'add':
    parser = argparse.ArgumentParser(prog=f"python3 {sys.argv[0]} add")
    parser.add_argument("title", help="Title of the task")
    parser.add_argument("-t", "--tags", default="Personal", help="Tags (#work #urgent)")
    parser.add_argument("-d", "--date", help="Due date (YYYY-MM-DD), defaults to today")
    parser.add_argument("-r", "--recurrence", default="None", choices=["None", "Daily", "Weekly", "Monthly"], help="Recurrence")
    parser.add_argument("-p", "--priority", default="Normal", choices=["High", "Normal", "Low"], help="Priority")
    parser.add_argument("-c", "--color", default="Default", choices=["Default", "Blue", "Green", "Red", "Yellow", "Purple"], help="Background Color")
    args = parser.parse_args(sys.argv[2:])
    
    import database
    database.init_db()
    
    due_date = args.date if args.date else datetime.date.today().isoformat()
    database.add_task(args.title, category=args.tags, due_date=due_date, recurrence_type=args.recurrence, priority=args.priority, color=args.color)
    print(f"Task '{args.title}' added successfully!")
    sys.exit(0)

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gio, GLib, Gdk
import os
import json
from pathlib import Path

import database

# ── App config helpers ───────────────────────────────────────────────────────
CONFIG_PATH = Path(os.path.expanduser("~/.local/share/python_todo_app/config.json"))

def _load_config():
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text())
        except Exception:
            pass
    return {}

def _save_config(cfg: dict):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2))

# ── Global app background CSS provider ───────────────────────────────────────
_app_bg_provider = Gtk.CssProvider()

def _apply_app_bg(image_path: str | None):
    """Inject or clear the full-window background image CSS."""
    if image_path and os.path.exists(image_path):
        safe = image_path.replace("'", "\\'")
        css = f"""
            .app-bg-window {{
                background-image:
                    linear-gradient(rgba(0,0,0,0.45), rgba(0,0,0,0.45)),
                    url('file://{safe}');
                background-size: cover;
                background-position: center;
            }}
        """
    else:
        css = ".app-bg-window {}"
    _app_bg_provider.load_from_data(css.encode())


def _is_image_path(value):
    """Return True if the stored 'color' value is actually a filesystem path."""
    if not value:
        return False
    return value.startswith('/') or value.startswith('file://')


def _apply_bg(row, value):
    """Apply either a named color class or an image-based CSS to a GTK row widget."""
    if not value or value == 'Default':
        return
    if _is_image_path(value):
        # Normalise to an absolute path
        path = value.replace('file://', '')
        # Escape single quotes inside the path
        safe_path = path.replace("'", "\\'")
        css = f"""
            row.task-img-bg {{
                background-image:
                    linear-gradient(rgba(0,0,0,0.55), rgba(0,0,0,0.55)),
                    url('file://{safe_path}');
                background-size: cover;
                background-position: center;
                border-radius: 12px;
            }}
            row.task-img-bg > box > label.title  {{ color: white; }}
            row.task-img-bg > box > label.subtitle {{ color: rgba(255,255,255,0.82); }}
        """
        provider = Gtk.CssProvider()
        provider.load_from_data(css.encode())
        row.get_style_context().add_provider(provider, Gtk.STYLE_PROVIDER_PRIORITY_USER)
        row.add_css_class('task-img-bg')
    else:
        row.add_css_class(f'task-bg-{value}')


class TaskRow(Adw.ActionRow):
    def __init__(self, task_data, window, reload_callback):
        super().__init__()
        self.task_id = task_data['id']
        self.title = task_data['title']
        self.tags = task_data['category']
        self.priority = task_data['priority'] or 'Normal'
        self.color = task_data['color'] or 'Default'
        self.due_date = task_data['due_date']
        self.created_at = task_data['created_at'][:16]
        self.updated_at = task_data['updated_at'][:16]
        self.window = window
        self.reload_callback = reload_callback
        
        if self.priority == 'High':
            self.title = f"🔥 {self.title}"
            
        self.set_title(self.title)
        
        # Apply custom background (color class or image)
        _apply_bg(self, self.color)
        
        rec_text = " (Recurring)" if task_data['template_id'] else ""
        subtitle_text = f"Tags: {self.tags}{rec_text} | {self.priority} Priority\nDue: {self.due_date} | Added: {self.created_at}\nUpdated: {self.updated_at}"
        self.set_subtitle(subtitle_text)
        self.set_subtitle_lines(3)
        
        self.set_icon_name("tag-symbolic")

        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        button_box.set_valign(Gtk.Align.CENTER)
        
        btn_remind = Gtk.Button(icon_name="appointment-new-symbolic")
        btn_remind.add_css_class("circular")
        btn_remind.set_tooltip_text("Send immediate Desktop Reminder")
        btn_remind.connect("clicked", self.on_remind)
        button_box.append(btn_remind)
        
        btn_yes = Gtk.Button(icon_name="emblem-ok-symbolic")
        btn_yes.add_css_class("suggested-action")
        btn_yes.add_css_class("circular")
        btn_yes.set_tooltip_text("Mark as Completed")
        btn_yes.connect("clicked", self.on_action, "completed")
        button_box.append(btn_yes)
        
        btn_no = Gtk.Button(icon_name="action-unavailable-symbolic")
        btn_no.add_css_class("circular")
        btn_no.set_tooltip_text("Mark as Missed")
        btn_no.connect("clicked", self.on_action, "missed")
        button_box.append(btn_no)
        
        btn_trash = Gtk.Button(icon_name="user-trash-symbolic")
        btn_trash.add_css_class("destructive-action")
        btn_trash.add_css_class("circular")
        btn_trash.set_tooltip_text("Delete Task Forever")
        btn_trash.connect("clicked", self.on_delete)
        button_box.append(btn_trash)
        
        self.add_suffix(button_box)
        
    def on_action(self, btn, action_type):
        database.update_task_status(self.task_id, action_type)
        self.window.toast_overlay.add_toast(Adw.Toast.new(f"Task marked as {action_type}."))
        self.reload_callback()
        
    def on_delete(self, btn):
        database.delete_task(self.task_id)
        self.window.toast_overlay.add_toast(Adw.Toast.new("Task deleted permanently."))
        self.reload_callback()
        
    def on_remind(self, btn):
        notification = Gio.Notification.new(self.title)
        notification.set_body(f"Reminder for custom task pending due {self.due_date}. Tags: {self.tags}.")
        app = Gio.Application.get_default()
        if app:
            app.send_notification(f"remind-{self.task_id}", notification)
        self.window.toast_overlay.add_toast(Adw.Toast.new("Desktop Reminder sent!"))


class HistoryRow(Adw.ActionRow):
    def __init__(self, task_data, window, reload_callback):
        super().__init__()
        self.task_id = task_data['id']
        self.title = task_data['title']
        self.tags = task_data['category']
        self.priority = task_data['priority'] or 'Normal'
        self.color = task_data['color'] or 'Default'
        self.due_date = task_data['due_date']
        self.status = task_data['status']
        self.updated_at = task_data['updated_at'][:16]
        self.created_at = task_data['created_at'][:16]
        self.window = window
        self.reload_callback = reload_callback
        
        if self.priority == 'High':
            self.title = f"🔥 {self.title}"
            
        self.set_title(self.title)
        
        _apply_bg(self, self.color)
        
        status_text = "Completed" if self.status == 'completed' else "Missed"
        self.set_subtitle(f"Tags: {self.tags} | {self.priority} Priority\nCreated: {self.created_at} | {status_text}: {self.updated_at}\nOriginally due: {self.due_date}")
        self.set_subtitle_lines(3)
        
        self.set_icon_name("emblem-ok-symbolic" if self.status == 'completed' else "emblem-important-symbolic")
            
        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        button_box.set_valign(Gtk.Align.CENTER)
        
        if self.status != 'completed':
            btn_redo = Gtk.Button(icon_name="emblem-ok-symbolic")
            btn_redo.add_css_class("suggested-action")
            btn_redo.add_css_class("circular")
            btn_redo.set_tooltip_text("Actually, I completed this")
            btn_redo.connect("clicked", self.on_action, "completed")
            button_box.append(btn_redo)
            
        btn_trash = Gtk.Button(icon_name="user-trash-symbolic")
        btn_trash.add_css_class("destructive-action")
        btn_trash.add_css_class("circular")
        btn_trash.set_tooltip_text("Clear this from History")
        btn_trash.connect("clicked", self.on_delete)
        button_box.append(btn_trash)
        
        self.add_suffix(button_box)
            
    def on_action(self, btn, action_type):
        database.update_task_status(self.task_id, action_type)
        self.window.toast_overlay.add_toast(Adw.Toast.new(f"Task recovered to {action_type}."))
        self.reload_callback()

    def on_delete(self, btn):
        database.delete_task(self.task_id)
        self.window.toast_overlay.add_toast(Adw.Toast.new("Historical task deleted."))
        self.reload_callback()

class TemplateRow(Adw.ActionRow):
    def __init__(self, template_data, window, reload_callback):
        super().__init__()
        self.template_id = template_data['id']
        self.title = template_data['title']
        self.tags = template_data['category']
        self.priority = template_data['priority'] or 'Normal'
        self.color = template_data['color'] or 'Default'
        self.recurrence_type = template_data['recurrence_type']
        self.created_at = template_data['created_at'][:16]
        self.window = window
        self.reload_callback = reload_callback
        
        if self.priority == 'High':
            self.title = f"🔥 {self.title}"
            
        self.set_title(self.title)
        
        _apply_bg(self, self.color)
            
        self.set_subtitle(f"Tags: {self.tags} | {self.priority} | Recurs: {self.recurrence_type}\nCreated: {self.created_at}")
        self.set_subtitle_lines(2)
        
        self.set_icon_name("view-refresh-symbolic")

        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        button_box.set_valign(Gtk.Align.CENTER)
        
        btn_del = Gtk.Button(icon_name="edit-delete-symbolic")
        btn_del.add_css_class("destructive-action")
        btn_del.add_css_class("circular")
        btn_del.connect("clicked", self.on_delete)
        button_box.append(btn_del)
        
        self.add_suffix(button_box)
        
    def on_delete(self, btn):
        database.delete_template(self.template_id)
        self.window.toast_overlay.add_toast(Adw.Toast.new("Schedule removed."))
        self.reload_callback()


class TodayView(Gtk.Box):
    def __init__(self, window):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.window = window
        self.set_margin_start(16); self.set_margin_end(16); self.set_margin_top(16); self.set_margin_bottom(16)
        
        self._selected_image_path = None   # holds path chosen by file chooser

        self.add_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.add_box.set_halign(Gtk.Align.CENTER)
        
        self.task_entry = Gtk.Entry(placeholder_text="Add task...")
        self.task_entry.set_width_chars(20)
        self.task_entry.connect("activate", self.on_add_task)
        self.add_box.append(self.task_entry)
        
        self.tags_entry = Gtk.Entry(placeholder_text="Tags (#work)")
        self.tags_entry.set_width_chars(15)
        self.tags_entry.connect("activate", self.on_add_task)
        self.add_box.append(self.tags_entry)
        
        # Color dropdown (falls back to 'Default' when an image is chosen)
        self.color_model = Gtk.StringList.new(["Default", "Blue", "Green", "Red", "Yellow", "Purple"])
        self.color_dropdown = Gtk.DropDown.new(self.color_model, None)
        self.color_dropdown.set_tooltip_text("Context Color (overridden if image chosen)")
        self.add_box.append(self.color_dropdown)
        
        # Image picker button
        self.img_btn = Gtk.Button(icon_name="insert-image-symbolic")
        self.img_btn.set_tooltip_text("Set background image for this task")
        self.img_btn.add_css_class("circular")
        self.img_btn.connect("clicked", self.on_pick_image)
        self.add_box.append(self.img_btn)

        # Small label that echoes the filename once picked
        self.img_label = Gtk.Label(label="No image", ellipsize=3)  # PANGO_ELLIPSIZE_END=3
        self.img_label.set_width_chars(12)
        self.img_label.add_css_class("dim-label")
        self.add_box.append(self.img_label)
        
        self.priority_model = Gtk.StringList.new(["Normal", "High", "Low"])
        self.priority_dropdown = Gtk.DropDown.new(self.priority_model, None)
        self.priority_dropdown.set_tooltip_text("Priority")
        self.add_box.append(self.priority_dropdown)
        
        self.recurrence_model = Gtk.StringList.new(["None", "Daily", "Weekly", "Monthly"])
        self.recurrence_dropdown = Gtk.DropDown.new(self.recurrence_model, None)
        self.recurrence_dropdown.set_tooltip_text("Recurrence")
        self.add_box.append(self.recurrence_dropdown)
        
        self.add_button = Gtk.Button(icon_name="list-add-symbolic")
        self.add_button.add_css_class("suggested-action")
        self.add_button.connect("clicked", self.on_add_task)
        self.add_box.append(self.add_button)
        
        self.append(self.add_box)
        
        self.scrolled = Gtk.ScrolledWindow()
        self.scrolled.set_vexpand(True)
        self.append(self.scrolled)
        
        self.clamp = Adw.Clamp()
        self.clamp.set_maximum_size(700)
        self.scrolled.set_child(self.clamp)
        
        self.content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.clamp.set_child(self.content_box)
        
        self.load_tasks()
        
    def load_tasks(self):
        while (child := self.content_box.get_first_child()) is not None:
            self.content_box.remove(child)
            
        today = datetime.date.today()
        tasks = database.get_tasks_for_date(today)
        
        if not tasks:
            self.content_box.append(Adw.StatusPage(title="All Caught Up", description="No remaining tasks for today.", icon_name="emblem-ok-symbolic"))
        else:
            group = Adw.PreferencesGroup()
            for row in tasks:
                group.add(TaskRow(row, self.window, self.window.reload_all_views))
            self.content_box.append(group)
            
    def on_pick_image(self, btn):
        """Open a native file chooser to select an image (GTK 4.6 compatible)."""
        chooser = Gtk.FileChooserNative(
            title="Choose a background image",
            transient_for=self.window,
            action=Gtk.FileChooserAction.OPEN,
            accept_label="Select",
            cancel_label="Cancel",
        )
        img_filter = Gtk.FileFilter()
        img_filter.set_name("Images")
        img_filter.add_mime_type("image/png")
        img_filter.add_mime_type("image/jpeg")
        img_filter.add_mime_type("image/webp")
        img_filter.add_mime_type("image/gif")
        chooser.add_filter(img_filter)
        chooser.connect("response", self._on_image_chosen)
        # Keep a reference so the dialog isn't garbage-collected
        self._file_chooser = chooser
        chooser.show()

    def _on_image_chosen(self, chooser, response):
        if response == Gtk.ResponseType.ACCEPT:
            gfile = chooser.get_file()
            if gfile:
                self._selected_image_path = gfile.get_path()
                self.img_label.set_label(os.path.basename(self._selected_image_path))
                self.img_btn.set_icon_name("emblem-photos-symbolic")
        self._file_chooser = None   # release reference

    def on_add_task(self, *args):
        title = self.task_entry.get_text().strip()
        if not title: return
        tags = self.tags_entry.get_text().strip() or "Personal"
        pri = ["Normal", "High", "Low"][self.priority_dropdown.get_selected()]
        rec = ["None", "Daily", "Weekly", "Monthly"][self.recurrence_dropdown.get_selected()]
        
        # Image path takes priority over the color dropdown
        if self._selected_image_path:
            bg_value = self._selected_image_path
        else:
            bg_value = ["Default", "Blue", "Green", "Red", "Yellow", "Purple"][self.color_dropdown.get_selected()]
        
        database.add_task(title, category=tags, due_date=datetime.date.today().isoformat(), recurrence_type=rec, priority=pri, color=bg_value)
        # Reset image selection
        self.task_entry.set_text("")
        self._selected_image_path = None
        self.img_label.set_label("No image")
        self.img_btn.set_icon_name("insert-image-symbolic")
        self.window.reload_all_views()
        self.window.toast_overlay.add_toast(Adw.Toast.new("Task added with custom background."))


class CatchUpView(Gtk.Box):
    def __init__(self, window):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.window = window
        self.scrolled = Gtk.ScrolledWindow()
        self.scrolled.set_vexpand(True)
        self.append(self.scrolled)
        self.clamp = Adw.Clamp()
        self.clamp.set_maximum_size(600)
        self.scrolled.set_child(self.clamp)
        self.content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.clamp.set_child(self.content_box)
        self.load_tasks()
        
    def load_tasks(self):
        while (child := self.content_box.get_first_child()) is not None:
            self.content_box.remove(child)
            
        today = datetime.date.today()
        tasks = database.get_missed_tasks(today)
        if not tasks:
            self.content_box.append(Adw.StatusPage(title="No Missed Tasks", description="You are fully caught up!", icon_name="face-smile-symbolic"))
        else:
            self.content_box.append(Adw.StatusPage(title="Welcome Back", description="You have a few missed tasks. Let's catch up.", icon_name="emblem-important-symbolic"))
            group = Adw.PreferencesGroup()
            for row in tasks:
                group.add(TaskRow(row, self.window, self.window.reload_all_views))
            self.content_box.append(group)


class HistoryView(Gtk.Box):
    def __init__(self, window):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.window = window
        self.scrolled = Gtk.ScrolledWindow()
        self.scrolled.set_vexpand(True)
        self.append(self.scrolled)
        self.clamp = Adw.Clamp()
        self.clamp.set_maximum_size(600)
        self.scrolled.set_child(self.clamp)
        self.content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.clamp.set_child(self.content_box)
        self.load_tasks()
        
    def load_tasks(self):
        while (child := self.content_box.get_first_child()) is not None:
            self.content_box.remove(child)
            
        tasks = database.get_history_tasks()
        if not tasks:
            self.content_box.append(Adw.StatusPage(title="No History", description="Completed and missed tasks appear here.", icon_name="document-open-recent-symbolic"))
        else:
            self.content_box.append(Adw.StatusPage(title="Your History", description="Past tasks sorted by date.", icon_name="document-open-recent-symbolic"))
            group = Adw.PreferencesGroup()
            for row in tasks:
                group.add(HistoryRow(row, self.window, self.window.reload_all_views))
            self.content_box.append(group)


class TemplatesView(Gtk.Box):
    def __init__(self, window):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.window = window
        self.scrolled = Gtk.ScrolledWindow()
        self.scrolled.set_vexpand(True)
        self.append(self.scrolled)
        self.clamp = Adw.Clamp()
        self.clamp.set_maximum_size(600)
        self.scrolled.set_child(self.clamp)
        self.content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.clamp.set_child(self.content_box)
        self.load_tasks()

    def load_tasks(self):
        while (child := self.content_box.get_first_child()) is not None:
            self.content_box.remove(child)
            
        templates = database.get_templates()
        if not templates:
            self.content_box.append(Adw.StatusPage(title="No Schedules", description="You have no recurring tasks.", icon_name="view-refresh-symbolic"))
        else:
            self.content_box.append(Adw.StatusPage(title="Recurring Tasks", description="Manage your active schedules.", icon_name="view-refresh-symbolic"))
            group = Adw.PreferencesGroup()
            for row in templates:
                group.add(TemplateRow(row, self.window, self.window.reload_all_views))
            self.content_box.append(group)


class SearchView(Gtk.Box):
    def __init__(self, window):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.window = window
        self.set_margin_start(16); self.set_margin_end(16); self.set_margin_top(16)
        
        self.search_entry = Gtk.SearchEntry(placeholder_text="Search titles or #tags...")
        self.search_entry.set_hexpand(True)
        self.search_entry.connect("search-changed", self.on_search)
        self.append(self.search_entry)
        
        self.scrolled = Gtk.ScrolledWindow()
        self.scrolled.set_vexpand(True)
        self.append(self.scrolled)
        self.clamp = Adw.Clamp()
        self.clamp.set_maximum_size(600)
        self.scrolled.set_child(self.clamp)
        self.content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.clamp.set_child(self.content_box)

    def load_tasks(self):
        self.on_search(self.search_entry)

    def on_search(self, entry):
        while (child := self.content_box.get_first_child()) is not None:
            self.content_box.remove(child)
            
        text = entry.get_text().strip()
        if not text:
            self.content_box.append(Adw.StatusPage(title="Search", description="Type above to filter by #tags or title.", icon_name="system-search-symbolic"))
            return
            
        results = database.search_tasks(text)
        if not results:
            self.content_box.append(Adw.StatusPage(title="No Match", description="No tasks found for your query.", icon_name="edit-find-symbolic"))
        else:
            group = Adw.PreferencesGroup()
            for row in results:
                if row['status'] == 'pending':
                    group.add(TaskRow(row, self.window, self.window.reload_all_views))
                else:
                    group.add(HistoryRow(row, self.window, self.window.reload_all_views))
            self.content_box.append(group)

class AnalyticsView(Gtk.Box):
    def __init__(self, window):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.window = window
        self.status = Adw.StatusPage(title="Analytics Unloaded", icon_name="utilities-system-monitor-symbolic")
        self.append(self.status)
        self.load_tasks()
        
    def load_tasks(self):
        data = database.get_analytics()
        cw = data['completed_week']
        mw = data['missed_week']
        pa = data['pending_all']
        
        rate = 0
        if cw + mw > 0:
            rate = int((cw / (cw + mw)) * 100)
            
        desc = f"Last 7 Days:\n✅ {cw} Completed\n❌ {mw} Missed\n\n🎯 Success Rate: {rate}%\n------------------\n📦 Overall Backlog: {pa} pending"
        
        self.status.set_title("Your Performance")
        self.status.set_description(desc)


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.set_title("Elite To-Do")
        self.set_default_size(800, 800)
        
        self.toast_overlay = Adw.ToastOverlay()
        self.set_content(self.toast_overlay)

        self.main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.main_box.add_css_class("app-bg-window")   # ← target for bg CSS
        self.toast_overlay.set_child(self.main_box)
        
        self.view_stack = Adw.ViewStack()
        
        # HeaderBar with ViewSwitcher + background control button
        self.header = Adw.HeaderBar()
        self.view_switcher = Adw.ViewSwitcherTitle()
        self.view_switcher.set_stack(self.view_stack)
        self.header.set_title_widget(self.view_switcher)
        
        # Background image button in the header
        bg_btn = Gtk.Button(icon_name="insert-image-symbolic")
        bg_btn.set_tooltip_text("Set app background image")
        bg_btn.add_css_class("circular")
        bg_btn.connect("clicked", self.on_pick_app_bg)
        self.header.pack_end(bg_btn)
        
        clear_bg_btn = Gtk.Button(icon_name="edit-clear-symbolic")
        clear_bg_btn.set_tooltip_text("Clear app background image")
        clear_bg_btn.add_css_class("circular")
        clear_bg_btn.connect("clicked", self.on_clear_app_bg)
        self.header.pack_end(clear_bg_btn)
        
        self.main_box.append(self.header)
        
        # Apply persisted background on window creation
        cfg = _load_config()
        _apply_app_bg(cfg.get("app_bg"))
        
        # Pages
        self.today_page = TodayView(self)
        self.catchup_page = CatchUpView(self)
        self.history_page = HistoryView(self)
        self.templates_page = TemplatesView(self)
        self.search_page = SearchView(self)
        self.analytics_page = AnalyticsView(self)
        
        pg = self.view_stack.add_titled(self.today_page, "today", "Today")
        pg.set_icon_name("go-home-symbolic")
        
        pg = self.view_stack.add_titled(self.catchup_page, "catchup", "Catch Up")
        pg.set_icon_name("view-restore-symbolic")
        
        pg = self.view_stack.add_titled(self.templates_page, "templates", "Schedules")
        pg.set_icon_name("view-refresh-symbolic")
        
        pg = self.view_stack.add_titled(self.history_page, "history", "History")
        pg.set_icon_name("document-open-recent-symbolic")
        
        pg = self.view_stack.add_titled(self.search_page, "search", "Search")
        pg.set_icon_name("system-search-symbolic")
        
        pg = self.view_stack.add_titled(self.analytics_page, "analytics", "Insights")
        pg.set_icon_name("utilities-system-monitor-symbolic")
        
        self.main_box.append(self.view_stack)

    def on_pick_app_bg(self, btn):
        """Open file chooser to pick an app-wide background image."""
        chooser = Gtk.FileChooserNative(
            title="Choose App Background Image",
            transient_for=self,
            action=Gtk.FileChooserAction.OPEN,
            accept_label="Set Background",
            cancel_label="Cancel",
        )
        f = Gtk.FileFilter()
        f.set_name("Images")
        f.add_mime_type("image/png")
        f.add_mime_type("image/jpeg")
        f.add_mime_type("image/webp")
        f.add_mime_type("image/gif")
        chooser.add_filter(f)
        
        # Pre-select current bg if set
        cfg = _load_config()
        if cfg.get("app_bg") and os.path.exists(cfg["app_bg"]):
            chooser.set_file(Gio.File.new_for_path(cfg["app_bg"]))
        
        chooser.connect("response", self._on_app_bg_chosen)
        self._app_bg_chooser = chooser
        chooser.show()

    def _on_app_bg_chosen(self, chooser, response):
        if response == Gtk.ResponseType.ACCEPT:
            gfile = chooser.get_file()
            if gfile:
                path = gfile.get_path()
                _apply_app_bg(path)
                cfg = _load_config()
                cfg["app_bg"] = path
                _save_config(cfg)
                self.toast_overlay.add_toast(Adw.Toast.new("App background updated!"))
        self._app_bg_chooser = None

    def on_clear_app_bg(self, btn):
        _apply_app_bg(None)
        cfg = _load_config()
        cfg.pop("app_bg", None)
        _save_config(cfg)
        self.toast_overlay.add_toast(Adw.Toast.new("App background cleared."))

    def reload_all_views(self):
        self.today_page.load_tasks()
        self.catchup_page.load_tasks()
        self.history_page.load_tasks()
        self.templates_page.load_tasks()
        self.search_page.load_tasks()
        self.analytics_page.load_tasks()


class TodoApplication(Adw.Application):
    def __init__(self):
        super().__init__(application_id="com.programmer.TodoApp", flags=Gio.ApplicationFlags.FLAGS_NONE)

    def do_startup(self):
        Adw.Application.do_startup(self)
        
        # Register the global bg provider once at display level
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            _app_bg_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1,
        )
        
        # Named color CSS providers
        color_provider = Gtk.CssProvider()
        color_provider.load_from_data(b"""
            row.task-bg-Blue   { background-color: alpha(@blue_3,   0.15); border-left: 4px solid @blue_3; }
            row.task-bg-Green  { background-color: alpha(@green_3,  0.15); border-left: 4px solid @green_3; }
            row.task-bg-Red    { background-color: alpha(@red_3,    0.15); border-left: 4px solid @red_3; }
            row.task-bg-Yellow { background-color: alpha(@yellow_3, 0.15); border-left: 4px solid @yellow_3; }
            row.task-bg-Purple { background-color: alpha(@purple_3, 0.15); border-left: 4px solid @purple_3; }
        """)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            color_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    def do_activate(self):
        database.init_db()
        win = self.props.active_window
        if not win:
            win = MainWindow(application=self)
        win.present()
        
        # V3 Desktop Notifications Framework
        today = datetime.date.today()
        tasks = database.get_tasks_for_date(today)
        n_high = sum(1 for t in tasks if t['priority'] == 'High')
        if n_high > 0:
            notification = Gio.Notification.new("Elite To-Do: Priority Pipeline")
            notification.set_body(f"You have {n_high} High Priority tasks waiting in your queue today. Time to execute.")
            self.send_notification("high-priority-alert", notification)

if __name__ == "__main__":
    app = TodoApplication()
    app.run(sys.argv)