USE AeroMRO_EDQSG;
GO
SET NOCOUNT ON;
SET XACT_ABORT ON;
GO

/* Drop in reverse dependency order for repeatable laboratory builds. */
DROP TABLE IF EXISTS dq.quality_issue;
DROP TABLE IF EXISTS dq.relationship_control_registry;
DROP TABLE IF EXISTS dq.quality_run;
DROP TABLE IF EXISTS dq.quality_rule;
DROP TABLE IF EXISTS dq.benchmark_defect_label;
DROP TABLE IF EXISTS aero.scrap_record;
DROP TABLE IF EXISTS aero.repair_order;
DROP TABLE IF EXISTS aero.life_limit_control;
DROP TABLE IF EXISTS aero.usage_snapshot;
DROP TABLE IF EXISTS aero.install_remove_event;
DROP TABLE IF EXISTS aero.maintenance_work_order;
DROP TABLE IF EXISTS aero.inspection_record;
DROP TABLE IF EXISTS aero.certificate_document;
DROP TABLE IF EXISTS aero.receipt_line;
DROP TABLE IF EXISTS aero.receipt;
DROP TABLE IF EXISTS aero.purchase_order_line;
DROP TABLE IF EXISTS aero.purchase_order;
DROP TABLE IF EXISTS aero.inventory_transaction;
DROP TABLE IF EXISTS aero.inventory_balance;
DROP TABLE IF EXISTS aero.part_instance;
DROP TABLE IF EXISTS aero.storage_location;
DROP TABLE IF EXISTS aero.warehouse;
DROP TABLE IF EXISTS aero.part_alternative;
DROP TABLE IF EXISTS aero.part_applicability;
DROP TABLE IF EXISTS aero.part_master;
DROP TABLE IF EXISTS aero.supplier;
DROP TABLE IF EXISTS aero.aircraft;
DROP TABLE IF EXISTS aero.aircraft_type;
DROP TABLE IF EXISTS aero.ata_chapter;
DROP TABLE IF EXISTS aero.manufacturer;
GO

CREATE TABLE aero.manufacturer (
    manufacturer_id int IDENTITY(1,1) NOT NULL CONSTRAINT PK_manufacturer PRIMARY KEY,
    manufacturer_code nvarchar(30) NOT NULL CONSTRAINT UQ_manufacturer_code UNIQUE,
    manufacturer_name nvarchar(200) NOT NULL,
    country_code char(2) NOT NULL,
    active_flag bit NOT NULL CONSTRAINT DF_manufacturer_active DEFAULT (1),
    created_at datetime2(0) NOT NULL CONSTRAINT DF_manufacturer_created DEFAULT (SYSUTCDATETIME()),
    created_by nvarchar(80) NOT NULL CONSTRAINT DF_manufacturer_creator DEFAULT (SUSER_SNAME()),
    updated_at datetime2(0) NOT NULL CONSTRAINT DF_manufacturer_updated DEFAULT (SYSUTCDATETIME()),
    updated_by nvarchar(80) NOT NULL CONSTRAINT DF_manufacturer_updater DEFAULT (SUSER_SNAME()),
    row_version rowversion NOT NULL
);
GO

CREATE TABLE aero.ata_chapter (
    ata_code char(4) NOT NULL CONSTRAINT PK_ata_chapter PRIMARY KEY,
    chapter_name nvarchar(200) NOT NULL,
    parent_ata_code char(4) NULL,
    active_flag bit NOT NULL CONSTRAINT DF_ata_active DEFAULT (1),
    created_at datetime2(0) NOT NULL CONSTRAINT DF_ata_created DEFAULT (SYSUTCDATETIME()),
    created_by nvarchar(80) NOT NULL CONSTRAINT DF_ata_creator DEFAULT (SUSER_SNAME()),
    updated_at datetime2(0) NOT NULL CONSTRAINT DF_ata_updated DEFAULT (SYSUTCDATETIME()),
    updated_by nvarchar(80) NOT NULL CONSTRAINT DF_ata_updater DEFAULT (SUSER_SNAME()),
    CONSTRAINT FK_ata_parent FOREIGN KEY (parent_ata_code) REFERENCES aero.ata_chapter(ata_code)
);
GO

CREATE TABLE aero.aircraft_type (
    aircraft_type_id int IDENTITY(1,1) NOT NULL CONSTRAINT PK_aircraft_type PRIMARY KEY,
    type_code nvarchar(30) NOT NULL CONSTRAINT UQ_aircraft_type_code UNIQUE,
    manufacturer_id int NOT NULL,
    model_name nvarchar(100) NOT NULL,
    series_name nvarchar(100) NULL,
    active_flag bit NOT NULL CONSTRAINT DF_aircraft_type_active DEFAULT (1),
    created_at datetime2(0) NOT NULL CONSTRAINT DF_aircraft_type_created DEFAULT (SYSUTCDATETIME()),
    created_by nvarchar(80) NOT NULL CONSTRAINT DF_aircraft_type_creator DEFAULT (SUSER_SNAME()),
    updated_at datetime2(0) NOT NULL CONSTRAINT DF_aircraft_type_updated DEFAULT (SYSUTCDATETIME()),
    updated_by nvarchar(80) NOT NULL CONSTRAINT DF_aircraft_type_updater DEFAULT (SUSER_SNAME()),
    CONSTRAINT FK_aircraft_type_manufacturer FOREIGN KEY (manufacturer_id) REFERENCES aero.manufacturer(manufacturer_id)
);
GO

