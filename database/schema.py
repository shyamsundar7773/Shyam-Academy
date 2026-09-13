import sqlite3


def initialize_database(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS modules (
            module_id INTEGER PRIMARY KEY AUTOINCREMENT,
            module_name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            owner_user_id TEXT NOT NULL DEFAULT 'local-dev-user',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS sessions (
            session_id INTEGER PRIMARY KEY AUTOINCREMENT,
            module_id INTEGER NOT NULL,
            day_number INTEGER NOT NULL,
            session_date TEXT NOT NULL,
            category TEXT NOT NULL,
            topic TEXT NOT NULL,
            scheduled_time TEXT NOT NULL,
            prompt TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'Scheduled',
            owner_user_id TEXT NOT NULL DEFAULT 'local-dev-user',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (module_id) REFERENCES modules(module_id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_sessions_module_day
            ON sessions(module_id, day_number, session_date);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_modules_owner_name
            ON modules(owner_user_id, module_name);

        CREATE TABLE IF NOT EXISTS user_appearance (
            user_id TEXT PRIMARY KEY,
            background TEXT NOT NULL DEFAULT 'paper',
            theme TEXT NOT NULL DEFAULT 'light',
            asset_path TEXT,
            asset_mime TEXT
        );

        CREATE TABLE IF NOT EXISTS user_bootstrap (
            user_id TEXT PRIMARY KEY,
            initialized_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS classroom_conversations (
            conversation_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            classroom_id TEXT NOT NULL,
            title TEXT NOT NULL,
            history_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(user_id, classroom_id)
        );
        CREATE INDEX IF NOT EXISTS idx_classroom_user
            ON classroom_conversations(user_id, updated_at);

        CREATE TABLE IF NOT EXISTS doubt_notes (
            doubt_note_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            classroom_id TEXT NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            saved_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_doubt_notes_user
            ON doubt_notes(user_id, saved_at);

        """
    )
    appearance_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(user_appearance)").fetchall()
    }
    if "theme" not in appearance_columns:
        connection.execute(
            "ALTER TABLE user_appearance ADD COLUMN theme TEXT NOT NULL DEFAULT 'light'"
        )
        connection.commit()
    session_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(sessions)").fetchall()
    }
    if "scheduled_end_time" not in session_columns:
        connection.execute(
            "ALTER TABLE sessions ADD COLUMN scheduled_end_time TEXT NOT NULL DEFAULT ''"
        )
        connection.commit()
    note_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(learning_notes)").fetchall()
    }
    test_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(tests)").fetchall()
    }
    if test_columns and "context_id" not in test_columns:
        connection.execute(
            "ALTER TABLE tests ADD COLUMN context_id TEXT NOT NULL DEFAULT ''"
        )
        connection.commit()
    interview_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(interview_sessions)").fetchall()
    }
    if interview_columns and "context_id" not in interview_columns:
        connection.execute(
            "ALTER TABLE interview_sessions ADD COLUMN context_id TEXT NOT NULL DEFAULT ''"
        )
        connection.commit()
    if note_columns and "title" not in note_columns:
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.executescript(
            """
            ALTER TABLE learning_notes RENAME TO learning_notes_legacy;
            CREATE TABLE learning_notes (
                note_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                module_id INTEGER NOT NULL,
                session_id INTEGER,
                category TEXT NOT NULL,
                topic TEXT NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                learning_number INTEGER NOT NULL,
                saved_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'AI classroom',
                context_id TEXT NOT NULL DEFAULT '',
                FOREIGN KEY (module_id) REFERENCES modules(module_id) ON DELETE CASCADE,
                FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE SET NULL
            );
            INSERT INTO learning_notes
                (note_id, user_id, module_id, session_id, category, topic, title,
                 content, learning_number, saved_at, created_at, updated_at, source)
            SELECT note_id, user_id, module_id, session_id, category, topic,
                   topic || ' — Learning ' || note_id, content, note_id,
                   saved_at, saved_at, saved_at, 'AI classroom'
            FROM learning_notes_legacy;
            DROP TABLE learning_notes_legacy;
            """
        )
        connection.execute("PRAGMA foreign_keys = ON")
    else:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS learning_notes (
                note_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                module_id INTEGER NOT NULL,
                session_id INTEGER,
                category TEXT NOT NULL,
                topic TEXT NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                learning_number INTEGER NOT NULL,
                saved_at TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'AI classroom',
                context_id TEXT NOT NULL DEFAULT '',
                FOREIGN KEY (module_id) REFERENCES modules(module_id) ON DELETE CASCADE,
                FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE SET NULL
            );
            """
        )
        note_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(learning_notes)").fetchall()
        }
        if "context_id" not in note_columns:
            connection.execute(
                "ALTER TABLE learning_notes ADD COLUMN context_id TEXT NOT NULL DEFAULT ''"
            )
            connection.commit()
        if "created_at" not in note_columns:
            connection.execute(
                "ALTER TABLE learning_notes ADD COLUMN created_at TEXT NOT NULL DEFAULT ''"
            )
            connection.execute(
                "UPDATE learning_notes SET created_at = saved_at WHERE created_at = ''"
            )
            connection.commit()
    connection.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_learning_notes_scope
            ON learning_notes(user_id, module_id, category, topic, saved_at);

        CREATE TABLE IF NOT EXISTS attendance (
            attendance_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            module_id INTEGER NOT NULL,
            session_id INTEGER NOT NULL,
            evidence_note_id INTEGER,
            evidence_source TEXT,
            status TEXT NOT NULL CHECK(status IN ('Attended', 'Missed')),
            attended_at TEXT,
            scheduled_date TEXT NOT NULL,
            scheduled_time TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(user_id, session_id),
            FOREIGN KEY (module_id) REFERENCES modules(module_id) ON DELETE CASCADE,
            FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE,
            FOREIGN KEY (evidence_note_id) REFERENCES learning_notes(note_id)
                ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS idx_attendance_module
            ON attendance(user_id, module_id, session_id);

        CREATE TABLE IF NOT EXISTS tests (
            test_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            module_id INTEGER,
            session_id INTEGER,
            context_id TEXT NOT NULL DEFAULT '',
            title TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            category TEXT NOT NULL,
            topic TEXT NOT NULL,
            difficulty TEXT NOT NULL,
            total_questions INTEGER NOT NULL,
            duration_minutes INTEGER,
            status TEXT NOT NULL DEFAULT 'Ready',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (module_id) REFERENCES modules(module_id) ON DELETE SET NULL,
            FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE SET NULL
        );
        CREATE TABLE IF NOT EXISTS test_questions (
            question_id TEXT PRIMARY KEY,
            test_id TEXT NOT NULL,
            order_index INTEGER NOT NULL,
            question_type TEXT NOT NULL,
            question_text TEXT NOT NULL,
            options_json TEXT NOT NULL DEFAULT '[]',
            correct_answer_json TEXT NOT NULL,
            explanation TEXT NOT NULL,
            points REAL NOT NULL,
            weak_area TEXT NOT NULL DEFAULT '',
            FOREIGN KEY (test_id) REFERENCES tests(test_id) ON DELETE CASCADE,
            UNIQUE(test_id, order_index)
        );
        CREATE TABLE IF NOT EXISTS test_attempts (
            attempt_id TEXT PRIMARY KEY,
            test_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            started_at TEXT NOT NULL,
            submitted_at TEXT,
            status TEXT NOT NULL DEFAULT 'In Progress',
            score REAL,
            percentage REAL,
            evaluation_summary TEXT NOT NULL DEFAULT '',
            weak_areas_json TEXT NOT NULL DEFAULT '[]',
            FOREIGN KEY (test_id) REFERENCES tests(test_id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS test_answers (
            answer_id TEXT PRIMARY KEY,
            attempt_id TEXT NOT NULL,
            question_id TEXT NOT NULL,
            answer_json TEXT NOT NULL,
            is_correct INTEGER,
            points_awarded REAL NOT NULL DEFAULT 0,
            feedback TEXT NOT NULL DEFAULT '',
            explanation TEXT NOT NULL DEFAULT '',
            FOREIGN KEY (attempt_id) REFERENCES test_attempts(attempt_id) ON DELETE CASCADE,
            FOREIGN KEY (question_id) REFERENCES test_questions(question_id) ON DELETE CASCADE,
            UNIQUE(attempt_id, question_id)
        );
        CREATE INDEX IF NOT EXISTS idx_tests_user ON tests(user_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_attempts_user ON test_attempts(user_id, started_at);

        CREATE TABLE IF NOT EXISTS interview_sessions (
            interview_session_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            module_id INTEGER,
            session_id INTEGER,
            context_id TEXT NOT NULL DEFAULT '',
            title TEXT NOT NULL,
            mode TEXT NOT NULL,
            difficulty TEXT NOT NULL,
            topic TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'In Progress',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            completed_at TEXT,
            FOREIGN KEY (module_id) REFERENCES modules(module_id) ON DELETE SET NULL,
            FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE SET NULL
        );
        CREATE TABLE IF NOT EXISTS interview_questions (
            question_id TEXT PRIMARY KEY,
            interview_session_id TEXT NOT NULL,
            order_index INTEGER NOT NULL,
            question_text TEXT NOT NULL,
            question_type TEXT NOT NULL,
            topic TEXT NOT NULL,
            expected_points_json TEXT NOT NULL DEFAULT '[]',
            FOREIGN KEY (interview_session_id) REFERENCES interview_sessions(interview_session_id) ON DELETE CASCADE,
            UNIQUE(interview_session_id, order_index)
        );
        CREATE TABLE IF NOT EXISTS interview_answers (
            answer_id TEXT PRIMARY KEY,
            interview_session_id TEXT NOT NULL,
            question_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            answer TEXT NOT NULL,
            submitted_at TEXT NOT NULL,
            FOREIGN KEY (interview_session_id) REFERENCES interview_sessions(interview_session_id) ON DELETE CASCADE,
            FOREIGN KEY (question_id) REFERENCES interview_questions(question_id) ON DELETE CASCADE,
            UNIQUE(interview_session_id, question_id)
        );
        CREATE TABLE IF NOT EXISTS interview_evaluations (
            evaluation_id TEXT PRIMARY KEY,
            answer_id TEXT NOT NULL UNIQUE,
            score REAL NOT NULL,
            correctness REAL NOT NULL,
            relevance REAL NOT NULL,
            clarity REAL NOT NULL,
            technical_depth REAL NOT NULL,
            communication_quality REAL NOT NULL,
            strengths_json TEXT NOT NULL DEFAULT '[]',
            weaknesses_json TEXT NOT NULL DEFAULT '[]',
            missing_points_json TEXT NOT NULL DEFAULT '[]',
            corrections_json TEXT NOT NULL DEFAULT '[]',
            suggested_answer TEXT NOT NULL DEFAULT '',
            feedback TEXT NOT NULL,
            evaluated_at TEXT NOT NULL,
            FOREIGN KEY (answer_id) REFERENCES interview_answers(answer_id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_interview_user ON interview_sessions(user_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_interview_answers_user ON interview_answers(user_id, submitted_at);

        CREATE TABLE IF NOT EXISTS notifications (
            notification_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            type TEXT NOT NULL,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            session_id INTEGER,
            module_id INTEGER,
            scheduled_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT '',
            delivered_at TEXT,
            read_at TEXT,
            cancelled_at TEXT,
            status TEXT NOT NULL DEFAULT 'SCHEDULED',
            priority TEXT NOT NULL DEFAULT 'NORMAL',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            delivery_attempts INTEGER NOT NULL DEFAULT 0,
            last_error TEXT,
            FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE SET NULL,
            FOREIGN KEY (module_id) REFERENCES modules(module_id) ON DELETE SET NULL
        );
        DROP INDEX IF EXISTS uq_notification_identity;
        CREATE UNIQUE INDEX IF NOT EXISTS uq_notification_identity
            ON notifications(user_id, session_id, type, scheduled_at)
            WHERE status != 'CANCELLED';
        CREATE INDEX IF NOT EXISTS idx_notifications_due
            ON notifications(status, scheduled_at, cancelled_at);
        CREATE INDEX IF NOT EXISTS idx_notifications_user
            ON notifications(user_id, read_at, scheduled_at);

        CREATE TABLE IF NOT EXISTS notification_preferences (
            user_id TEXT PRIMARY KEY,
            notifications_enabled INTEGER NOT NULL DEFAULT 1,
            session_reminders INTEGER NOT NULL DEFAULT 1,
            session_start INTEGER NOT NULL DEFAULT 1,
            missed_session INTEGER NOT NULL DEFAULT 1,
            test_reminders INTEGER NOT NULL DEFAULT 1,
            interview_reminders INTEGER NOT NULL DEFAULT 1,
            mentor_recommendations INTEGER NOT NULL DEFAULT 1,
            desktop_enabled INTEGER NOT NULL DEFAULT 1,
            android_enabled INTEGER NOT NULL DEFAULT 1,
            quiet_start TEXT NOT NULL DEFAULT '23:00',
            quiet_end TEXT NOT NULL DEFAULT '07:00',
            reminder_offset_minutes INTEGER NOT NULL DEFAULT 5,
            timezone TEXT NOT NULL DEFAULT 'Asia/Kolkata',
            allow_urgent_quiet_hours INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS notification_devices (
            device_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            platform TEXT NOT NULL,
            push_token TEXT,
            app_version TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            PRIMARY KEY (device_id, user_id)
        );
        CREATE INDEX IF NOT EXISTS idx_notification_devices_user
            ON notification_devices(user_id, active);

        CREATE TABLE IF NOT EXISTS alarms (
            alarm_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            session_id INTEGER NOT NULL UNIQUE,
            module_id INTEGER,
            title TEXT NOT NULL,
            body TEXT NOT NULL DEFAULT '',
            scheduled_at TEXT NOT NULL,
            timezone TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'ACTIVE'
                CHECK(status IN ('ACTIVE', 'CANCELLED')),
            source TEXT NOT NULL DEFAULT 'timetable',
            recurrence_rule TEXT NOT NULL DEFAULT '',
            next_occurrence TEXT,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE,
            FOREIGN KEY (module_id) REFERENCES modules(module_id) ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS idx_alarms_user_status
            ON alarms(user_id, status, scheduled_at);

        CREATE TABLE IF NOT EXISTS mentor_conversations (
            conversation_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            title TEXT NOT NULL DEFAULT 'AI Mentor',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS mentor_messages (
            message_id TEXT PRIMARY KEY,
            conversation_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('user', 'mentor')),
            message TEXT NOT NULL,
            action_type TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (conversation_id) REFERENCES mentor_conversations(conversation_id)
                ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_mentor_conversations_user
            ON mentor_conversations(user_id, updated_at);
        CREATE INDEX IF NOT EXISTS idx_mentor_messages_conversation
            ON mentor_messages(conversation_id, created_at);

        CREATE TABLE IF NOT EXISTS routines (
            routine_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            category TEXT NOT NULL DEFAULT 'CUSTOM',
            frequency TEXT NOT NULL CHECK(frequency IN ('DAILY','WEEKLY','SELECTED_DAYS')),
            start_date TEXT NOT NULL,
            end_date TEXT,
            time_local TEXT NOT NULL,
            duration_minutes INTEGER NOT NULL CHECK(duration_minutes > 0),
            timezone TEXT NOT NULL,
            selected_days_json TEXT NOT NULL DEFAULT '[]',
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_routines_user ON routines(user_id, enabled, start_date);
        CREATE TABLE IF NOT EXISTS routine_occurrences (
            occurrence_id TEXT PRIMARY KEY,
            routine_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            occurrence_date TEXT NOT NULL,
            scheduled_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'UPCOMING'
                CHECK(status IN ('UPCOMING','DUE','COMPLETED','SKIPPED','MISSED','CANCELLED')),
            completed_at TEXT,
            skipped_at TEXT,
            note TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(routine_id, occurrence_date),
            FOREIGN KEY (routine_id) REFERENCES routines(routine_id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_routine_occurrences_user_date
            ON routine_occurrences(user_id, occurrence_date, status);
        CREATE TABLE IF NOT EXISTS routine_preferences (
            user_id TEXT PRIMARY KEY,
            enabled INTEGER NOT NULL DEFAULT 1,
            reminder_minutes INTEGER NOT NULL DEFAULT 10,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS routine_events (
            event_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            routine_id TEXT,
            occurrence_id TEXT,
            event_type TEXT NOT NULL,
            payload_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_routine_events_user
            ON routine_events(user_id, created_at);

        CREATE TABLE IF NOT EXISTS ai_tasks (
            task_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            task_type TEXT NOT NULL,
            agent_id TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            started_at TEXT,
            completed_at TEXT,
            input_summary TEXT NOT NULL DEFAULT '',
            output_summary TEXT NOT NULL DEFAULT '',
            context_json TEXT NOT NULL DEFAULT '{}',
            provider_reference TEXT NOT NULL DEFAULT '',
            action_references_json TEXT NOT NULL DEFAULT '[]',
            error_category TEXT,
            error_message TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_ai_tasks_user_created
            ON ai_tasks(user_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_ai_tasks_user_status
            ON ai_tasks(user_id, status);

        CREATE TABLE IF NOT EXISTS ai_action_proposals (
            proposal_id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            agent_id TEXT NOT NULL,
            action_type TEXT NOT NULL,
            target_reference TEXT NOT NULL DEFAULT '',
            summary TEXT NOT NULL,
            structured_payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'PENDING',
            approved_at TEXT,
            executed_at TEXT,
            error_category TEXT,
            error_message TEXT,
            UNIQUE(task_id, action_type, target_reference),
            FOREIGN KEY (task_id) REFERENCES ai_tasks(task_id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_ai_proposals_user_status
            ON ai_action_proposals(user_id, status, expires_at);

        CREATE TABLE IF NOT EXISTS ai_audit_log (
            audit_id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            agent_id TEXT NOT NULL,
            operation TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            result_status TEXT NOT NULL,
            proposal_id TEXT,
            error_category TEXT,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            FOREIGN KEY (task_id) REFERENCES ai_tasks(task_id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_ai_audit_user_time
            ON ai_audit_log(user_id, timestamp);

        CREATE TABLE IF NOT EXISTS ai_user_settings (
            user_id TEXT PRIMARY KEY,
            enabled INTEGER NOT NULL DEFAULT 1,
            preferred_provider TEXT NOT NULL DEFAULT '',
            preferred_model TEXT NOT NULL DEFAULT '',
            voice_input_provider TEXT NOT NULL DEFAULT 'not_configured',
            voice_output_provider TEXT NOT NULL DEFAULT 'not_configured',
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_ai_user_settings_enabled
            ON ai_user_settings(user_id, enabled);
        """
    )
    attendance_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(attendance)").fetchall()
    }
    if "evidence_note_id" not in attendance_columns:
        connection.execute(
            "ALTER TABLE attendance ADD COLUMN evidence_note_id INTEGER"
        )
        connection.commit()
    if "evidence_source" not in attendance_columns:
        connection.execute(
            "ALTER TABLE attendance ADD COLUMN evidence_source TEXT"
        )
        connection.commit()
    # Evidence links written by the former heuristic backfill are not proof
    # of a successful Save Notes action.
    connection.execute(
        "UPDATE attendance SET evidence_note_id=NULL "
        "WHERE evidence_source IS NULL"
    )
    connection.commit()
    alarm_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(alarms)").fetchall()
    }
    for column, definition in (
        ("recurrence_rule", "TEXT NOT NULL DEFAULT ''"),
        ("next_occurrence", "TEXT"),
        ("enabled", "INTEGER NOT NULL DEFAULT 1"),
    ):
        if column not in alarm_columns:
            connection.execute(f"ALTER TABLE alarms ADD COLUMN {column} {definition}")
    connection.commit()
    notification_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(notifications)").fetchall()
    }
    routine_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(routines)").fetchall()
    }
    if routine_columns and "category" not in routine_columns:
        connection.execute(
            "ALTER TABLE routines ADD COLUMN category TEXT NOT NULL DEFAULT 'CUSTOM'"
        )
        connection.commit()
    occurrence_schema = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='routine_occurrences'"
    ).fetchone()
    if occurrence_schema and "UPCOMING" not in (occurrence_schema["sql"] or ""):
        connection.execute("PRAGMA foreign_keys=OFF")
        connection.executescript(
            """
            ALTER TABLE routine_occurrences RENAME TO routine_occurrences_legacy;
            CREATE TABLE routine_occurrences (
                occurrence_id TEXT PRIMARY KEY,
                routine_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                occurrence_date TEXT NOT NULL,
                scheduled_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'UPCOMING'
                    CHECK(status IN ('UPCOMING','DUE','COMPLETED','MISSED','SKIPPED','CANCELLED')),
                completed_at TEXT,
                skipped_at TEXT,
                note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(routine_id, occurrence_date),
                FOREIGN KEY (routine_id) REFERENCES routines(routine_id) ON DELETE CASCADE
            );
            INSERT INTO routine_occurrences
                (occurrence_id,routine_id,user_id,occurrence_date,scheduled_at,status,
                 completed_at,skipped_at,note,created_at,updated_at)
            SELECT occurrence_id,routine_id,user_id,occurrence_date,scheduled_at,
                   CASE WHEN status='PENDING' THEN 'UPCOMING' ELSE status END,
                   completed_at,skipped_at,note,created_at,updated_at
            FROM routine_occurrences_legacy;
            DROP TABLE routine_occurrences_legacy;
            """
        )
        connection.execute("PRAGMA foreign_keys=ON")
        connection.commit()
    if "routine_occurrence_id" not in notification_columns:
        connection.execute(
            "ALTER TABLE notifications ADD COLUMN routine_occurrence_id TEXT"
        )
        connection.commit()
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_notifications_routine_occurrence "
        "ON notifications(user_id, routine_occurrence_id, type)"
    )
    connection.commit()
