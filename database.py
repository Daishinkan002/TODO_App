import sqlite3
import datetime
import calendar
from pathlib import Path
import os

DB_DIR = Path(os.path.expanduser('~')) / '.local' / 'share' / 'python_todo_app'
DB_PATH = DB_DIR / 'todos.db'

def get_connection():
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    # Task Templates
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS TaskTemplates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            category TEXT DEFAULT 'Personal',
            recurrence_type TEXT NOT NULL,
            recurrence_value TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Task Instances
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS TaskInstances (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            category TEXT DEFAULT 'Personal',
            template_id INTEGER,
            due_date DATE NOT NULL,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(template_id) REFERENCES TaskTemplates(id)
        )
    ''')
    
    # V2 Migrations
    try:
        cursor.execute("ALTER TABLE TaskTemplates ADD COLUMN priority TEXT DEFAULT 'Normal'")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE TaskInstances ADD COLUMN priority TEXT DEFAULT 'Normal'")
    except sqlite3.OperationalError:
        pass
        
    cursor.execute('''
        CREATE TRIGGER IF NOT EXISTS update_templates_trigger
        AFTER UPDATE ON TaskTemplates
        BEGIN
            UPDATE TaskTemplates SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
        END;
    ''')
    cursor.execute('''
        CREATE TRIGGER IF NOT EXISTS update_instances_trigger
        AFTER UPDATE ON TaskInstances
        BEGIN
            UPDATE TaskInstances SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
        END;
    ''')
    
    conn.commit()
    conn.close()

def add_task(title, category='Personal', due_date=None, recurrence_type='None', priority='Normal'):
    """Add a new task, supporting recurrences."""
    conn = get_connection()
    cursor = conn.cursor()
    if not due_date:
        due_date = datetime.date.today().isoformat()
    
    template_id = None
    if recurrence_type and recurrence_type.lower() != 'none':
        cursor.execute('''
            INSERT INTO TaskTemplates (title, category, priority, recurrence_type)
            VALUES (?, ?, ?, ?)
        ''', (title, category, priority, recurrence_type))
        template_id = cursor.lastrowid
    
    cursor.execute('''
        INSERT INTO TaskInstances (title, category, priority, template_id, due_date)
        VALUES (?, ?, ?, ?, ?)
    ''', (title, category, priority, template_id, due_date))
    
    conn.commit()
    conn.close()

def get_tasks_for_date(target_date):
    """Get tasks pending for a specific date (e.g., today)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, title, category, priority, template_id, due_date, status,
               datetime(created_at, 'localtime') as created_at,
               datetime(updated_at, 'localtime') as updated_at
        FROM TaskInstances 
        WHERE due_date = ? AND status = 'pending'
        ORDER BY 
            CASE priority WHEN 'High' THEN 1 WHEN 'Normal' THEN 2 WHEN 'Low' THEN 3 ELSE 4 END ASC, 
            created_at DESC
    ''', (target_date.isoformat(),))
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_missed_tasks(today_date):
    """Get tasks whose due dates are strictly before today and are still pending."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, title, category, priority, template_id, due_date, status,
               datetime(created_at, 'localtime') as created_at,
               datetime(updated_at, 'localtime') as updated_at
        FROM TaskInstances 
        WHERE due_date < ? AND status = 'pending'
        ORDER BY 
            CASE priority WHEN 'High' THEN 1 WHEN 'Normal' THEN 2 WHEN 'Low' THEN 3 ELSE 4 END ASC,
            due_date ASC
    ''', (today_date.isoformat(),))
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_history_tasks():
    """Get tasks that have been marked as completed or missed."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, title, category, priority, template_id, due_date, status,
               datetime(created_at, 'localtime') as created_at,
               datetime(updated_at, 'localtime') as updated_at
        FROM TaskInstances 
        WHERE status IN ('completed', 'missed')
        ORDER BY updated_at DESC
        LIMIT 100
    ''')
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_templates():
    """Get all recurring task templates."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, title, category, priority, recurrence_type,
               datetime(created_at, 'localtime') as created_at
        FROM TaskTemplates
        ORDER BY category ASC, title ASC
    ''')
    rows = cursor.fetchall()
    conn.close()
    return rows

def search_tasks(query):
    """Search tasks across history and pending."""
    conn = get_connection()
    cursor = conn.cursor()
    like_query = f"%{query}%"
    cursor.execute('''
        SELECT id, title, category, priority, template_id, due_date, status,
               datetime(created_at, 'localtime') as created_at,
               datetime(updated_at, 'localtime') as updated_at
        FROM TaskInstances 
        WHERE title LIKE ? OR category LIKE ?
        ORDER BY updated_at DESC
        LIMIT 50
    ''', (like_query, like_query))
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_analytics():
    """Returns analytics for completed, missed, and pending tasks."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Completed this week (last 7 days)
    seven_days_ago = (datetime.date.today() - datetime.timedelta(days=7)).isoformat()
    cursor.execute("SELECT COUNT(*) FROM TaskInstances WHERE status = 'completed' AND updated_at >= ?", (seven_days_ago,))
    completed_week = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM TaskInstances WHERE status = 'missed' AND updated_at >= ?", (seven_days_ago,))
    missed_week = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM TaskInstances WHERE status = 'pending'")
    pending_all = cursor.fetchone()[0]
    
    conn.close()
    return {
        'completed_week': completed_week,
        'missed_week': missed_week,
        'pending_all': pending_all,
    }

def delete_template(template_id):
    """Delete a recurring template and any pending instances."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM TaskTemplates WHERE id = ?', (template_id,))
    cursor.execute("DELETE FROM TaskInstances WHERE template_id = ? AND status = 'pending'", (template_id,))
    conn.commit()
    conn.close()

def update_task_status(task_id, status):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE TaskInstances 
        SET status = ? 
        WHERE id = ?
    ''', (status, task_id))
    conn.commit()
    
    # Check if we need to auto-generate the next recurring instance
    if status in ('completed', 'missed', 'skipped'):
        cursor.execute('SELECT template_id, due_date FROM TaskInstances WHERE id = ?', (task_id,))
        row = cursor.fetchone()
        if row and row['template_id']:
            template_id = row['template_id']
            cursor.execute('SELECT title, category, priority, recurrence_type FROM TaskTemplates WHERE id = ?', (template_id,))
            template = cursor.fetchone()
            if template:
                old_date = datetime.date.fromisoformat(row['due_date'])
                rtype = template['recurrence_type'].lower()
                next_date = None
                
                if rtype == 'daily':
                    next_date = old_date + datetime.timedelta(days=1)
                elif rtype == 'weekly':
                    next_date = old_date + datetime.timedelta(days=7)
                elif rtype == 'monthly':
                    month = old_date.month % 12 + 1
                    year = old_date.year + (old_date.month // 12)
                    max_day = calendar.monthrange(year, month)[1]
                    next_date = old_date.replace(year=year, month=month, day=min(old_date.day, max_day))
                
                if next_date:
                    # Avoid duplicate pending tasks for the same template
                    cursor.execute("SELECT id FROM TaskInstances WHERE template_id = ? AND status = 'pending'", (template_id,))
                    if not cursor.fetchone():
                        cursor.execute('''
                            INSERT INTO TaskInstances (title, category, priority, template_id, due_date)
                            VALUES (?, ?, ?, ?, ?)
                        ''', (template['title'], template['category'], template['priority'], template_id, next_date.isoformat()))
                        conn.commit()

    conn.close()

def delete_task(task_id):
    """Hard delete a task instance natively."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM TaskInstances WHERE id = ?', (task_id,))
    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print("Database initialized.")