CREATE TABLE aero.aircraft (
    aircraft_id int IDENTITY(1,1) NOT NULL CONSTRAINT PK_aircraft PRIMARY KEY,
    registration_no nvarchar(20) NOT NULL CONSTRAINT UQ_aircraft_registration UNIQUE,
    aircraft_serial_no nvarchar(50) NOT NULL CONSTRAINT UQ_aircraft_serial UNIQUE,
    aircraft_type_id int NOT NULL,
    operator_code nvarchar(30) NOT NULL,
    aircraft_status varchar(20) NOT NULL,
    delivery_date date NULL,
    created_at datetime2(0) NOT NULL CONSTRAINT DF_aircraft_created DEFAULT (SYSUTCDATETIME()),
    created_by nvarchar(80) NOT NULL CONSTRAINT DF_aircraft_creator DEFAULT (SUSER_SNAME()),
    updated_at datetime2(0) NOT NULL CONSTRAINT DF_aircraft_updated DEFAULT (SYSUTCDATETIME()),
    updated_by nvarchar(80) NOT NULL CONSTRAINT DF_aircraft_updater DEFAULT (SUSER_SNAME()),
    CONSTRAINT FK_aircraft_type FOREIGN KEY (aircraft_type_id) REFERENCES aero.aircraft_type(aircraft_type_id),
    CONSTRAINT CK_aircraft_status CHECK (aircraft_status IN ('ACTIVE','STORED','MAINTENANCE','RETIRED'))
);
GO

CREATE TABLE aero.supplier (
    supplier_id int IDENTITY(1,1) NOT NULL CONSTRAINT PK_supplier PRIMARY KEY,
    supplier_code nvarchar(30) NOT NULL CONSTRAINT UQ_supplier_code UNIQUE,
    supplier_name nvarchar(200) NOT NULL,
    approval_no nvarchar(80) NOT NULL CONSTRAINT UQ_supplier_approval UNIQUE,
    approval_valid_to date NOT NULL,
    supplier_rating decimal(5,2) NOT NULL,
    supplier_status varchar(20) NOT NULL,
    created_at datetime2(0) NOT NULL CONSTRAINT DF_supplier_created DEFAULT (SYSUTCDATETIME()),
    created_by nvarchar(80) NOT NULL CONSTRAINT DF_supplier_creator DEFAULT (SUSER_SNAME()),
    updated_at datetime2(0) NOT NULL CONSTRAINT DF_supplier_updated DEFAULT (SYSUTCDATETIME()),
    updated_by nvarchar(80) NOT NULL CONSTRAINT DF_supplier_updater DEFAULT (SUSER_SNAME()),
    CONSTRAINT CK_supplier_rating CHECK (supplier_rating BETWEEN 0 AND 100),
    CONSTRAINT CK_supplier_status CHECK (supplier_status IN ('APPROVED','SUSPENDED','EXPIRED'))
);
GO

CREATE TABLE aero.part_master (
    part_id int IDENTITY(1,1) NOT NULL CONSTRAINT PK_part_master PRIMARY KEY,
    part_number nvarchar(80) NOT NULL CONSTRAINT UQ_part_number UNIQUE,
    part_name nvarchar(200) NOT NULL,
    manufacturer_id int NOT NULL,
    ata_code char(4) NOT NULL,
    unit_code varchar(10) NOT NULL,
    serialized_flag bit NOT NULL,
    batch_control_flag bit NOT NULL,
    life_limited_flag bit NOT NULL,
    repairable_flag bit NOT NULL,
    shelf_life_days int NULL,
    active_status varchar(20) NOT NULL,
    created_at datetime2(0) NOT NULL CONSTRAINT DF_part_created DEFAULT (SYSUTCDATETIME()),
    created_by nvarchar(80) NOT NULL CONSTRAINT DF_part_creator DEFAULT (SUSER_SNAME()),
    updated_at datetime2(0) NOT NULL CONSTRAINT DF_part_updated DEFAULT (SYSUTCDATETIME()),
    updated_by nvarchar(80) NOT NULL CONSTRAINT DF_part_updater DEFAULT (SUSER_SNAME()),
    row_version rowversion NOT NULL,
    CONSTRAINT FK_part_manufacturer FOREIGN KEY (manufacturer_id) REFERENCES aero.manufacturer(manufacturer_id),
    CONSTRAINT FK_part_ata FOREIGN KEY (ata_code) REFERENCES aero.ata_chapter(ata_code),
    CONSTRAINT CK_part_unit CHECK (unit_code IN ('EA','SET','M','KG','L')),
    CONSTRAINT CK_part_status CHECK (active_status IN ('ACTIVE','OBSOLETE','RESTRICTED')),
    CONSTRAINT CK_part_shelf_life CHECK (shelf_life_days IS NULL OR shelf_life_days > 0),
    CONSTRAINT CK_part_control CHECK (serialized_flag = 1 OR batch_control_flag = 1)
);
GO

