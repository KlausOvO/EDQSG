USE AeroMRO_EDQSG;
GO
/* 在受控无外键场景中执行合法写入：所有part_id均经过父记录存在性校验。 */
DECLARE @part_id int=(SELECT TOP(1) part_id FROM aero.part_master ORDER BY part_id);
DECLARE @instance_id bigint=(SELECT TOP(1) part_instance_id FROM aero.part_instance WHERE part_id=@part_id ORDER BY part_instance_id);
DECLARE @location_id int=(SELECT TOP(1) location_id FROM aero.storage_location ORDER BY location_id);
DECLARE @receipt_id bigint=(SELECT TOP(1) receipt_id FROM aero.receipt ORDER BY receipt_id);
DECLARE @part_number nvarchar(80)=(SELECT part_number FROM aero.part_master WHERE part_id=@part_id);
DECLARE @part_name nvarchar(200)=(SELECT part_name FROM aero.part_master WHERE part_id=@part_id);

IF @part_id IS NULL OR @instance_id IS NULL OR @location_id IS NULL OR @receipt_id IS NULL
    THROW 51000, N'受控关系验证负载缺少基础数据。', 1;

INSERT aero.inventory_transaction(
    part_instance_id,part_id,transaction_type,source_location_id,target_location_id,
    quantity,transaction_time,reference_type,reference_id,operator_id,
    part_number_snapshot,part_name_snapshot,created_by
)
VALUES(
    @instance_id,@part_id,'ADJUST',NULL,@location_id,1,SYSUTCDATETIME(),
    'RECEIPT',@receipt_id,N'controlled-validator',@part_number,@part_name,N'controlled-validator'
);

/* 该负载是阴性对照，不写入缺陷标签。期望孤儿率保持为0。 */
GO
