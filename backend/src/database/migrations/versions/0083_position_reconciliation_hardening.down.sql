IF OBJECT_ID(N'dbo.CK_ppa_unassigned_position_null', N'C') IS NOT NULL
    ALTER TABLE dbo.product_position_assignments DROP CONSTRAINT CK_ppa_unassigned_position_null;
GO
IF OBJECT_ID(N'dbo.CK_ppa_automatic_evidence', N'C') IS NOT NULL
    ALTER TABLE dbo.product_position_assignments DROP CONSTRAINT CK_ppa_automatic_evidence;
GO
IF OBJECT_ID(N'dbo.CK_ppa_assignment_source', N'C') IS NOT NULL
    ALTER TABLE dbo.product_position_assignments DROP CONSTRAINT CK_ppa_assignment_source;
GO
IF OBJECT_ID(N'dbo.CK_ppa_assignment_status', N'C') IS NOT NULL
    ALTER TABLE dbo.product_position_assignments DROP CONSTRAINT CK_ppa_assignment_status;
GO