CREATE TABLE aero.part_applicability (
    part_id int NOT NULL,
    aircraft_type_id int NOT NULL,
    effective_from date NOT NULL,
    effective_to date NULL,
    applicability_note nvarchar(500) NULL,
    created_at datetime2(0) NOT NULL CONSTRAINT DF_applicability_created DEFAULT (SYSUTCDATETIME()),
    created_by nvarchar(80) NOT NULL CONSTRAINT DF_applicability_creator DEFAULT (SUSER_SNAME()),
    CONSTRAINT PK_part_applicability PRIMARY KEY (part_id, aircraft_type_id, effective_from),
    CONSTRAINT FK_applicability_part FOREIGN KEY (part_id) REFERENCES aero.part_master(part_id),
    CONSTRAINT FK_applicability_aircraft_type FOREIGN KEY (aircraft_type_id) REFERENCES aero.aircraft_type(aircraft_type_id),
    CONSTRAINT CK_applicability_dates CHECK (effective_to IS NULL OR effective_to >= effective_from)
);
GO

CREATE TABLE aero.part_alternative (
    part_alternative_id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_part_alternative PRIMARY KEY,
    base_part_id int NOT NULL,
    alternative_part_id int NOT NULL,
    relation_type varchar(20) NOT NULL,
    effective_from date NOT NULL,
    effective_to date NULL,
    created_at datetime2(0) NOT NULL CONSTRAINT DF_part_alt_created DEFAULT (SYSUTCDATETIME()),
    created_by nvarchar(80) NOT NULL CONSTRAINT DF_part_alt_creator DEFAULT (SUSER_SNAME()),
    CONSTRAINT UQ_part_alternative UNIQUE (base_part_id, alternative_part_id, effective_from),
    CONSTRAINT FK_part_alt_base FOREIGN KEY (base_part_id) REFERENCES aero.part_master(part_id),
    CONSTRAINT FK_part_alt_alt FOREIGN KEY (alternative_part_id) REFERENCES aero.part_master(part_id),
    CONSTRAINT CK_part_alt_not_self CHECK (base_part_id <> alternative_part_id),
    CONSTRAINT CK_part_alt_type CHECK (relation_type IN ('INTERCHANGEABLE','SUPERSEDED_BY','ALTERNATE')),
    CONSTRAINT CK_part_alt_dates CHECK (effective_to IS NULL OR effective_to >= effective_from)
);
GO

CREATE TABLE aero.warehouse (
    warehouse_id int IDENTITY(1,1) NOT NULL CONSTRAINT PK_warehouse PRIMARY KEY,
    warehouse_code nvarchar(30) NOT NULL CONSTRAINT UQ_warehouse_code UNIQUE,
    warehouse_name nvarchar(200) NOT NULL,
    organization_code nvarchar(30) NOT NULL,
    active_flag bit NOT NULL CONSTRAINT DF_warehouse_active DEFAULT (1),
    created_at datetime2(0) NOT NULL CONSTRAINT DF_warehouse_created DEFAULT (SYSUTCDATETIME()),
    created_by nvarchar(80) NOT NULL CONSTRAINT DF_warehouse_creator DEFAULT (SUSER_SNAME()),
    updated_at datetime2(0) NOT NULL CONSTRAINT DF_warehouse_updated DEFAULT (SYSUTCDATETIME()),
    updated_by nvarchar(80) NOT NULL CONSTRAINT DF_warehouse_updater DEFAULT (SUSER_SNAME())
);
GO

CREATE TABLE aero.storage_location (
    location_id int IDENTITY(1,1) NOT NULL CONSTRAINT PK_storage_location PRIMARY KEY,
    warehouse_id int NOT NULL,
    location_code nvarchar(50) NOT NULL,
    environment_class varchar(20) NOT NULL,
    hazardous_class varchar(20) NULL,
    quarantine_flag bit NOT NULL CONSTRAINT DF_location_quarantine DEFAULT (0),
    active_flag bit NOT NULL CONSTRAINT DF_location_active DEFAULT (1),
    created_at datetime2(0) NOT NULL CONSTRAINT DF_location_created DEFAULT (SYSUTCDATETIME()),
    created_by nvarchar(80) NOT NULL CONSTRAINT DF_location_creator DEFAULT (SUSER_SNAME()),
    updated_at datetime2(0) NOT NULL CONSTRAINT DF_location_updated DEFAULT (SYSUTCDATETIME()),
    updated_by nvarchar(80) NOT NULL CONSTRAINT DF_location_updater DEFAULT (SUSER_SNAME()),
    CONSTRAINT UQ_storage_location UNIQUE (warehouse_id, location_code),
    CONSTRAINT FK_location_warehouse FOREIGN KEY (warehouse_id) REFERENCES aero.warehouse(warehouse_id),
    CONSTRAINT CK_location_environment CHECK (environment_class IN ('NORMAL','COLD','DRY','CONTROLLED'))
);
GO

