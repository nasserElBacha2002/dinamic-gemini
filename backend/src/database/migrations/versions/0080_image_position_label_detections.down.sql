/*
  0080_image_position_label_detections.down.sql

  Manual rollback for 0080 (not executed by the UP-only migration runner).
*/

IF OBJECT_ID(N'dbo.image_position_label_detections', N'U') IS NOT NULL
BEGIN
    DROP TABLE dbo.image_position_label_detections;
END
GO
