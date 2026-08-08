/* Run only after scenarios/SG3_drop_serial_unique_index.sql. */
USE AeroMRO_EDQSG;
GO
DECLARE @part_id int=(SELECT TOP(1) part_id FROM aero.part_master WHERE serialized_flag=1 ORDER BY part_id);
DECLARE @serial nvarchar(100)=(SELECT TOP(1) serial_number FROM aero.part_instance WHERE part_id=@part_id AND serial_number IS NOT NULL ORDER BY part_instance_id);
DECLARE @location int=(SELECT MIN(location_id) FROM aero.storage_location);
INSERT aero.part_instance(part_id,serial_number,batch_number,production_date,expiry_date,condition_status,current_location_id,on_hand_quantity,received_at,created_by,updated_by)
VALUES(@part_id,@serial,NULL,CONVERT(date,SYSUTCDATETIME()),NULL,'SERVICEABLE',@location,1,SYSUTCDATETIME(),N'propagation_workload',N'propagation_workload');
DECLARE @new_id bigint=SCOPE_IDENTITY();
INSERT aero.inventory_balance(part_instance_id,location_id,available_quantity,frozen_quantity,balance_updated_at,updated_by)
VALUES(@new_id,@location,1,0,SYSUTCDATETIME(),N'propagation_workload');
INSERT dq.benchmark_defect_label(scenario_id,defect_domain,indicator_id,defect_type,target_table,target_column,target_key,severity,causal_parent_scenario_id,expected_effect,random_seed)
VALUES(N'P-SG3-DQ4-DUP-SERIAL','COUPLING','DQ4',N'结构诱发重复序列号',N'aero.part_instance',N'serial_number',CONVERT(nvarchar(100),@new_id),1.0,N'SG3-DROP-SERIAL-UQ',N'验证SG3缺陷向DQ4传播',20260724);
GO