CREATE TABLE aero.part_instance (
    part_instance_id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_part_instance PRIMARY KEY,
    part_id int NOT NULL,
    serial_number nvarchar(100) NULL,
    batch_number nvarchar(100) NULL,
    production_date date NULL,
    expiry_date date NULL,
    condition_status varchar(20) NOT NULL,
    current_location_id int NULL,
    on_hand_quantity decimal(18,3) NOT NULL,
    received_at datetime2(0) NOT NULL,
    created_at datetime2(0) NOT NULL CONSTRAINT DF_instance_created DEFAULT (SYSUTCDATETIME()),
    created_by nvarchar(80) NOT NULL CONSTRAINT DF_instance_creator DEFAULT (SUSER_SNAME()),
    updated_at datetime2(0) NOT NULL CONSTRAINT DF_instance_updated DEFAULT (SYSUTCDATETIME()),
    updated_by nvarchar(80) NOT NULL CONSTRAINT DF_instance_updater DEFAULT (SUSER_SNAME()),
    row_version rowversion NOT NULL,
    CONSTRAINT FK_instance_part FOREIGN KEY (part_id) REFERENCES aero.part_master(part_id),
    CONSTRAINT FK_instance_location FOREIGN KEY (current_location_id) REFERENCES aero.storage_location(location_id),
    CONSTRAINT CK_instance_condition CHECK (condition_status IN ('SERVICEABLE','UNSERVICEABLE','QUARANTINE','INSTALLED','REPAIR','SCRAPPED')),
    CONSTRAINT CK_instance_quantity CHECK (on_hand_quantity >= 0),
    CONSTRAINT CK_instance_dates CHECK (expiry_date IS NULL OR production_date IS NULL OR expiry_date >= production_date)
);
GO
CREATE UNIQUE INDEX UX_part_instance_serial ON aero.part_instance(part_id, serial_number) WHERE serial_number IS NOT NULL;
CREATE INDEX IX_part_instance_location ON aero.part_instance(current_location_id, condition_status);
GO

CREATE TABLE aero.inventory_balance (
    part_instance_id bigint NOT NULL CONSTRAINT PK_inventory_balance PRIMARY KEY,
    location_id int NOT NULL,
    available_quantity decimal(18,3) NOT NULL,
    frozen_quantity decimal(18,3) NOT NULL,
    balance_updated_at datetime2(0) NOT NULL,
    updated_by nvarchar(80) NOT NULL,
    CONSTRAINT FK_balance_instance FOREIGN KEY (part_instance_id) REFERENCES aero.part_instance(part_instance_id),
    CONSTRAINT FK_balance_location FOREIGN KEY (location_id) REFERENCES aero.storage_location(location_id),
    CONSTRAINT CK_balance_quantity CHECK (available_quantity >= 0 AND frozen_quantity >= 0)
);
GO

CREATE TABLE aero.inventory_transaction (
    inventory_transaction_id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_inventory_transaction PRIMARY KEY,
    part_instance_id bigint NOT NULL,
    part_id int NOT NULL,
    transaction_type varchar(20) NOT NULL,
    source_location_id int NULL,
    target_location_id int NULL,
    quantity decimal(18,3) NOT NULL,
    transaction_time datetime2(0) NOT NULL,
    reference_type varchar(30) NOT NULL,
    reference_id bigint NOT NULL,
    operator_id nvarchar(80) NULL,
    part_number_snapshot nvarchar(80) NOT NULL,
    part_name_snapshot nvarchar(200) NOT NULL,
    created_at datetime2(0) NOT NULL CONSTRAINT DF_tx_created DEFAULT (SYSUTCDATETIME()),
    created_by nvarchar(80) NOT NULL CONSTRAINT DF_tx_creator DEFAULT (SUSER_SNAME()),
    CONSTRAINT FK_tx_instance FOREIGN KEY (part_instance_id) REFERENCES aero.part_instance(part_instance_id),
    CONSTRAINT FK_tx_part FOREIGN KEY (part_id) REFERENCES aero.part_master(part_id),
    CONSTRAINT FK_tx_source FOREIGN KEY (source_location_id) REFERENCES aero.storage_location(location_id),
    CONSTRAINT FK_tx_target FOREIGN KEY (target_location_id) REFERENCES aero.storage_location(location_id),
    CONSTRAINT CK_tx_type CHECK (transaction_type IN ('RECEIPT','ISSUE','TRANSFER','INSTALL','REMOVE','FREEZE','UNFREEZE','SCRAP','ADJUST')),
    CONSTRAINT CK_tx_quantity CHECK (quantity > 0),
    CONSTRAINT CK_tx_location CHECK (source_location_id IS NOT NULL OR target_location_id IS NOT NULL)
);
GO
CREATE INDEX IX_inventory_transaction_instance_time ON aero.inventory_transaction(part_instance_id, transaction_time);
CREATE INDEX IX_inventory_transaction_reference ON aero.inventory_transaction(reference_type, reference_id);
GO

CREATE TABLE aero.purchase_order (
    purchase_order_id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_purchase_order PRIMARY KEY,
    purchase_order_no nvarchar(40) NOT NULL CONSTRAINT UQ_purchase_order_no UNIQUE,
    supplier_id int NOT NULL,
    order_date date NOT NULL,
    currency_code char(3) NOT NULL,
    order_status varchar(20) NOT NULL,
    requested_by nvarchar(80) NOT NULL,
    created_at datetime2(0) NOT NULL CONSTRAINT DF_po_created DEFAULT (SYSUTCDATETIME()),
    created_by nvarchar(80) NOT NULL CONSTRAINT DF_po_creator DEFAULT (SUSER_SNAME()),
    updated_at datetime2(0) NOT NULL CONSTRAINT DF_po_updated DEFAULT (SYSUTCDATETIME()),
    updated_by nvarchar(80) NOT NULL CONSTRAINT DF_po_updater DEFAULT (SUSER_SNAME()),
    CONSTRAINT FK_po_supplier FOREIGN KEY (supplier_id) REFERENCES aero.supplier(supplier_id),
    CONSTRAINT CK_po_status CHECK (order_status IN ('DRAFT','APPROVED','PARTIAL','CLOSED','CANCELLED'))
);
GO

