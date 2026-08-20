from sqlalchemy import create_engine, text
import enquest_config as config


class EnquestSQLEngine:
    """Data access for EnQuest BBSS Hazard / Human Factors classification.

    Classifies dbo.FormData_Master in place (no staging table): the two AI_*
    columns live directly on the production table, and idempotent skip
    behaviour comes from checking those columns for NULL rather than from a
    staging-table rebuild.
    """

    def __init__(self, connection_str):
        # pool_pre_ping: each classification batch spends real time (potentially
        # several minutes) doing AI calls with the DB connection sitting
        # completely idle in the pool. Azure SQL's gateway (and often
        # intermediate firewalls) will silently drop a TCP connection idle
        # that long, and SQLAlchemy's pool doesn't notice by default -- it
        # just hands back the dead connection, which fails on first use
        # ("Communication link failure"). pre_ping adds a lightweight
        # liveness check before handing out a pooled connection and
        # transparently reconnects if it's gone stale.
        # pool_recycle: belt-and-suspenders -- proactively discard and replace
        # any connection older than 30 minutes, regardless of pre_ping.
        self.engine = create_engine(
            connection_str,
            fast_executemany=True,
            pool_pre_ping=True,
            pool_recycle=1800,
        )

    def ensure_schema(self):
        """Add the AI classification columns and review-log table if they
        don't already exist. Never touches the existing Hazard_Category (LSR)
        field or any other pre-existing column."""
        with self.engine.begin() as conn:
            conn.execute(text(f"""
                IF COL_LENGTH('{config.TABLE_NAME}', '{config.HAZARD_FIELD}') IS NULL
                    ALTER TABLE {config.TABLE_NAME} ADD {config.HAZARD_FIELD} NVARCHAR(64) NULL;

                IF COL_LENGTH('{config.TABLE_NAME}', '{config.HUMAN_FACTORS_FIELD}') IS NULL
                    ALTER TABLE {config.TABLE_NAME} ADD {config.HUMAN_FACTORS_FIELD} NVARCHAR(64) NULL;
            """))

            conn.execute(text(f"""
                IF OBJECT_ID('{config.REVIEW_LOG_TABLE_NAME}', 'U') IS NULL
                BEGIN
                    CREATE TABLE {config.REVIEW_LOG_TABLE_NAME} (
                        LogId INT IDENTITY(1,1) PRIMARY KEY,
                        RowId BIGINT NOT NULL,
                        Dimension NVARCHAR(32) NOT NULL,
                        Label NVARCHAR(64) NOT NULL,
                        Confidence NVARCHAR(16) NOT NULL,
                        Evidence NVARCHAR(MAX) NULL,
                        LoggedAt DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
                    );
                END
            """))

    def get_pending_observations(self, limit, force=False):
        """Fetch observations to classify. When force is False, only rows
        where both AI fields are still NULL are returned, so the daily
        webjob only ever sees newly submitted cards."""
        where_clause = "" if force else f"""
            WHERE {config.HAZARD_FIELD} IS NULL AND {config.HUMAN_FACTORS_FIELD} IS NULL AND Flag <> 'D'
        """
        with self.engine.connect() as conn:
            query = text(f"""
                SELECT TOP(:limit) RowId, Hazard_Description, Action_Taken
                FROM {config.TABLE_NAME}
                {where_clause}
                ORDER BY RowId
            """)
            result = conn.execute(query, {"limit": limit})
            return [
                {
                    "RowId": row.RowId,
                    "Hazard_Description": row.Hazard_Description or "",
                    "Action_Taken": row.Action_Taken or "",
                }
                for row in result.fetchall()
            ]

    def update_classification_batch(self, rows):
        """Write both AI fields for each row in a single UPDATE statement per
        row, so no row is ever left with only one dimension populated."""
        if not rows:
            return
        with self.engine.begin() as conn:
            query = text(f"""
                UPDATE {config.TABLE_NAME}
                SET {config.HAZARD_FIELD} = :HazardLabel,
                    {config.HUMAN_FACTORS_FIELD} = :HumanFactorsLabel
                WHERE RowId = :RowId
            """)
            conn.execute(query, rows)

    def insert_review_log_batch(self, rows):
        """Append-only log of classifications still Low confidence after
        exhausting the confidence-retry budget (see enquest_process_batch.py),
        for human review during the pilot. Medium/High confidence results
        never reach this table.

        Note: the Evidence column stays in the table schema (harmless,
        nullable) but is no longer populated -- generating a verbatim quote
        on every call was pure output-token cost for the ~95%+ of cards
        that never needed it, since confidence isn't known until after
        generation. Reviewers use RowId to look up the source text directly."""
        if not rows:
            return
        with self.engine.begin() as conn:
            query = text(f"""
                INSERT INTO {config.REVIEW_LOG_TABLE_NAME} (RowId, Dimension, Label, Confidence)
                VALUES (:RowId, :Dimension, :Label, :Confidence)
            """)
            conn.execute(query, rows)
