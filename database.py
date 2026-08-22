import sqlite3

# ==========================================
# DATABASE: SQLite Setup
# ==========================================

DATABASE_PATH = "scheduling.db"

def get_connection():
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def get_db():
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()

def init_db():
    # Create or open the scheduling database and create its tables.
    conn = sqlite3.connect(DATABASE_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS participants (
            id INTEGER PRIMARY KEY,
            username TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            bio TEXT DEFAULT NULL,
            timezone TEXT NOT NULL,
            is_hidden INTEGER NOT NULL DEFAULT 0,
            is_admin INTEGER NOT NULL DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            deleted_at TEXT DEFAULT NULL,

            CHECK (is_hidden IN (0, 1)),
            CHECK (is_admin IN (0, 1))
        );

        CREATE TABLE IF NOT EXISTS friends (
            id INTEGER PRIMARY KEY,
            requester_id INTEGER NOT NULL,
            recipient_id INTEGER NOT NULL,
            pending INTEGER NOT NULL DEFAULT 1,

            FOREIGN KEY (requester_id) REFERENCES participants(id) ON DELETE CASCADE,
            FOREIGN KEY (recipient_id) REFERENCES participants(id) ON DELETE CASCADE,

            CHECK (requester_id != recipient_id),
            CHECK (pending IN (0, 1))
        );

        CREATE UNIQUE INDEX IF NOT EXISTS unique_friend_pair
        ON friends (
            MIN(requester_id, recipient_id),
            MAX(requester_id, recipient_id)
        );

        CREATE TABLE IF NOT EXISTS groups (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            owner_id INTEGER DEFAULT NULL,
            invite_only INTEGER NOT NULL DEFAULT 0,
            is_hidden INTEGER NOT NULL DEFAULT 0,
            members_can_invite INTEGER NOT NULL DEFAULT 0,
            archived_at TEXT DEFAULT NULL,
            deleted_at TEXT DEFAULT NULL,
            deleted_by_owner_deletion INTEGER NOT NULL DEFAULT 0,

            FOREIGN KEY (owner_id) REFERENCES participants(id),

            CHECK (invite_only IN (0, 1)),
            CHECK (is_hidden IN (0, 1)),
            CHECK (is_hidden = 0 OR invite_only = 1),
            CHECK (members_can_invite IN (0, 1)),
            CHECK (deleted_by_owner_deletion IN (0, 1))
        );

        CREATE TABLE IF NOT EXISTS group_invite_links (
            id INTEGER PRIMARY KEY,
            group_id INTEGER NOT NULL,
            invite_token TEXT UNIQUE NOT NULL,
            created_by INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            expires_at TEXT,
            max_uses INTEGER,
            uses INTEGER NOT NULL DEFAULT 0,

            FOREIGN KEY (group_id)
                REFERENCES groups(id)
                ON DELETE CASCADE,

            FOREIGN KEY (created_by)
                REFERENCES participants(id)
                ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS group_members (
            group_id INTEGER NOT NULL,
            participant_id INTEGER NOT NULL,
            invited_at TEXT DEFAULT NULL,
            invited_by INTEGER DEFAULT NULL,
            pending_invite INTEGER NOT NULL DEFAULT 0,
            joined_at TEXT DEFAULT NULL,
            left_at TEXT DEFAULT NULL,

            PRIMARY KEY (group_id, participant_id),

            FOREIGN KEY (group_id) 
                REFERENCES groups(id) 
                ON DELETE CASCADE, 
            FOREIGN KEY (participant_id) 
                REFERENCES participants(id) 
                ON DELETE CASCADE,
            FOREIGN KEY (invited_by) 
                REFERENCES participants(id) 
                ON DELETE SET NULL,

            CHECK (pending_invite IN (0, 1))
        );

        CREATE TABLE IF NOT EXISTS recurring_availability (
            id INTEGER PRIMARY KEY,
            group_id INTEGER,
            participant_id INTEGER NOT NULL,
            weekday INTEGER NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            end_day_offset INTEGER NOT NULL DEFAULT 0,
            is_available INTEGER NOT NULL,
            description TEXT,

            FOREIGN KEY (participant_id)
                REFERENCES participants(id) 
                ON DELETE CASCADE,
            FOREIGN KEY (group_id, participant_id)
                REFERENCES group_members(group_id, participant_id) 
                ON DELETE CASCADE,
            
            CHECK (weekday BETWEEN 0 AND 6),
            CHECK (end_day_offset BETWEEN 0 AND 6),
            CHECK (end_day_offset > 0
                OR end_time > start_time),
            CHECK (is_available BETWEEN 0 AND 2)
        );
        
        CREATE TABLE IF NOT EXISTS specific_availability (
            id INTEGER PRIMARY KEY,
            group_id INTEGER,
            participant_id INTEGER NOT NULL,
            start_datetime TEXT NOT NULL,
            end_datetime TEXT NOT NULL,
            is_available INTEGER NOT NULL,
            description TEXT,

            FOREIGN KEY (participant_id)
                REFERENCES participants(id) 
                ON DELETE CASCADE,
            FOREIGN KEY (group_id, participant_id)
                REFERENCES group_members(group_id, participant_id) 
                ON DELETE CASCADE,
            
            CHECK (is_available BETWEEN 0 AND 2),
            CHECK (end_datetime > start_datetime)
        );

        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY,
            group_id INTEGER NOT NULL,
            name TEXT,
            description TEXT,
            timezone TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (group_id)
                REFERENCES groups(id)
                ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS recurring_event_times (
            id INTEGER PRIMARY KEY,
            event_id INTEGER NOT NULL,

            weekday INTEGER NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            end_day_offset INTEGER NOT NULL DEFAULT 0,

            FOREIGN KEY (event_id)
                REFERENCES events(id)
                ON DELETE CASCADE,

            CHECK (weekday BETWEEN 0 AND 6),
            CHECK (end_day_offset BETWEEN 0 AND 6),
            CHECK (
                end_day_offset > 0
                OR end_time > start_time
            )
        );
        
        CREATE TABLE IF NOT EXISTS specific_event_times (
            id INTEGER PRIMARY KEY,
            event_id INTEGER NOT NULL,

            start_datetime TEXT NOT NULL,
            end_datetime TEXT NOT NULL,

            FOREIGN KEY (event_id)
                REFERENCES events(id)
                ON DELETE CASCADE,

            CHECK (end_datetime > start_datetime)
        );

        CREATE TABLE IF NOT EXISTS event_participants (
            event_id INTEGER NOT NULL,
            participant_id INTEGER NOT NULL,

            status TEXT NOT NULL DEFAULT 'pending',
            responded_at TEXT,

            PRIMARY KEY (event_id, participant_id),

            FOREIGN KEY (event_id)
                REFERENCES events(id)
                ON DELETE CASCADE,

            FOREIGN KEY (participant_id)
                REFERENCES participants(id)
                ON DELETE CASCADE,

            CHECK (
                status IN (
                    'pending',
                    'attending',
                    'declined'
                )
            )
        );

        CREATE TABLE IF NOT EXISTS banned_participants (
            id INTEGER PRIMARY KEY,
            group_id INTEGER NOT NULL,
            participant_id INTEGER NOT NULL,
            banned_by INTEGER DEFAULT NULL,
            banned_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            reason_for_ban TEXT DEFAULT NULL,
            unbanned_by INTEGER DEFAULT NULL,
            unbanned_at TEXT DEFAULT NULL,
            reason_for_unban TEXT DEFAULT NULL,

            FOREIGN KEY (group_id) REFERENCES groups(id) ON DELETE CASCADE,
            FOREIGN KEY (participant_id) REFERENCES participants(id) ON DELETE CASCADE,
            FOREIGN KEY (banned_by) REFERENCES participants(id) ON DELETE SET NULL,
            FOREIGN KEY (unbanned_by) REFERENCES participants(id) ON DELETE SET NULL
        );
                    
        CREATE UNIQUE INDEX IF NOT EXISTS one_active_ban_per_participant_per_group
            ON banned_participants(group_id, participant_id)
            WHERE unbanned_at IS NULL
        ;
        
    """) 
    
    # Store dates and times in ISO format: "2026-07-28T18:00:00", "2026-07-28T20:30:00"
    # Don't need storage tables for weekdays, as API can pass 0-6 when users select an option.
    # Don't need timezones table as there is a built-in library for this (zoneinfo)! It uses IANA names.

    # Storing local days and times in the "recurring_availability" table and converting during aggregation to account for Daylights Saving Time and mismatched days (evening chicago = morning elsewhere the next day).
    # Converting and storing full UTC datetime on input in the "specific_availability" table, since this use DateTime and can account for the issues "recurring_availability" cannot.
    # "specific_availability" also has an "is_available" value so participants can add days/times they are not available but would usually be otherwise (stored in the same table).

    # Will add password system later (participants). May want columns in table such as: password_hash, created_at, last_login, email (maybe), verified_at (maybe)

    conn.commit()
    conn.close()













        # CREATE TABLE IF NOT EXISTS audit_log (
        #     id INTEGER PRIMARY KEY,
        #     actor_id INTEGER,
        #     action TEXT NOT NULL,
        #     group_id INTEGER,
        #     participant_id INTEGER,
        #     details TEXT,
        #     created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

        #     FOREIGN KEY (actor_id)
        #         REFERENCES participants(id),

        #     FOREIGN KEY (group_id)
        #         REFERENCES groups(id),

        #     FOREIGN KEY (participant_id)
        #         REFERENCES participants(id)
        # );