CREATE TABLE aero.purchase_order_line (
    purchase_order_line_id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_purchase_order_line PRIMARY KEY,
    purchase_order_id bigint NOT NULL,
    line_no int NOT NULL,
    part_id int NOT NULL,
    ordered_quantity decimal(18,3) NOT NULL,
    unit_price decimal(18,2) NOT NULL,
    required_date date NOT NULL,
    received_quantity decimal(18,3) NOT NULL CONSTRAINT DF_po_line_received DEFAULT (0),
    created_at datetime2(0) NOT NULL CONSTRAINT DF_po_line_created DEFAULT (SYSUTCDATETIME()),
    created_by nvarchar(80) NOT NULL CONSTRAINT DF_po_line_creator DEFAULT (SUSER_SNAME()),
    CONSTRAINT UQ_purchase_order_line UNIQUE (purchase_order_id, line_no),
    CONSTRAINT FK_po_line_order FOREIGN KEY (purchase_order_id) REFERENCES aero.purchase_order(purchase_order_id),
    CONSTRAINT FK_po_line_part FOREIGN KEY (part_id) REFERENCES aero.part_master(part_id),
    CONSTRAINT CK_po_line_quantity CHECK (ordered_quantity > 0 AND received_quantity >= 0 AND received_quantity <= ordered_quantity * 1.05),
    CONSTRAINT CK_po_line_price CHECK (unit_price >= 0)
);
GO

CREATE TABLE aero.receipt (
    receipt_id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_receipt PRIMARY KEY,
    receipt_no nvarchar(40) NOT NULL CONSTRAINT UQ_receipt_no UNIQUE,
    purchase_order_id bigint NOT NULL,
    received_at datetime2(0) NOT NULL,
    received_by nvarchar(80) NULL,
    receipt_status varchar(20) NOT NULL,
    created_at datetime2(0) NOT NULL CONSTRAINT DF_receipt_created DEFAULT (SYSUTCDATETIME()),
    created_by nvarchar(80) NOT NULL CONSTRAINT DF_receipt_creator DEFAULT (SUSER_SNAME()),
    updated_at datetime2(0) NOT NULL CONSTRAINT DF_receipt_updated DEFAULT (SYSUTCDATETIME()),
    updated_by nvarchar(80) NOT NULL CONSTRAINT DF_receipt_updater DEFAULT (SUSER_SNAME()),
    CONSTRAINT FK_receipt_po FOREIGN KEY (purchase_order_id) REFERENCES aero.purchase_order(purchase_order_id),
    CONSTRAINT CK_receipt_status CHECK (receipt_status IN ('RECEIVED','INSPECTION','ACCEPTED','REJECTED'))
);
GO

CREATE TABLE aero.receipt_line (
    receipt_line_id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_receipt_line PRIMARY KEY,
    receipt_id bigint NOT NULL,
    purchase_order_line_id bigint NOT NULL,
    part_instance_id bigint NOT NULL,
    received_quantity decimal(18,3) NOT NULL,
    certificate_required_flag bit NOT NULL,
    certificate_no_received nvarchar(100) NULL,
    created_at datetime2(0) NOT NULL CONSTRAINT DF_receipt_line_created DEFAULT (SYSUTCDATETIME()),
    created_by nvarchar(80) NOT NULL CONSTRAINT DF_receipt_line_creator DEFAULT (SUSER_SNAME()),
    CONSTRAINT UQ_receipt_line_instance UNIQUE (receipt_id, part_instance_id),
    CONSTRAINT FK_receipt_line_receipt FOREIGN KEY (receipt_id) REFERENCES aero.receipt(receipt_id),
    CONSTRAINT FK_receipt_line_po_line FOREIGN KEY (purchase_order_line_id) REFERENCES aero.purchase_order_line(purchase_order_line_id),
    CONSTRAINT FK_receipt_line_instance FOREIGN KEY (part_instance_id) REFERENCES aero.part_instance(part_instance_id),
    CONSTRAINT CK_receipt_line_quantity CHECK (received_quantity > 0)
);
GO

CREATE TABLE aero.certificate_document (
    certificate_document_id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_certificate_document PRIMARY KEY,
    part_instance_id bigint NOT NULL,
    certificate_type varchar(30) NOT NULL,
    certificate_no nvarchar(100) NOT NULL,
    issuer_name nvarchar(200) NOT NULL,
    issue_date date NOT NULL,
    valid_to date NULL,
    document_hash char(64) NOT NULL,
    verification_status varchar(20) NOT NULL,
    created_at datetime2(0) NOT NULL CONSTRAINT DF_certificate_created DEFAULT (SYSUTCDATETIME()),
    created_by nvarchar(80) NOT NULL CONSTRAINT DF_certificate_creator DEFAULT (SUSER_SNAME()),
    CONSTRAINT UQ_certificate_no UNIQUE (certificate_type, certificate_no),
    CONSTRAINT FK_certificate_instance FOREIGN KEY (part_instance_id) REFERENCES aero.part_instance(part_instance_id),
    CONSTRAINT CK_certificate_type CHECK (certificate_type IN ('EASA_FORM1','FAA_8130_3','COC','RELEASE_NOTE')),
    CONSTRAINT CK_certificate_status CHECK (verification_status IN ('VERIFIED','PENDING','REJECTED')),
    CONSTRAINT CK_certificate_dates CHECK (valid_to IS NULL OR valid_to >= issue_date)
);
GO

