DROP VIEW IF EXISTS v_events_unified;

CREATE VIEW v_events_unified AS
SELECT
  ocel_id AS event_id,
  'ApprovePurchaseOrder' AS activity,
  ocel_time AS ts,
  resource,
  lifecycle,
  NULL AS raw
FROM event_ApprovePurchaseOrder
UNION ALL
SELECT
  ocel_id AS event_id,
  'ApprovePurchaseRequisition' AS activity,
  ocel_time AS ts,
  resource,
  lifecycle,
  NULL AS raw
FROM event_ApprovePurchaseRequisition
UNION ALL
SELECT
  ocel_id AS event_id,
  'CreateGoodsReceipt' AS activity,
  ocel_time AS ts,
  resource,
  lifecycle,
  NULL AS raw
FROM event_CreateGoodsReceipt
UNION ALL
SELECT
  ocel_id AS event_id,
  'CreateInvoiceReceipt' AS activity,
  ocel_time AS ts,
  resource,
  lifecycle,
  NULL AS raw
FROM event_CreateInvoiceReceipt
UNION ALL
SELECT
  ocel_id AS event_id,
  'CreatePurchaseOrder' AS activity,
  ocel_time AS ts,
  resource,
  lifecycle,
  NULL AS raw
FROM event_CreatePurchaseOrder
UNION ALL
SELECT
  ocel_id AS event_id,
  'CreatePurchaseRequisition' AS activity,
  ocel_time AS ts,
  resource,
  lifecycle,
  NULL AS raw
FROM event_CreatePurchaseRequisition
UNION ALL
SELECT
  ocel_id AS event_id,
  'CreateRequestforQuotation' AS activity,
  ocel_time AS ts,
  resource,
  lifecycle,
  NULL AS raw
FROM event_CreateRequestforQuotation
UNION ALL
SELECT
  ocel_id AS event_id,
  'DelegatePurchaseRequisitionApproval' AS activity,
  ocel_time AS ts,
  resource,
  lifecycle,
  NULL AS raw
FROM event_DelegatePurchaseRequisitionApproval
UNION ALL
SELECT
  ocel_id AS event_id,
  'ExecutePayment' AS activity,
  ocel_time AS ts,
  resource,
  lifecycle,
  NULL AS raw
FROM event_ExecutePayment
UNION ALL
SELECT
  ocel_id AS event_id,
  'PerformTwoWayMatch' AS activity,
  ocel_time AS ts,
  resource,
  lifecycle,
  NULL AS raw
FROM event_PerformTwoWayMatch;
