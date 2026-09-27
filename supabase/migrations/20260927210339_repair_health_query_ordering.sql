SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '30s';
CREATE INDEX IF NOT EXISTS fdep_erp_received_health_nullslast_idx
  ON public.fdep_erp (received_date DESC NULLS LAST)
  WHERE received_date IS NOT NULL;
COMMENT ON INDEX public.fdep_erp_received_health_nullslast_idx IS 'Matches the deployed public health query sort order; prevents a full scan/sort for LIMIT 1.';