CREATE TABLE aero.inspection_record (
    inspection_record_id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_inspection_record PRIMARY KEY,
    receipt_line_id bigint NOT NULL,
    part_instance_id bigint NOT NULL,
    inspection_result varchar(20) NOT NULL,
    inspected_at datetime2(0) NOT NULL,
    inspector_id nvarchar(80) NOT NULL,
    defect_note nvarchar(1000) NULL,
    created_at datetime2(0) NOT NULL CONSTRAINT DF_inspection_created DEFAULT (SYSUTCDATETIME()),
    created_by nvarchar(80) NOT NULL CONSTRAINT DF_inspection_creator DEFAULT (SUSER_SNAME()),
    CONSTRAINT UQ_inspection_receipt_line UNIQUE (receipt_line_id),
    CONSTRAINT FK_inspection_receipt_line FOREIGN KEY (receipt_line_id) REFERENCES aero.receipt_line(receipt_line_id),
    CONSTRAINT FK_inspection_instance FOREIGN KEY (part_instance_id) REFERENCES aero.part_instance(part_instance_id),
    CONSTRAINT CK_inspection_result CHECK (inspection_result IN ('PASS','FAIL','CONDITIONAL'))
);
GO

CREATE TABLE aero.maintenance_work_order (
    maintenance_work_order_id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_maintenance_work_order PRIMARY KEY,
    work_order_no nvarchar(40) NOT NULL CONSTRAINT UQ_work_order_no UNIQUE,
    aircraft_id int NOT NULL,
    task_type varchar(30) NOT NULL,
    opened_at datetime2(0) NOT NULL,
    closed_at datetime2(0) NULL,
    work_order_status varchar(20) NOT NULL,
    created_at datetime2(0) NOT NULL CONSTRAINT DF_mwo_created DEFAULT (SYSUTCDATETIME()),
    created_by nvarchar(80) NOT NULL CONSTRAINT DF_mwo_creator DEFAULT (SUSER_SNAME()),
    updated_at datetime2(0) NOT NULL CONSTRAINT DF_mwo_updated DEFAULT (SYSUTCDATETIME()),
    updated_by nvarchar(80) NOT NULL CONSTRAINT DF_mwo_updater DEFAULT (SUSER_SNAME()),
    CONSTRAINT FK_mwo_aircraft FOREIGN KEY (aircraft_id) REFERENCES aero.aircraft(aircraft_id),
    CONSTRAINT CK_mwo_status CHECK (work_order_status IN ('OPEN','IN_PROGRESS','CLOSED','CANCELLED')),
    CONSTRAINT CK_mwo_dates CHECK (closed_at IS NULL OR closed_at >= opened_at)
);
GO

CREATE TABLE aero.install_remove_event (
    install_remove_event_id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_install_remove_event PRIMARY KEY,
    maintenance_work_order_id bigint NOT NULL,
    aircraft_id int NOT NULL,
    part_instance_id bigint NOT NULL,
    installation_position nvarchar(80) NOT NULL,
    installed_at datetime2(0) NOT NULL,
    removed_at datetime2(0) NULL,
    removal_reason nvarchar(500) NULL,
    created_at datetime2(0) NOT NULL CONSTRAINT DF_install_event_created DEFAULT (SYSUTCDATETIME()),
    created_by nvarchar(80) NOT NULL CONSTRAINT DF_install_event_creator DEFAULT (SUSER_SNAME()),
    CONSTRAINT FK_install_mwo FOREIGN KEY (maintenance_work_order_id) REFERENCES aero.maintenance_work_order(maintenance_work_order_id),
    CONSTRAINT FK_install_aircraft FOREIGN KEY (aircraft_id) REFERENCES aero.aircraft(aircraft_id),
    CONSTRAINT FK_install_instance FOREIGN KEY (part_instance_id) REFERENCES aero.part_instance(part_instance_id),
    CONSTRAINT CK_install_dates CHECK (removed_at IS NULL OR removed_at >= installed_at)
);
GO
CREATE UNIQUE INDEX UX_active_installation ON aero.install_remove_event(part_instance_id) WHERE removed_at IS NULL;
GO

CREATE TABLE aero.usage_snapshot (
    usage_snapshot_id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_usage_snapshot PRIMARY KEY,
    part_instance_id bigint NOT NULL,
    snapshot_at datetime2(0) NOT NULL,
    flight_hours decimal(18,2) NOT NULL,
    flight_cycles int NOT NULL,
    source_system nvarchar(50) NOT NULL,
    created_at datetime2(0) NOT NULL CONSTRAINT DF_usage_created DEFAULT (SYSUTCDATETIME()),
    created_by nvarchar(80) NOT NULL CONSTRAINT DF_usage_creator DEFAULT (SUSER_SNAME()),
    CONSTRAINT UQ_usage_snapshot UNIQUE (part_instance_id, snapshot_at),
    CONSTRAINT FK_usage_instance FOREIGN KEY (part_instance_id) REFERENCES aero.part_instance(part_instance_id),
    CONSTRAINT CK_usage_nonnegative CHECK (flight_hours >= 0 AND flight_cycles >= 0)
);
GO

