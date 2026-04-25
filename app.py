import sys
import argparse
import datetime
import gi

# CLI Quick Add implementation
if len(sys.argv) > 1 and sys.argv[1] == 'add':
    parser = argparse.ArgumentParser(prog=f"python3 {sys.argv[0]} add")
    parser.add_argument("title", help="Title of the task")
    parser.add_argument("-c", "--category", default="Personal", help="Category (e.g., Work, Personal, Code)")
    parser.add_argument("-d", "--date", help="Due date (YYYY-MM-DD), defaults to today")
    parser.add_argument("-r", "--recurrence", default="None", choices=["None", "Daily", "Weekly", "Monthly"], help="Recurrence")
    parser.add_argument("-p", "--priority", default="Normal", choices=["High", "Normal", "Low"], help="Priority")
    args = parser.parse_args(sys.argv[2:])
    
    import database
    database.init_db()
    
    due_date = args.date if args.date else datetime.date.today().isoformat()
    database.add_task(args.title, args.category, due_date, recurrence_type=args.recurrence, priority=args.priority)
    print(f"Task '{args.title}' added successfully for {due_date} in category '{args.category}' | Priority '{args.priority}'.")
    sys.exit(0)

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gio, GLib

import database


class TaskRow(Adw.ActionRow):
    def __init__(self, task_data, window, reload_callback):
        super().__init__()
        self.task_id = task_data['id']
        self.title = task_data['title']
        self.category = task_data['category']
        self.priority = task_data['priority'] or 'Normal'
        self.due_date = task_data['due_date']
        self.created_at = task_data['created_at'][:16]
        self.updated_at = task_data['updated_at'][:16]
        self.window = window
        self.reload_callback = reload_callback
        
        # Priority Highlighting
        if self.priority == 'High':
            self.title = f"🔥 {self.title}"
            
        self.set_title(self.title)
        
        rec_text = " (Recurring)" if task_data['template_id'] else ""
        subtitle_text = f"{self.category}{rec_text} | {self.priority} Priority\nDue: {self.due_date} | Added: {self.created_at}\nUpdated: {self.updated_at}"
        self.set_subtitle(subtitle_text)
        self.set_subtitle_lines(3)
        
        self.set_icon_name("object-select-symbolic" if self.category == "Work" else "text-editor-symbolic" if self.category == "Code" else "user-info-symbolic")

        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        button_box.set_valign(Gtk.Align.CENTER)
        
        btn_yes = Gtk.Button(icon_name="emblem-ok-symbolic")
        btn_yes.add_css_class("suggested-action")
        btn_yes.add_css_class("circular")
        btn_yes.set_tooltip_text("Mark as Completed")
        btn_yes.connect("clicked", self.on_action, "completed")
        button_box.append(btn_yes)
        
        btn_no = Gtk.Button(icon_name="edit-delete-symbolic")
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


class HistoryRow(Adw.ActionRow):
    def __init__(self, task_data, window, reload_callback):
        super().__init__()
        self.task_id = task_data['id']
        self.title = task_data['title']
        self.category = task_data['category']
        self.priority = task_data['priority'] or 'Normal'
        self.due_date = task_data['due_date']
        self.status = task_data['status']
        self.updated_at = task_data['updated_at'][:16]
        self.created_at = task_data['created_at'][:16]
        self.window = window
        self.reload_callback = reload_callback
        
        if self.priority == 'High':
            self.title = f"🔥 {self.title}"
            
        self.set_title(self.title)
        
        status_text = "Completed" if self.status == 'completed' else "Missed"
        self.set_subtitle(f"{self.category} | {self.priority} Priority\nCreated: {self.created_at} | {status_text}: {self.updated_at}\nOriginally due: {self.due_date}")
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
        self.category = template_data['category']
        self.priority = template_data['priority'] or 'Normal'
        self.recurrence_type = template_data['recurrence_type']
        self.created_at = template_data['created_at'][:16]
        self.window = window
        self.reload_callback = reload_callback
        
        if self.priority == 'High':
            self.title = f"🔥 {self.title}"
            
        self.set_title(self.title)
        self.set_subtitle(f"{self.category} | {self.priority} | Recurs: {self.recurrence_type}\nCreated: {self.created_at}")
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
        
        self.add_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.add_box.set_halign(Gtk.Align.CENTER)
        
        self.task_entry = Gtk.Entry(placeholder_text="Add task for today...")
        self.task_entry.set_width_chars(30)
        self.task_entry.connect("activate", self.on_add_task)
        self.add_box.append(self.task_entry)
        
        self.category_model = Gtk.StringList.new(["Personal", "Work", "Code"])
        self.category_dropdown = Gtk.DropDown.new(self.category_model, None)
        self.category_dropdown.set_tooltip_text("Category")
        self.add_box.append(self.category_dropdown)
        
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
        self.clamp.set_maximum_size(650)
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
            
    def on_add_task(self, *args):
        title = self.task_entry.get_text().strip()
        if not title: return
        cat = ["Personal", "Work", "Code"][self.category_dropdown.get_selected()]
        pri = ["Normal", "High", "Low"][self.priority_dropdown.get_selected()]
        rec = ["None", "Daily", "Weekly", "Monthly"][self.recurrence_dropdown.get_selected()]
        
        database.add_task(title, category=cat, due_date=datetime.date.today().isoformat(), recurrence_type=rec, priority=pri)
        self.task_entry.set_text("")
        self.window.reload_all_views()
        self.window.toast_overlay.add_toast(Adw.Toast.new("Task added."))


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
        
        self.search_entry = Gtk.SearchEntry(placeholder_text="Search tasks...")
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
        # Trigger same as search
        self.on_search(self.search_entry)

    def on_search(self, entry):
        while (child := self.content_box.get_first_child()) is not None:
            self.content_box.remove(child)
            
        text = entry.get_text().strip()
        if not text:
            self.content_box.append(Adw.StatusPage(title="Search", description="Type above to find any task.", icon_name="system-search-symbolic"))
            return
            
        results = database.search_tasks(text)
        if not results:
            self.content_box.append(Adw.StatusPage(title="No Match", description="No tasks found for your query.", icon_name="edit-find-symbolic"))
        else:
            group = Adw.PreferencesGroup()
            for row in results:
                # Based on status, use TaskRow or HistoryRow
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
        self.set_title("To-Do")
        self.set_default_size(700, 800)
        
        self.toast_overlay = Adw.ToastOverlay()
        self.set_content(self.toast_overlay)

        self.main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.toast_overlay.set_child(self.main_box)
        
        self.view_stack = Adw.ViewStack()
        
        # HeaderBar with ViewSwitcher
        self.header = Adw.HeaderBar()
        self.view_switcher = Adw.ViewSwitcherTitle()
        self.view_switcher.set_stack(self.view_stack)
        self.header.set_title_widget(self.view_switcher)
        self.main_box.append(self.header)
        
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

    def do_activate(self):
        database.init_db()
        win = self.props.active_window
        if not win:
            win = MainWindow(application=self)
        win.present()

if __name__ == "__main__":
    app = TodoApplication()
    app.run(sys.argv)