from sqlalchemy import create_engine, text, bindparam

class SQLEngine:
    def __init__(self, connection_str):
        # Enable fast_executemany for bulk inserts
        self.engine = create_engine(connection_str, fast_executemany=True)

    def prepare_staging_table(self, days=300):
        """Drop and recreate staging table for the last `days` days."""
        with self.engine.begin() as conn:
            conn.execute(text(f"""
                IF OBJECT_ID('dbo.APP_F_SPA_FormData_Master_Staging', 'U') IS NOT NULL
                    DROP TABLE dbo.APP_F_SPA_FormData_Master_Staging;

                SELECT
                    [RowId]
                    ,[UID]
                    ,[Project]
                    ,[Project_UID]
                    ,[Facility]
                    ,[Facility_UID]
                    ,[Facility_Area]
                    ,[Facility_Area_UID]
                    ,[Work_Process]
                    ,[Work_Process_UID]
                    ,[Submission_Date]
                    ,[Full_Name]
                    ,[Company_Name]
                    ,[Shift]
                    ,[Hazard_Description]
                    ,[Safe]
                    ,[Unsafe]
                    ,[Act_Behaviour]
                    ,[Condition]
                    ,[Action_Taken]
                    ,[Unsafe_Condition_Corrected]
                    ,[Risk_Level]
                    ,[Upload_By]
                    ,[Upload_By_Email]
                    ,[Upload_By_Id]
                    ,[User_Type]
                    ,[Source]
                    ,[Source_Ref]
                    ,[iName]
                    ,[iCompany_Name]
                    ,[iCrew_Category]
                    ,[Match_Score]
                    ,[Match_ts]
                    ,[Match_Status]
                    ,[Match_Remarks]
                    ,[Hazard_Description_Language]
                    ,[Action_Taken_Language]
                    ,[iHazard_Description]
                    ,[iAction_Taken]
                    ,[Translation_Status]
                    ,[Translation_ts]
                    ,[Translation_Remarks]
                    ,[Activity_Processed_Status]
                    ,[Activity_Process_ts]
                    ,[App_Version]
                    ,[IP_Address]
                    ,[Flag]
                    ,[Remarks]
                    ,[Created]
                    ,[Modified]
                    ,[Created_By_Id]
                    ,[Created_By_Name]
                    ,[Created_By_Email]
                    ,[Modified_By_Id]
                    ,[Modified_By_Name]
                    ,[Modified_By_Email]
                    ,[Current_Owner]
                    ,[CoW]
                    ,[CoM]
                    ,CAST(NULL AS NVARCHAR(255)) AS Classification
                    ,CAST(NULL AS NVARCHAR(MAX)) AS Justification
                INTO dbo.APP_F_SPA_FormData_Master_Staging
                FROM dbo.FormData_Master
                WHERE Submission_Date >= DATEADD(DAY, -{days}, CAST(GETDATE() AS DATE)) AND Facility = 'Aberdeen Facility 4';
            """))

    def get_pending_observations(self, limit=60000):
        """Fetch unclassified observations."""
        with self.engine.connect() as conn:
            query = text("""
                SELECT TOP(:limit) RowId, iHazard_Description
                FROM APP_F_SPA_FormData_Master_Staging
                WHERE Classification IS NULL
            """)
            result = conn.execute(query, {"limit": limit})
            return [{"RowId": row.RowId, "iHazard_Description": row.iHazard_Description} for row in result.fetchall()]

    def update_classification_batch(self, rows):
        if not rows:
            return
        with self.engine.begin() as conn:
            query = text("""
                UPDATE APP_F_SPA_FormData_Master_Staging
                SET Classification = :Classification, Justification = :Justification
                WHERE RowId = :RowId
            """)
            conn.execute(query, rows)


    def insert_classified_data_rows(self, row_ids):
        """Insert classified rows from staging into the final table."""
        if not row_ids:
            return

        with self.engine.begin() as conn:
            query = text("""
                INSERT INTO APP_F_SPA_FormData_Master (
                    UID, Project, Project_UID, Facility, Facility_UID, Facility_Area, Facility_Area_UID, Work_Process, Work_Process_UID, 
                    Submission_Date, Full_Name, Company_Name, Shift, Hazard_Description, Safe, Unsafe, Act_Behaviour, Condition, Action_Taken,
                    Unsafe_Condition_Corrected, Risk_Level, Upload_By, Upload_By_Email, Upload_By_Id, User_Type, Source, Source_Ref,
                    iName, iCompany_Name, iCrew_Category, Match_Score, Match_ts, Match_Status, Match_Remarks, Hazard_Description_Language,
                    Action_Taken_Language, iHazard_Description, iAction_Taken, Translation_Status, Translation_ts, Translation_Remarks,
                    Activity_Processed_Status, Activity_Process_ts, App_Version, IP_Address, Flag, Remarks, Created, Modified,
                    Created_By_Id, Created_By_Name, Created_By_Email, Modified_By_Id, Modified_By_Name, Modified_By_Email, Current_Owner,
                    CoW, CoM, Classification, Justification
                )
                SELECT 
                    UID, Project, Project_UID, Facility, Facility_UID, Facility_Area, Facility_Area_UID, Work_Process, Work_Process_UID, 
                    Submission_Date, Full_Name, Company_Name, Shift, Hazard_Description, Safe, Unsafe, Act_Behaviour, Condition, Action_Taken,
                    Unsafe_Condition_Corrected, Risk_Level, Upload_By, Upload_By_Email, Upload_By_Id, User_Type, Source, Source_Ref,
                    iName, iCompany_Name, iCrew_Category, Match_Score, Match_ts, Match_Status, Match_Remarks, Hazard_Description_Language,
                    Action_Taken_Language, iHazard_Description, iAction_Taken, Translation_Status, Translation_ts, Translation_Remarks,
                    Activity_Processed_Status, Activity_Process_ts, App_Version, IP_Address, Flag, Remarks, Created, Modified,
                    Created_By_Id, Created_By_Name, Created_By_Email, Modified_By_Id, Modified_By_Name, Modified_By_Email, Current_Owner,
                    CoW, CoM, Classification, Justification
                FROM APP_F_SPA_FormData_Master_Staging
                WHERE RowId IN :row_ids
            """).bindparams(bindparam("row_ids", expanding=True))
            conn.execute(query, {"row_ids": row_ids})

    def commit(self):
        """Placeholder (SQLAlchemy handles commits automatically with begin)."""
        pass

    def close(self):
        """Placeholder for engine cleanup if needed."""
        pass