CREATE TABLE aero.life_limit_control (
    life_limit_control_id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_life_limit_control PRIMARY KEY,
    part_instance_id bigint NOT NULL,
    limit_type varchar(20) NOT NULL,
    limit_value decimal(18,2) NOT NULL,
    used_value decimal(18,2) NOT NULL,
    remaining_value AS (limit_value - used_value) PERSISTED,
    evaluated_at datetime2(0) NOT NULL,
    created_at datetime2(0) NOT NULL CONSTRAINT DF_life_created DEFAULT (SYSUTCDATETIME()),
    created_by nvarchar(80) NOT NULL CONSTRAINT DF_life_creator DEFAULT (SUSER_SNAME()),
    CONSTRAINT UQ_life_limit UNIQUE (part_instance_id, limit_type),
    CONSTRAINT FK_life_instance FOREIGN KEY (part_instance_id) REFERENCES aero.part_instance(part_instance_id),
    CONSTRAINT CK_life_type CHECK (limit_type IN ('HOURS','CYCLES','CALENDAR_DAYS')),
    CONSTRAINT CK_life_values CHECK (limit_value > 0 AND used_value >= 0 AND used_value <= limit_value)
);
GO

CREATE TABLE aero.repair_order (
    repair_order_id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_repair_order PRIMARY KEY,
    repair_order_no nvarchar(40) NOT NULL CONSTRAINT UQ_repair_order_no UNIQUE,
    part_instance_id bigint NOT NULL,
    supplier_id int NOT NULL,
    sent_at datetime2(0) NOT NULL,
    returned_at datetime2(0) NULL,
    repair_status varchar(20) NOT NULL,
    repair_result nvarchar(500) NULL,
    created_at datetime2(0) NOT NULL CONSTRAINT DF_repair_created DEFAULT (SYSUTCDATETIME()),
    created_by nvarchar(80) NOT NULL CONSTRAINT DF_repair_creator DEFAULT (SUSER_SNAME()),
    updated_at datetime2(0) NOT NULL CONSTRAINT DF_repair_updated DEFAULT (SYSUTCDATETIME()),
    updated_by nvarchar(80) NOT NULL CONSTRAINT DF_repair_updater DEFAULT (SUSER_SNAME()),
    CONSTRAINT FK_repair_instance FOREIGN KEY (part_instance_id) REFERENCES aero.part_instance(part_instance_id),
    CONSTRAINT FK_repair_supplier FOREIGN KEY (supplier_id) REFERENCES aero.supplier(supplier_id),
    CONSTRAINT CK_repair_status CHECK (repair_status IN ('SENT','IN_REPAIR','RETURNED','SCRAPPED')),
    CONSTRAINT CK_repair_dates CHECK (returned_at IS NULL OR returned_at >= sent_at)
);
GO

CREATE TABLE aero.scrap_record (
    scrap_record_id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_scrap_record PRIMARY KEY,
    part_instance_id bigint NOT NULL CONSTRAINT UQ_scrap_instance UNIQUE,
    scrap_date date NOT NULL,
    scrap_reason nvarchar(500) NOT NULL,
    approved_by nvarchar(80) NOT NULL,
    disposal_certificate_no nvarchar(100) NOT NULL,
    created_at datetime2(0) NOT NULL CONSTRAINT DF_scrap_created DEFAULT (SYSUTCDATETIME()),
    created_by nvarchar(80) NOT NULL CONSTRAINT DF_scrap_creator DEFAULT (SUSER_SNAME()),
    CONSTRAINT FK_scrap_instance FOREIGN KEY (part_instance_id) REFERENCES aero.part_instance(part_instance_id)
);
GO

/* Evaluation laboratory metadata and truth tables. */
CREATE TABLE dq.quality_rule (
    rule_id nvarchar(80) NOT NULL CONSTRAINT PK_quality_rule PRIMARY KEY,
    rule_domain varchar(10) NOT NULL,
    indicator_id varchar(10) NOT NULL,
    rule_name nvarchar(200) NOT NULL,
    rule_expression nvarchar(max) NOT NULL,
    severity decimal(5,4) NOT NULL,
    critical_flag bit NOT NULL,
    active_flag bit NOT NULL CONSTRAINT DF_quality_rule_active DEFAULT (1),
    created_at datetime2(0) NOT NULL CONSTRAINT DF_quality_rule_created DEFAULT (SYSUTCDATETIME()),
    CONSTRAINT CK_quality_rule_domain CHECK (rule_domain IN ('DATA','SCHEMA','COUPLING')),
    CONSTRAINT CK_quality_rule_severity CHECK (severity BETWEEN 0 AND 1)
);
GO
CREATE TABLE dq.relationship_control_registry (
    relationship_id nvarchar(80) NOT NULL CONSTRAINT PK_relationship_control_registry PRIMARY KEY,
    child_table nvarchar(256) NOT NULL,
    child_columns nvarchar(500) NOT NULL,
    parent_table nvarchar(256) NOT NULL,
    parent_columns nvarchar(500) NOT NULL,
    cardinality varchar(30) NOT NULL,
    criticality varchar(20) NOT NULL,
    physical_fk_required bit NOT NULL,
    enforcement_modes nvarchar(500) NOT NULL,
    control_coverage decimal(6,5) NOT NULL,
    control_reliability decimal(6,5) NOT NULL,
    operating_effectiveness decimal(6,5) NOT NULL,
    exception_approved bit NOT NULL,
    exception_reason nvarchar(1000) NULL,
    performance_evidence_id nvarchar(100) NULL,
    owner_name nvarchar(200) NOT NULL,
    review_due_date date NULL,
    maximum_orphan_rate decimal(8,7) NOT NULL,
    minimum_control_score decimal(6,5) NOT NULL,
    created_at datetime2(0) NOT NULL CONSTRAINT DF_rel_registry_created DEFAULT (SYSUTCDATETIME()),
    CONSTRAINT CK_rel_registry_criticality CHECK (criticality IN ('low','medium','high','critical')),
    CONSTRAINT CK_rel_registry_rates CHECK (
        control_coverage BETWEEN 0 AND 1 AND control_reliability BETWEEN 0 AND 1
        AND operating_effectiveness BETWEEN 0 AND 1 AND maximum_orphan_rate BETWEEN 0 AND 1
        AND minimum_control_score BETWEEN 0 AND 1
    )
);
GO

CREATE TABLE dq.quality_run (
    quality_run_id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_quality_run PRIMARY KEY,
    dataset_version nvarchar(40) NOT NULL,
    scenario_id nvarchar(80) NOT NULL,
    algorithm_version nvarchar(40) NOT NULL,
    weight_version nvarchar(40) NOT NULL,
    random_seed int NOT NULL,
    started_at datetime2(0) NOT NULL,
    finished_at datetime2(0) NULL,
    run_status varchar(20) NOT NULL,
    CONSTRAINT CK_quality_run_status CHECK (run_status IN ('RUNNING','SUCCESS','FAILED'))
);
GO
CREATE TABLE dq.quality_issue (
    quality_issue_id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_quality_issue PRIMARY KEY,
    quality_run_id bigint NOT NULL,
    rule_id nvarchar(80) NOT NULL,
    target_table nvarchar(256) NOT NULL,
    target_column nvarchar(128) NULL,
    target_key nvarchar(500) NULL,
    confidence decimal(6,5) NOT NULL,
    detected_flag bit NOT NULL,
    verified_flag bit NULL,
    created_at datetime2(0) NOT NULL CONSTRAINT DF_quality_issue_created DEFAULT (SYSUTCDATETIME()),
    CONSTRAINT FK_quality_issue_run FOREIGN KEY (quality_run_id) REFERENCES dq.quality_run(quality_run_id),
    CONSTRAINT FK_quality_issue_rule FOREIGN KEY (rule_id) REFERENCES dq.quality_rule(rule_id),
    CONSTRAINT CK_quality_issue_confidence CHECK (confidence BETWEEN 0 AND 1)
);
GO
CREATE TABLE dq.benchmark_defect_label (
    defect_label_id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_benchmark_defect_label PRIMARY KEY,
    scenario_id nvarchar(80) NOT NULL,
    defect_domain varchar(10) NOT NULL,
    indicator_id varchar(10) NOT NULL,
    defect_type nvarchar(100) NOT NULL,
    target_table nvarchar(256) NOT NULL,
    target_column nvarchar(128) NULL,
    target_key nvarchar(500) NULL,
    severity decimal(5,4) NOT NULL,
    causal_parent_scenario_id nvarchar(80) NULL,
    expected_effect nvarchar(1000) NOT NULL,
    random_seed int NOT NULL,
    created_at datetime2(0) NOT NULL CONSTRAINT DF_defect_label_created DEFAULT (SYSUTCDATETIME()),
    CONSTRAINT CK_defect_domain CHECK (defect_domain IN ('DATA','SCHEMA','COUPLING')),
    CONSTRAINT CK_defect_severity CHECK (severity BETWEEN 0 AND 1)
);
GO

/* Machine-readable descriptions: benchmark labels, not substitutes for expert definitions. */
DECLARE @schema sysname, @table sysname, @column sysname, @sql nvarchar(max);
DECLARE table_cursor CURSOR LOCAL FAST_FORWARD FOR
SELECT s.name, t.name FROM sys.tables t JOIN sys.schemas s ON s.schema_id=t.schema_id
WHERE s.name IN (N'aero',N'dq');
OPEN table_cursor;
FETCH NEXT FROM table_cursor INTO @schema,@table;
WHILE @@FETCH_STATUS=0
BEGIN
    BEGIN TRY
        EXEC sys.sp_addextendedproperty @name=N'MS_Description',
             @value=N'AeroMRO-EDQSG benchmark table: '+@table,
             @level0type=N'SCHEMA',@level0name=@schema,@level1type=N'TABLE',@level1name=@table;
    END TRY BEGIN CATCH END CATCH;
    FETCH NEXT FROM table_cursor INTO @schema,@table;
END
CLOSE table_cursor; DEALLOCATE table_cursor;

DECLARE column_cursor CURSOR LOCAL FAST_FORWARD FOR
SELECT s.name,t.name,c.name FROM sys.columns c JOIN sys.tables t ON t.object_id=c.object_id
JOIN sys.schemas s ON s.schema_id=t.schema_id WHERE s.name IN (N'aero',N'dq');
OPEN column_cursor;
FETCH NEXT FROM column_cursor INTO @schema,@table,@column;
WHILE @@FETCH_STATUS=0
BEGIN
    BEGIN TRY
        EXEC sys.sp_addextendedproperty @name=N'MS_Description',
             @value=N'AeroMRO benchmark field: '+@column,
             @level0type=N'SCHEMA',@level0name=@schema,@level1type=N'TABLE',@level1name=@table,
             @level2type=N'COLUMN',@level2name=@column;
    END TRY BEGIN CATCH END CATCH;
    FETCH NEXT FROM column_cursor INTO @schema,@table,@column;
END
CLOSE column_cursor; DEALLOCATE column_cursor;
GO
